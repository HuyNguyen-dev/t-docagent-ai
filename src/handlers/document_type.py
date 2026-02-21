import asyncio
import io
import mimetypes
import re
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

import orjson
from fastapi import BackgroundTasks, Form, HTTPException, UploadFile, status
from pymongo import DESCENDING

from agents.training_agent.agent import ExtractionAgent
from config import settings
from handlers.document import DocumentHandler
from handlers.document_format import DocumentFormatHandler
from models.document_content import DocumentContent
from models.document_format import DocumentFormat
from models.document_type import DocumentType
from models.document_work_item import DocumentWorkItem
from schemas.document_format import (
    BaseMappingProperty,
    DocumentFormatDasboardQuery,
    DocumentFormatDeleteQuery,
    DocumentFormatField,
    DocumentFormatQuery,
    DocumentFormatTable,
)
from schemas.document_type import (
    DocumentTypeDashboardItem,
    DocumentTypeDashboardWorkItem,
    DocumentTypeDFTrainingItem,
    DocumentTypeName,
    DocumentTypeResponse,
    DocumentTypeUpdate,
    DocumentTypeUpdateDisplay,
)
from schemas.export import DocumentTypeExport, MetadataExport
from schemas.response import Page, PaginatedMetadata
from utils.constants import DEFAULT_COLUMN_IDS, DEFAULT_COLUMN_NAMES, DEFAULT_WORK_ITEMS_FOLDER, TIMEZONE
from utils.enums import DocumentContentState, DocumentFormatState, DocWorkItemStage, DocWorkItemState, TimeRangeFilter
from utils.logger.custom_logging import LoggerMixin

df_handler = DocumentFormatHandler()


class DocumentTypeChecker(LoggerMixin):
    async def __call__(self, dt_name: str = Form(description="The name of new document type")) -> str | HTTPException:
        """Check if document type name already exists."""
        existing_dt = await DocumentType.find_one(
            DocumentType.name
            == {
                "$regex": f"^{re.escape(dt_name)}$",
                "$options": "i",
            },
        )
        if existing_dt:
            self.logger.warning(
                "event=document-type-name-already-exists dt_name=%s",
                dt_name,
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Document type with name '{dt_name}' already exists",
            )
        return dt_name


class DocumentTypeHandler(LoggerMixin):
    def __init__(self) -> None:
        self.document_handler = DocumentHandler()
        super().__init__()

    def _transform_doc_type_to_doc_format(
        self,
        dt_update: DocumentTypeUpdate,
        dt_db: DocumentType,
    ) -> DocumentFormat | None:
        df_name = dt_db.name
        df_uri = self.document_handler._make_path(
            document_type_name=dt_db.name,
            document_format_name=df_name,
            filename=dt_db.doc_uri.split("/")[-1],
        )
        return DocumentFormat(
            name=df_name,
            dt_id=dt_db.id,
            doc_uri=df_uri,
            state=DocumentFormatState.IN_TRAINING,
            fields=[
                DocumentFormatField(
                    display_name=field.display_name,
                    mapped_to=field.id,
                )
                for field in dt_update.fields.properties
            ],
            tables=[
                DocumentFormatTable(
                    id=table.id,
                    columns=[
                        BaseMappingProperty(
                            display_name=column.display_name,
                            mapped_to=column.id,
                        )
                        for column in table.columns.properties
                    ],
                )
                for table in dt_update.tables
            ],
        )

    @staticmethod
    def _convert_filter_time_to_start_time(
        time_range: TimeRangeFilter,
    ) -> datetime:
        now = datetime.now(TIMEZONE)
        time_deltas = {
            TimeRangeFilter.LAST_24_HOURS: timedelta(days=1),
            TimeRangeFilter.LAST_3_DAYS: timedelta(days=3),
            TimeRangeFilter.LAST_7_DAYS: timedelta(weeks=1),
            TimeRangeFilter.LAST_30_DAYS: timedelta(days=30),
            TimeRangeFilter.LAST_3_MONTHS: timedelta(weeks=13),
            TimeRangeFilter.LAST_6_MONTHS: timedelta(weeks=26),
            TimeRangeFilter.LAST_YEAR: timedelta(days=365),
        }
        delta = time_deltas.get(time_range)
        return now - delta if delta is not None else None

    async def get_all_document_types(
        self,
        q: str = "",
        page: int = 1,
        page_size: int = 10,
    ) -> Page | None:
        n_skip = (page - 1) * page_size

        pipeline = []

        if q:
            # Escape special regex characters in the user input to prevent errors
            safe_search_term = re.escape(q)
            pipeline.append(
                {
                    "$match": {
                        "name": {
                            "$regex": safe_search_term,
                            "$options": "i",  # 'i' for case-insensitive matching
                        },
                    },
                },
            )

        pipeline.extend(
            [
                # Stage 1: Join DocumentType with its DocumentFormats
                {
                    "$lookup": {
                        "from": DocumentFormat.get_collection_name(),
                        "localField": "_id",
                        "foreignField": "dt_id",
                        "as": "formats",
                    },
                },
                # Stage 2: Unwind the formats. Use preserveNullAndEmptyArrays to keep
                # DocumentTypes that might not have any formats yet.
                {
                    "$unwind": {
                        "path": "$formats",
                        "preserveNullAndEmptyArrays": True,
                    },
                },
                # Stage 3: Now join the formats with their DocumentWorkItems.
                # This is a LEFT JOIN to keep formats that have no work items.
                {
                    "$lookup": {
                        "from": DocumentWorkItem.get_collection_name(),
                        "localField": "formats._id",
                        "foreignField": "df_id",
                        "as": "work_items",
                    },
                },
                # Stage 4: Unwind the work items. A DocumentType with no work items
                # will still be preserved from the previous stages.
                {
                    "$unwind": {
                        "path": "$work_items",
                        "preserveNullAndEmptyArrays": True,
                    },
                },
                # Stage 5: THE KEY STAGE - Group by the DocumentType
                # This is where all the counting happens correctly.
                {
                    "$group": {
                        # Group by DocumentType's ID and Name
                        "_id": {"id": "$_id", "name": "$name", "created_at": "$created_at"},
                        "total": {
                            "$sum": {
                                "$cond": [{"$ifNull": ["$work_items._id", False]}, 1, 0],
                            },
                        },
                        "total_need_training": {
                            "$sum": {
                                "$cond": [{"$eq": ["$work_items.state", DocWorkItemState.NEEDS_TRAINING]}, 1, 0],
                            },
                        },
                        "total_failed": {
                            "$sum": {
                                "$cond": [{"$eq": ["$work_items.state", DocWorkItemState.FAILED]}, 1, 0],
                            },
                        },
                    },
                },
                # Stage 6: Sort the Document Types themselves (e.g., by created_at)
                {
                    "$sort": {"_id.created_at": DESCENDING},
                },
                # Stage 7: Facet for metadata (total DT count) and paginated data
                {
                    "$facet": {
                        "metadata": [{"$count": "total"}],
                        "data": [
                            {"$skip": n_skip},
                            {"$limit": page_size},
                            # Project to the final, flat structure you want
                            {
                                "$project": {
                                    "_id": "$_id.id",
                                    "dt_name": "$_id.name",
                                    "total": "$total",
                                    "total_need_training": "$total_need_training",
                                    "total_failed": "$total_failed",
                                },
                            },
                        ],
                    },
                },
            ],
        )
        result = await DocumentType.aggregate(pipeline).to_list()
        if not result or not result[0]["data"]:
            return Page()
        total_items = result[0]["metadata"][0]["total"]
        dashboard_items = [DocumentTypeDashboardItem(**item) for item in result[0]["data"]]
        total_pages = (total_items + page_size - 1) // page_size or 1
        return Page(
            items=dashboard_items,
            metadata=PaginatedMetadata(
                page=min(page, total_pages),
                page_size=page_size,
                total_items=total_items,
                total_pages=total_pages,
            ),
        )

    async def get_work_items_by_dt_id(
        self,
        dt_id: str,
        q: str = "",
        states: list[DocWorkItemState] | None = None,
        time_range: TimeRangeFilter | None = None,
        page: int = 1,
        page_size: int = 10,
    ) -> Page | None:
        dt_db = await DocumentType.find_one(DocumentType.id == dt_id)
        if not dt_db:
            self.logger.error(
                'event=retrieving-document-work-items-by-dt-id-failed dt_id=%s message="Not existing document type."',
                dt_id,
            )
            return None

        n_skip = (page - 1) * page_size

        dwi_match_conditions = {
            "$expr": {"$eq": ["$df_id", "$$df_id_var"]},
        }

        if states:
            dwi_match_conditions["state"] = {"$in": states}

        if time_range:
            dwi_match_conditions["created_at"] = {
                "$gte": self._convert_filter_time_to_start_time(time_range=time_range),
            }

        pipeline = [
            {"$match": {"dt_id": dt_id}},
            {
                "$lookup": {
                    "from": DocumentWorkItem.get_collection_name(),
                    "let": {"df_id_var": "$_id"},
                    "pipeline": [
                        {"$match": dwi_match_conditions},
                        *(
                            []
                            if not q
                            else [
                                {"$addFields": {"_filename": {"$last": {"$split": ["$doc_uri", "/"]}}}},
                                {"$match": {"_filename": {"$regex": re.escape(q), "$options": "i"}}},
                                {"$project": {"_filename": 0}},
                            ]
                        ),
                    ],
                    "as": "work_item_docs",
                },
            },
            {"$unwind": "$work_item_docs"},
            {
                "$replaceRoot": {
                    "newRoot": {
                        "$mergeObjects": ["$work_item_docs", {"df_name": "$name"}],
                    },
                },
            },
            {
                "$lookup": {
                    "from": DocumentContent.get_collection_name(),
                    "let": {"work_item_id": "$_id"},
                    "pipeline": [
                        {
                            "$match": {
                                "$expr": {"$eq": ["$dwi_id", "$$work_item_id"]},
                                "state": "EXTRACTED",
                            },
                        },
                    ],
                    "as": "content_docs",
                },
            },
            {
                "$unwind": {
                    "path": "$content_docs",
                    "preserveNullAndEmptyArrays": True,
                },
            },
            {"$sort": {"created_at": DESCENDING}},
            {
                "$facet": {
                    "metadata": [
                        {"$count": "total"},
                    ],
                    "data": [
                        {"$skip": n_skip},
                        {"$limit": page_size},
                        {
                            "$replaceRoot": {
                                "newRoot": {
                                    "$mergeObjects": [
                                        {
                                            "_id": "$_id",
                                            "stage": "$stage",
                                            "state": "$state",
                                            "df_name": "$df_name",
                                            "doc_name": {
                                                "$last": {"$split": ["$doc_uri", "/"]},
                                            },
                                            "created_at": "$created_at",
                                            "last_run": "$last_run",
                                        },
                                        "$content_docs.extracted_content.fields",
                                    ],
                                },
                            },
                        },
                    ],
                },
            },
        ]

        # Execute the entire pipeline in a single database call
        result_cursor = DocumentFormat.aggregate(pipeline)
        aggregation_result = await result_cursor.to_list(length=1)
        if not aggregation_result or not aggregation_result[0]["metadata"]:
            return Page(
                dt_name=dt_db.name,
                items=[],
                column_names={column_id: DEFAULT_COLUMN_NAMES[i] for i, column_id in enumerate(DEFAULT_COLUMN_IDS)},
            )

        result_payload = aggregation_result[0]
        total_items = result_payload["metadata"][0]["total"]
        items = [DocumentTypeDashboardWorkItem(**doc).model_dump() for doc in result_payload["data"]]

        fields_ids = [field.id for field in dt_db.fields.properties]
        fields_names = [field.display_name for field in dt_db.fields.properties]

        column_ids = [*DEFAULT_COLUMN_IDS, *fields_ids]
        column_names = [*DEFAULT_COLUMN_NAMES, *fields_names]

        # Fake render empty string for fields/columns not extracted
        for item in items:
            missing_fields = set(fields_ids) - set(item)
            item.update(dict.fromkeys(missing_fields, ""))

        total_pages = (total_items + page_size - 1) // page_size or 1
        return Page(
            dt_name=dt_db.name,
            items=items,
            column_names={column_id: column_names[i] for i, column_id in enumerate(column_ids)},
            metadata=PaginatedMetadata(
                page=min(page, total_pages),
                page_size=page_size,
                total_items=total_items,
                total_pages=total_pages,
            ),
        )

    async def get_df_training_by_dt_id(
        self,
        dt_id: str,
        q: str = "",
        states: list[DocWorkItemState] | None = None,
        time_range: TimeRangeFilter | None = None,
        page: int = 1,
        page_size: int = 10,
    ) -> Page | None:
        dt_db = await DocumentType.find_one(DocumentType.id == dt_id)
        if not dt_db:
            self.logger.error(
                'event=retrieving-document-format-training-by-dt-id-failed dt_id=%s message="Not existing document type".',
                dt_id,
            )
            return None

        n_skip = (page - 1) * page_size

        dwi_match_conditions = {
            "$expr": {"$eq": ["$df_id", "$$df_id_var"]},
        }

        if states:
            dwi_match_conditions["state"] = {"$in": states}

        if time_range:
            dwi_match_conditions["created_at"] = {
                "$gte": self._convert_filter_time_to_start_time(time_range=time_range),
            }

        pipeline = [
            {"$match": {"dt_id": dt_id}},
            {
                "$lookup": {
                    "from": DocumentWorkItem.get_collection_name(),
                    "let": {"df_id_var": "$_id"},
                    "pipeline": [
                        {"$match": dwi_match_conditions},
                        *(
                            []
                            if not q
                            else [
                                {"$addFields": {"_filename": {"$last": {"$split": ["$doc_uri", "/"]}}}},
                                {"$match": {"_filename": {"$regex": re.escape(q), "$options": "i"}}},
                                {"$project": {"_filename": 0}},
                            ]
                        ),
                    ],
                    "as": "work_item_docs",
                },
            },
            {
                "$unwind": {
                    "path": "$work_item_docs",
                    "preserveNullAndEmptyArrays": True,
                },
            },
            {
                "$replaceRoot": {
                    "newRoot": {
                        "$mergeObjects": [
                            "$work_item_docs",
                            {
                                "df_name": "$name",
                                "df_state": "$state",
                            },
                        ],
                    },
                },
            },
            {"$match": {"_id": {"$ne": None}}},
            {"$sort": {"last_run": DESCENDING}},
            {
                "$facet": {
                    "metadata": [{"$count": "total"}],
                    "data": [
                        {"$skip": n_skip},
                        {"$limit": page_size},
                        {
                            "$replaceRoot": {
                                "newRoot": {
                                    "$mergeObjects": [
                                        {
                                            "_id": "$_id",
                                            "doc_name": {
                                                "$last": {"$split": ["$doc_uri", "/"]},
                                            },
                                            "df_id": "$df_id",
                                            "df_name": "$df_name",
                                            "training_status": "$df_state",
                                            "stage": "$stage",
                                            "state": "$state",
                                            "created_at": "$created_at",
                                            "last_run": "$last_run",
                                        },
                                    ],
                                },
                            },
                        },
                    ],
                },
            },
        ]
        result_cursor = DocumentFormat.aggregate(pipeline)
        aggregation_result = await result_cursor.to_list(length=1)
        column_ids = list(DocumentTypeDFTrainingItem.model_fields.keys())
        column_names = [
            "ID",
            "Document Name",
            "Format ID",
            "Format",
            "Training Status",
            "Stage",
            "State",
            "Date Added",
            "Last Run",
        ]

        if not aggregation_result or not aggregation_result[0]["metadata"]:
            return Page(
                dt_name=dt_db.name,
                items=[],
                column_names={column_id: column_names[i] for i, column_id in enumerate(column_ids)},
            )

        result_payload = aggregation_result[0]
        total_items = result_payload["metadata"][0]["total"]
        items = [DocumentTypeDFTrainingItem(**doc).model_dump() for doc in result_payload["data"]]
        total_pages = (total_items + page_size - 1) // page_size or 1
        return Page(
            dt_name=dt_db.name,
            items=items,
            column_names={column_id: column_names[i] for i, column_id in enumerate(column_ids)},
            metadata=PaginatedMetadata(
                page=min(page, total_pages),
                page_size=page_size,
                total_items=total_items,
                total_pages=total_pages,
            ),
        )

    async def get_all_names_document_types(self, filter_active: bool = True) -> list[DocumentTypeName] | None:
        try:
            if filter_active:
                pipeline = [
                    {
                        "$lookup": {
                            "from": DocumentFormat.get_collection_name(),
                            "localField": "_id",
                            "foreignField": "dt_id",
                            "as": "document_formats",
                        },
                    },
                    # Match document types that have at least one activated format
                    {
                        "$match": {
                            "document_formats": {
                                "$elemMatch": {
                                    "state": DocumentFormatState.ACTIVATE,
                                },
                            },
                        },
                    },
                    {
                        "$project": {
                            "_id": 1,
                            "name": 1,
                        },
                    },
                ]
                dt_names = await DocumentType.aggregate(pipeline).to_list()
            else:
                pipeline = [
                    {
                        "$project": {
                            "_id": 1,
                            "name": 1,
                        },
                    },
                ]
                dt_names = await DocumentType.aggregate(pipeline).to_list()
            if not dt_names:
                self.logger.warning(
                    'event=get-all-document-type-names-empty message="No document type names found with active formats".',
                )
                return None
            # Convert the aggregation results to DocumentTypeName models
            dt_names = [DocumentTypeName(**dt) for dt in dt_names]
        except (TypeError, AttributeError, ValueError):
            self.logger.exception(
                'event=retrieving-all-document-type-names-failed message="Invalid document type data".',
            )
            return None
        return dt_names

    async def get_df_by_dt_id(
        self,
        dt_id: str,
        q: str = "",
        page: int = 1,
        page_size: int = 10,
    ) -> Page | None:
        dt_db = await DocumentType.find_one(DocumentType.id == dt_id)
        if not dt_db:
            self.logger.error(
                'event=get-document-formats-by-dt-id-failed dt_id=%s message="Not existing document type".',
                dt_id,
            )
            return None
        n_skip = (page - 1) * page_size
        pipeline = [
            {"$match": {"dt_id": dt_id}},
        ]
        if q:
            pipeline.append(
                {
                    "$match": {
                        "name": {
                            "$regex": q,
                            "$options": "i",  # Case-insensitive search
                        },
                    },
                },
            )

        pipeline = [
            *pipeline,
            {
                "$facet": {
                    "items": [  # This sub-pipeline gets the paginated data
                        {"$sort": {"created_at": DESCENDING}},
                        {"$skip": n_skip},
                        {"$limit": page_size},
                        # Optional: Add a $project stage here if you only need specific fields
                        {"$project": {"name": 1, "created_at": 1, "_id": 1, "last_updated": 1, "state": 1}},
                    ],
                    "metadata": [  # This sub-pipeline gets the total count
                        {"$count": "total"},  # The output will be [{"count": N}]
                    ],
                },
            },
        ]
        result_cursor = DocumentFormat.aggregate(pipeline)
        aggregation_result = await result_cursor.to_list(length=1)
        if not aggregation_result or not aggregation_result[0]["metadata"]:
            return Page(
                dt_name=dt_db.name,
                items=[],
                column_names={
                    "id": "ID",
                    "name": "Name",
                    "state": "Status",
                    "created_at": "Date Added",
                    "last_updated": "Last Updated",
                },
            )
        result_payload = aggregation_result[0]
        total_items = result_payload["metadata"][0]["total"]
        items = [DocumentFormatQuery(**doc).model_dump() for doc in result_payload["items"]]
        total_pages = (total_items + page_size - 1) // page_size or 1
        return Page(
            dt_name=dt_db.name,
            items=items,
            column_names={
                "id": "ID",
                "name": "Name",
                "state": "Status",
                "created_at": "Date Added",
                "last_updated": "Last Updated",
            },
            metadata=PaginatedMetadata(
                page=min(page, total_pages),
                page_size=page_size,
                total_items=total_items,
                total_pages=total_pages,
            ),
        )

    async def create_document_type(
        self,
        dt_name: str,
        dt_file: UploadFile,
    ) -> dict | None:
        self.logger.debug(
            "event=starting-create-new-document-type file_name=%s",
            dt_file.filename,
        )
        object_path = await self.document_handler.upload_document(
            file=dt_file,
            document_type_name=dt_name,
            original_filename=dt_file.filename,
        )
        if object_path is None:
            self.logger.error(
                "event=document-upload-failed file_name=%s document_type=%s",
                dt_file.filename,
                dt_name,
            )
            return None
        presigned_url = await self.document_handler.create_presigned_urls(
            object_names=[object_path],
            expiration=settings.PRESIGN_URL_EXPIRATION,
            response_content_type=dt_file.content_type,
            inline=True,
        )
        # TODO: handle when failed to create presigned_url
        new_dt = DocumentType(name=dt_name, doc_uri=object_path)
        await new_dt.insert()

        return {
            "dt_id": new_dt.id,
            "dt_name": new_dt.name,
            "doc_uri": next(iter(presigned_url.values())),
        }

    async def get_document_type_by_id(self, dt_id: str) -> DocumentTypeResponse | None:
        dt_db = await DocumentType.find_one(DocumentType.id == dt_id)
        if dt_db is None:
            self.logger.debug(
                'event=fetch-document-type-by-id-failed dt_id=%s message="Not existing document type".',
                dt_id,
            )
            return None
        doc_type_resp = DocumentTypeResponse.model_validate(dt_db.model_dump())
        df_activate = await DocumentFormat.find_one(
            DocumentFormat.dt_id == doc_type_resp.id,
            DocumentFormat.state == DocumentFormatState.ACTIVATE,
        )
        presigned_url = await self.document_handler.create_presigned_urls(
            object_names=[doc_type_resp.doc_uri],
            expiration=settings.PRESIGN_URL_EXPIRATION,
            inline=True,
        )
        doc_type_resp.doc_uri = next(iter(presigned_url.values()))
        doc_type_resp.is_activate = df_activate is not None
        return doc_type_resp

    async def save_configuration_document_type(
        self,
        dt_id: str,
        dt_update: DocumentTypeUpdateDisplay,
        is_activate: bool = False,
    ) -> dict | str | None:
        dt_db = await DocumentType.find_one(DocumentType.id == dt_id)
        if dt_db is None:
            self.logger.warning(
                'event=save-configuration-document-type-failed dt_id=%s message="Not existing document type".',
                dt_id,
            )
            return None
        self.logger.debug(
            "event=starting-save-configuration-document-type dt_id=%s",
            dt_id,
        )
        dt_update = DocumentTypeUpdate.model_validate(dt_update.model_dump())
        dt_update_data = dt_update.model_dump()
        dt_update_data["last_updated"] = datetime.now(TIMEZONE)

        existed_dt_data = dt_db.model_dump()
        existed_dt_data.update(dt_update_data)
        updated_dt = DocumentType.model_validate(existed_dt_data)
        # TODO: handle update document content when update document type
        if dt_update.auto_mapping:
            document_format = self._transform_doc_type_to_doc_format(
                dt_update=dt_update,
                dt_db=dt_db,
            )
            df_db = await DocumentFormat.find_one(
                DocumentFormat.doc_uri == document_format.doc_uri,
            )
            if df_db:
                self.logger.warning(
                    "event=auto-mapping-document-format "
                    'message="Document format df_id=%s df_name=%s existed. Start updating ...".',
                    document_format.id,
                    document_format.name,
                )
                # Update data for Document Format
                update_df_data = document_format.model_dump()
                update_df_data["last_updated"] = datetime.now(TIMEZONE)
                update_df_data.pop("id")
                await df_db.update({"$set": update_df_data})
            else:
                is_df_coppied = await self.document_handler.copy_document(
                    source_object_path=updated_dt.doc_uri,
                    destination_object_path=document_format.doc_uri,
                )
                if not is_df_coppied:
                    return None
                df_db = await document_format.insert()

            source_df_path = Path(df_db.doc_uri)
            dwi_doc_uri = source_df_path.parent / DEFAULT_WORK_ITEMS_FOLDER / source_df_path.name
            dwi_db = await DocumentWorkItem.find_one(DocumentWorkItem.doc_uri == str(dwi_doc_uri))

            if dwi_db is None:
                doc_work_item = DocumentWorkItem(
                    df_id=df_db.id,
                    doc_uri=str(dwi_doc_uri),
                )
                is_dwi_coppied = await self.document_handler.copy_document(
                    source_object_path=df_db.doc_uri,
                    destination_object_path=str(dwi_doc_uri),
                )
                if not is_dwi_coppied:
                    return None
                await doc_work_item.insert()
            else:
                await dwi_db.set({"stage": DocWorkItemStage.TRAINING, "state": DocWorkItemState.COMPLETED})

        await updated_dt.save()
        if is_activate:
            source_df_path = Path(df_db.doc_uri)
            dwi_doc_uri = source_df_path.parent / DEFAULT_WORK_ITEMS_FOLDER / source_df_path.name
            dwi_db = await DocumentWorkItem.find_one(DocumentWorkItem.doc_uri == str(dwi_doc_uri))
            return {
                "dt_name": updated_dt.name,
                "df_name": df_db.name,
                "doc_uri": dwi_db.doc_uri,
                "dwi_id": dwi_db.id,
            }
        return updated_dt.id

    async def delete_document_type_by_id(self, dt_id: str) -> bool:
        dt_db = await DocumentType.find_one(DocumentType.id == dt_id)
        if dt_db is None:
            self.logger.debug(
                'event=delete-document-type-by-id-failed dt_id=%s message="Not existing document type".',
                dt_id,
            )
            return None

        doc_formats = await DocumentFormat.find(
            DocumentFormat.dt_id == dt_id,
            projection_model=DocumentFormatDeleteQuery,
        ).to_list()

        async with asyncio.TaskGroup() as task_group:
            tasks = [
                task_group.create_task(
                    df_handler.delete_document_format_by_id(df_id=df.id),
                )
                for df in doc_formats
            ]
        results = [task.result() for task in tasks]
        if False in results:
            return False

        await dt_db.delete()
        await self.document_handler.delete_document(
            object_path=dt_db.doc_uri,
        )
        return True

    async def activate_document_type_by_id(
        self,
        dt_id: str,
        dt_update: DocumentTypeUpdateDisplay,
        background_tasks: BackgroundTasks,
    ) -> bool:
        training_data = await self.save_configuration_document_type(
            dt_id=dt_id,
            dt_update=dt_update,
            is_activate=True,
        )
        if not isinstance(training_data, dict):
            self.logger.error(
                "event=activating-document-type-by-id-failed "
                "dt_id=%s "
                'message="Failed to save configuration for document type and auto mapping document format".',
                dt_id,
            )
            return False

        extraction_agent = await ExtractionAgent.create()

        await extraction_agent.update_status_document_work_item(
            dwi_id=training_data["dwi_id"],
            stage=DocWorkItemStage.EXTRACTION,
            state=DocWorkItemState.IN_PROCESS,
        )
        await extraction_agent.put_event_message(
            dt_id,
            message={
                "dwi": training_data["dwi_id"],
                "state": DocWorkItemState.IN_PROCESS.value,
            },
        )

        background_tasks.add_task(
            extraction_agent.run,
            dt_name=training_data["dt_name"],
            df_name=training_data["df_name"],
            doc_uri=training_data["doc_uri"],
        )
        return True

    async def is_document_type_exists(self, dt_name: str) -> bool:
        """Check if document type name already exists."""
        existing_dt = await DocumentType.find_one(
            DocumentType.name
            == {
                "$regex": f"^{re.escape(dt_name)}$",
                "$options": "i",
            },
        )
        if existing_dt:
            self.logger.warning(
                "event=document-type-name-already-exists dt_name=%s",
                dt_name,
            )
            return True
        return False

    async def export_document_type(self, dt_id: str | None = None) -> DocumentTypeExport | None:
        """Export document type by ID or all if no ID provided."""
        dt = await DocumentType.find_one(DocumentType.id == dt_id)
        if dt:
            document_type = dt
            document_formats = await DocumentFormat.find(
                DocumentFormat.dt_id == dt_id,
            ).to_list()

            document_work_items = []
            document_contents = []
            for df in document_formats:
                work_items = await DocumentWorkItem.find(
                    DocumentWorkItem.df_id == df.id,
                ).to_list()
                document_work_items.extend(work_items)

                # Get document contents for each work item
                for wi in work_items:
                    contents = await DocumentContent.find(
                        DocumentContent.dwi_id == wi.id,
                    ).to_list()
                    document_contents.extend(contents)
        else:
            self.logger.warning(
                'event=document-type-not-found message="Document type with ID %s not found"',
                dt_id,
            )
            return None

        return DocumentTypeExport(
            metadata=MetadataExport(),
            document_type=document_type,
            document_formats=document_formats,
            document_work_items=document_work_items,
            document_contents=document_contents,
        )

    async def export_document_type_as_zip(self, dt_id: str | None = None) -> io.BytesIO | None:
        """Export document type as a zip file containing JSON data and all related files."""
        # Get the export data
        export_data = await self.export_document_type(dt_id)
        if not export_data:
            return None

        # Download all files concurrently using TaskGroup
        downloaded_streams = []
        download_items = []
        download_tasks = []
        async with asyncio.TaskGroup() as tg:
            # Collect all URIs that need to be downloaded and create tasks
            if export_data.document_type and export_data.document_type.doc_uri:
                download_items.append(("document_type", export_data.document_type))
                download_tasks.append(
                    tg.create_task(self.document_handler.download_document(object_path=export_data.document_type.doc_uri)),
                )

            for df in export_data.document_formats:
                if df.doc_uri:
                    download_items.append(("format", df))
                    download_tasks.append(tg.create_task(self.document_handler.download_document(object_path=df.doc_uri)))

            for dwi in export_data.document_work_items:
                if dwi.doc_uri:
                    download_items.append(("work_item", dwi))
                    download_tasks.append(tg.create_task(self.document_handler.download_document(object_path=dwi.doc_uri)))

        # Extract results from completed tasks
        downloaded_streams = [task.result() for task in download_tasks]

        # Check for download failures
        for i, (item_type, item) in enumerate(download_items):
            if downloaded_streams[i] is None:
                self.logger.error(
                    ('event=export-document-type-as-zip-failed message="Failed to download %s file" uri="%s"'),
                    item_type,
                    item.doc_uri,
                )
                return None

        # Create zip file in thread pool to avoid blocking event loop
        zip_buffer = await asyncio.to_thread(self._create_zip_file_sync, export_data, download_items, downloaded_streams)

        if zip_buffer:
            zip_buffer.seek(0)

        return zip_buffer

    def _create_zip_file_sync(
        self,
        export_data: DocumentTypeExport,
        download_items: list[tuple[str, object]],
        downloaded_streams: list,
    ) -> io.BytesIO | None:
        """Create zip file synchronously in thread pool."""
        try:
            zip_buffer = io.BytesIO()
            used_filenames = set()
            file_mapping = {}

            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                # Write JSON data
                json_content = export_data.model_dump()
                zip_file.writestr("export_data.json", orjson.dumps(json_content, option=orjson.OPT_INDENT_2).decode("utf-8"))

                # Process all downloaded files
                for (item_type, item), file_stream in zip(download_items, downloaded_streams, strict=False):
                    if file_stream is None:
                        continue

                    filename = Path(item.doc_uri).name
                    base_name = Path(filename).stem
                    extension = Path(filename).suffix

                    # Generate unique filename based on item type
                    if item_type == "document_type":
                        zip_filename = f"files/document_type_{filename}"
                    else:
                        # Find index for format/work_item
                        if item_type == "format":
                            items_list = export_data.document_formats
                            prefix = "format"
                        else:  # work_item
                            items_list = export_data.document_work_items
                            prefix = "workitem"

                        index = items_list.index(item)
                        zip_filename = f"files/{prefix}_{index}_{base_name}{extension}"

                        # Ensure uniqueness
                        counter = 1
                        while zip_filename in used_filenames:
                            zip_filename = f"files/{prefix}_{index}_{base_name}_{counter}{extension}"
                            counter += 1

                    used_filenames.add(zip_filename)
                    file_mapping[item.doc_uri] = zip_filename
                    zip_file.writestr(zip_filename, file_stream.getvalue())

                # Write file mapping
                zip_file.writestr("file_mapping.json", orjson.dumps(file_mapping, option=orjson.OPT_INDENT_2).decode("utf-8"))

        except Exception:
            self.logger.exception('event=export-document-type-as-zip-failed message="Failed to create zip export"')
            return None
        return zip_buffer

    async def import_document_type(self, dt_name: str, file: UploadFile) -> dict | None:
        """Import document type from a ZIP file containing JSON data and files."""
        try:
            is_existed = await self.is_document_type_exists(dt_name)
            if is_existed:
                return None

            content = await file.read()
            zip_buffer = io.BytesIO(content)

            # Step 1: extract metadata (no zip_file returned)
            def extract_zip_metadata() -> tuple[dict, dict] | None:
                with zipfile.ZipFile(zip_buffer, "r") as zip_file:
                    if "export_data.json" not in zip_file.namelist():
                        return None

                    json_content = zip_file.read("export_data.json")
                    data = orjson.loads(json_content.decode("utf-8"))

                    file_mapping = {}
                    if "file_mapping.json" in zip_file.namelist():
                        mapping_content = zip_file.read("file_mapping.json")
                        file_mapping = orjson.loads(mapping_content.decode("utf-8"))

                    return data, file_mapping

            extract_result = await asyncio.to_thread(extract_zip_metadata)
            if extract_result is None:
                self.logger.error(
                    'event=import-document-types-failed message="No export_data.json found in zip file"',
                )
                return None

            data, file_mapping = extract_result

            # Step 2: reopen zip_buffer safely
            zip_buffer.seek(0)
            with zipfile.ZipFile(zip_buffer, "r") as zip_file:
                result = await self._import_from_json(dt_name, data, zip_file, file_mapping)

        except Exception:
            self.logger.exception('event=import-document-types-failed message="Failed to import document types"')
            return None

        return result

    async def _import_from_json(
        self,
        dt_name: str,
        data: dict,
        zip_file: zipfile.ZipFile | None = None,
        file_mapping: dict | None = None,
    ) -> dict | None:
        """Import document type from JSON data, optionally extracting files from zip."""
        if "document_type" not in data:
            self.logger.error('event=import-document-types-failed message="Failed to import document type"')
            return None

        # Import document type
        new_dt = await self._import_document_type(dt_name, data["document_type"], zip_file, file_mapping)
        if not new_dt:
            return None

        # Import document formats and create ID mapping
        df_id_mapping, successful_dfs = await self._import_document_formats(
            data.get("document_formats", []),
            new_dt,
            zip_file,
            file_mapping,
        )

        # Import document work items and create ID mapping
        dwi_id_mapping = await self._import_document_work_items(
            data.get("document_work_items", []),
            df_id_mapping,
            successful_dfs,
            zip_file,
            file_mapping,
        )

        # Import document contents
        await self._import_document_contents(
            data.get("document_contents", []),
            dwi_id_mapping,
        )

        doc_uri = ""
        if new_dt.doc_uri:
            # Detect content type from file extension
            content_type, _ = mimetypes.guess_type(new_dt.doc_uri)
            presigned_url = await self.document_handler.create_presigned_urls(
                object_names=[new_dt.doc_uri],
                expiration=settings.PRESIGN_URL_EXPIRATION,
                response_content_type=content_type,
                inline=True,
            )
            if presigned_url:
                doc_uri = next(iter(presigned_url.values()))

            return {
                "dt_id": new_dt.id,
                "dt_name": new_dt.name,
                "doc_uri": doc_uri,
            }

        return None

    async def _import_document_type(
        self,
        dt_name: str,
        dt_data: dict,
        zip_file: zipfile.ZipFile | None = None,
        file_mapping: dict | None = None,
    ) -> DocumentType | None:
        """Import a single document type."""
        new_dt = DocumentType(
            name=dt_name,
            doc_uri=dt_data.get("doc_uri", ""),
            fields=dt_data.get("fields", {}),
            tables=dt_data.get("tables", []),
            agent_validation=dt_data.get("agent_validation", False),
            auto_mapping=dt_data.get("auto_mapping", False),
        )
        await new_dt.insert()

        # Handle file upload if zip_file and file_mapping are provided
        if zip_file and dt_data.get("doc_uri") and file_mapping:
            success = await self._upload_document_type_file(new_dt, dt_data["doc_uri"], zip_file, file_mapping)
            if not success:
                self.logger.warning(
                    "event=import-document-type-file-upload-failed dt_name=%s original_uri=%s",
                    new_dt.name,
                    dt_data["doc_uri"],
                )

        return new_dt

    async def _upload_document_type_file(
        self,
        new_dt: DocumentType,
        original_uri: str,
        zip_file: zipfile.ZipFile,
        file_mapping: dict,
    ) -> bool:
        """Upload document type file from zip."""
        if original_uri in file_mapping:
            zip_filename = file_mapping[original_uri]
            if zip_filename in zip_file.namelist():
                file_content = zip_file.read(zip_filename)
                original_filename = Path(original_uri).name
                file_obj = UploadFile(
                    filename=original_filename,
                    file=io.BytesIO(file_content),
                )
                new_object_path = await self.document_handler.upload_document(
                    file=file_obj,
                    document_type_name=new_dt.name,
                    original_filename=original_filename,
                )
                if new_object_path:
                    new_dt.doc_uri = new_object_path
                    await new_dt.save()
                    return True
                self.logger.error(
                    "event=import-document-type-file-upload-failed dt_name=%s original_uri=%s",
                    new_dt.name,
                    original_uri,
                )
                return False
        return False

    async def _import_document_formats(
        self,
        df_data_list: list[dict],
        new_dt: DocumentType,
        zip_file: zipfile.ZipFile | None = None,
        file_mapping: dict | None = None,
    ) -> tuple[dict[str, str], dict[str, DocumentFormat]]:
        """Import document formats and return ID mapping and successful formats."""
        df_id_mapping = {}
        successful_dfs = {}

        for df_data in df_data_list:
            try:
                old_df_id = df_data["id"]
                df_data["dt_id"] = new_dt.id

                state_str = df_data.get("state", "IN_TRAINING")
                try:
                    state = DocumentFormatState(state_str)
                except ValueError:
                    state = DocumentFormatState.IN_TRAINING

                new_df = DocumentFormat(
                    name=df_data["name"],
                    dt_id=df_data["dt_id"],
                    doc_uri=df_data.get("doc_uri", ""),
                    fields=df_data.get("fields", []),
                    tables=df_data.get("tables", []),
                    extraction_prompt=df_data.get("extraction_prompt", ""),
                    sample_table_rows=df_data.get("sample_table_rows", ""),
                    state=state,
                )
                await new_df.insert()

                file_upload_success = True
                if zip_file and df_data.get("doc_uri") and file_mapping:
                    file_upload_success = await self._upload_document_format_file(
                        new_df,
                        new_dt,
                        df_data["doc_uri"],
                        zip_file,
                        file_mapping,
                    )

                df_id_mapping[old_df_id] = new_df.id
                if file_upload_success:
                    successful_dfs[old_df_id] = new_df

                self.logger.info(
                    "event=document-format-imported-successfully df_name=%s df_id=%s file_upload_success=%s",
                    new_df.name,
                    new_df.id,
                    file_upload_success,
                )

            except Exception:
                self.logger.exception(
                    "event=import-document-format-failed df_name=%s",
                    df_data.get("name", "unknown"),
                )
                continue

        return df_id_mapping, successful_dfs

    async def _upload_document_format_file(
        self,
        new_df: DocumentFormat,
        new_dt: DocumentType,
        original_uri: str,
        zip_file: zipfile.ZipFile,
        file_mapping: dict,
    ) -> bool:
        """Upload document format file from zip."""
        if original_uri in file_mapping:
            zip_filename = file_mapping[original_uri]
            if zip_filename in zip_file.namelist():
                file_content = zip_file.read(zip_filename)
                original_filename = Path(original_uri).name
                file_obj = UploadFile(
                    filename=original_filename,
                    file=io.BytesIO(file_content),
                )
                parts = original_uri.split("/")
                document_format_name = new_dt.name if parts[2] == parts[3] else new_df.name

                new_object_path = await self.document_handler.upload_document(
                    file=file_obj,
                    document_type_name=new_dt.name,
                    document_format_name=document_format_name,
                    original_filename=original_filename,
                )

                if new_object_path:
                    if parts[2] == parts[3]:
                        new_df.name = new_dt.name
                    new_df.doc_uri = new_object_path
                    await new_df.save()
                    return True

                self.logger.error(
                    "event=import-document-format-file-upload-failed df_name=%s original_uri=%s",
                    new_df.name,
                    original_uri,
                )
                return False
            self.logger.warning(
                "event=import-document-format-file-not-found-in-zip df_name=%s zip_filename=%s",
                new_df.name,
                zip_filename,
            )
        else:
            self.logger.warning(
                "event=import-document-format-file-mapping-not-found df_name=%s original_uri=%s",
                new_df.name,
                original_uri,
            )
        return False

    async def _import_document_work_items(
        self,
        dwi_data_list: list[dict],
        df_id_mapping: dict[str, str],
        successful_dfs: dict[str, DocumentFormat],
        zip_file: zipfile.ZipFile | None = None,
        file_mapping: dict | None = None,
    ) -> dict[str, str]:
        """Import document work items and return ID mapping."""
        dwi_id_mapping = {}

        for dwi_data in dwi_data_list:
            try:
                old_df_id = dwi_data["df_id"]
                old_dwi_id = dwi_data["id"]

                if old_df_id not in df_id_mapping:
                    self.logger.warning(
                        "event=import-document-work-item-skipped reason=document_format_not_found old_df_id=%s",
                        old_df_id,
                    )
                    continue

                dwi_data["df_id"] = df_id_mapping[old_df_id]

                stage_str = dwi_data.get("stage", "Training")
                try:
                    stage = DocWorkItemStage(stage_str)
                except ValueError:
                    stage = DocWorkItemStage.TRAINING

                state_str = dwi_data.get("state", "Completed")
                try:
                    state = DocWorkItemState(state_str)
                except ValueError:
                    state = DocWorkItemState.COMPLETED

                new_dwi = DocumentWorkItem(
                    df_id=dwi_data["df_id"],
                    doc_uri=dwi_data.get("doc_uri", ""),
                    stage=stage,
                    state=state,
                    is_workflow=dwi_data.get("is_workflow", False),
                )
                await new_dwi.insert()

                copy_success = True
                if zip_file and dwi_data.get("doc_uri") and file_mapping and old_df_id in successful_dfs:
                    copy_success = await self._copy_document_work_item_file(
                        new_dwi,
                        dwi_data["doc_uri"],
                        successful_dfs[old_df_id],
                        zip_file,
                        file_mapping,
                    )

                dwi_id_mapping[old_dwi_id] = new_dwi.id

                self.logger.info(
                    "event=document-work-item-imported-successfully dwi_id=%s df_id=%s copy_success=%s",
                    new_dwi.id,
                    new_dwi.df_id,
                    copy_success,
                )

            except Exception:
                self.logger.exception(
                    "event=import-document-work-item-failed df_id=%s",
                    dwi_data.get("df_id", "unknown"),
                )
                continue

        return dwi_id_mapping

    async def _copy_document_work_item_file(
        self,
        new_dwi: DocumentWorkItem,
        original_uri: str,
        corresponding_df: DocumentFormat,
        zip_file: zipfile.ZipFile,
        file_mapping: dict,
    ) -> bool:
        """Copy document work item file from corresponding document format."""
        if original_uri in file_mapping:
            zip_filename = file_mapping[original_uri]
            if zip_filename in zip_file.namelist():
                if corresponding_df.doc_uri:
                    source_df_path = Path(corresponding_df.doc_uri)
                    dwi_doc_uri = source_df_path.parent / DEFAULT_WORK_ITEMS_FOLDER / source_df_path.name

                    is_copied = await self.document_handler.copy_document(
                        source_object_path=corresponding_df.doc_uri,
                        destination_object_path=str(dwi_doc_uri),
                    )
                    if is_copied:
                        new_dwi.doc_uri = str(dwi_doc_uri)
                        await new_dwi.save()
                        return True
                    self.logger.error(
                        "event=import-document-work-item-copy-failed dwi_id=%s source=%s destination=%s",
                        new_dwi.id,
                        corresponding_df.doc_uri,
                        str(dwi_doc_uri),
                    )
                    return False
                self.logger.warning(
                    "event=import-document-work-item-copy-skipped dwi_id=%s reason=document_format_has_no_doc_uri",
                    new_dwi.id,
                )
                return False
            self.logger.warning(
                "event=import-document-work-item-file-not-found-in-zip dwi_id=%s zip_filename=%s",
                new_dwi.id,
                zip_filename,
            )
            return False
        self.logger.warning(
            "event=import-document-work-item-file-mapping-not-found dwi_id=%s original_uri=%s",
            new_dwi.id,
            original_uri,
        )

        return False

    async def _import_document_contents(
        self,
        dc_data_list: list[dict],
        dwi_id_mapping: dict[str, str],
    ) -> None:
        """Import document contents."""
        for dc_data in dc_data_list:
            try:
                old_dwi_id = dc_data["dwi_id"]

                if old_dwi_id not in dwi_id_mapping:
                    self.logger.warning(
                        "event=import-document-content-skipped reason=document_work_item_not_found old_dwi_id=%s",
                        old_dwi_id,
                    )
                    continue

                dc_data["dwi_id"] = dwi_id_mapping[old_dwi_id]

                state_str = dc_data.get("state", "IN_PROCESS")
                try:
                    state = DocumentContentState(state_str)
                except ValueError:
                    state = DocumentContentState.IN_PROCESS

                new_dc = DocumentContent(
                    dwi_id=dc_data["dwi_id"],
                    state=state,
                    extracted_content=dc_data.get("extracted_content", {}),
                    transformed_content=dc_data.get("transformed_content", {}),
                    computed_content=dc_data.get("computed_content", {}),
                    metadata=dc_data.get("metadata", {}),
                )
                await new_dc.insert()

                self.logger.info(
                    "event=document-content-imported-successfully dc_id=%s dwi_id=%s",
                    new_dc.id,
                    new_dc.dwi_id,
                )

            except Exception:
                self.logger.exception(
                    "event=import-document-content-failed dwi_id=%s",
                    dc_data.get("dwi_id", "unknown"),
                )
                continue

    async def get_all_names_document_formats_by_dt_id(self, dt_id: str) -> list[DocumentFormatDasboardQuery]:
        """
        Get all document format names and IDs for a given document type ID.
        """
        pipeline = [
            {"$match": {"dt_id": dt_id}},
            {
                "$project": {
                    "_id": 1,
                    "name": 1,
                },
            },
        ]
        df_names = await DocumentFormat.aggregate(pipeline).to_list()
        if not df_names:
            self.logger.warning(
                'event=get-all-document-format-names-empty dt_id=%s message="No document format names found".',
                dt_id,
            )
            return []
        # Convert the aggregation results to DocumentFormatDasboardQuery models
        return [DocumentFormatDasboardQuery(**df) for df in df_names]
