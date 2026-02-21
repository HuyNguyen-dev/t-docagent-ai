import asyncio
import io
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import orjson
from beanie.operators import In

from config import settings
from handlers.conversation import ConversationHandler
from handlers.document import DocumentHandler
from models.conversation import Conversation
from models.document_content import DocumentContent
from models.document_format import DocumentFormat
from models.document_type import DocumentType
from models.document_work_item import DocumentWorkItem
from schemas.document_work_item import DetailedDocumentWorkItem, DocumentWorkItemDeleteQuery
from utils.enums import DocumentContentState, WorkItemDownloadType
from utils.logger.custom_logging import LoggerMixin


class DocumentWorkItemHandler(LoggerMixin):
    def __init__(self) -> None:
        super().__init__()
        self.document_handler = DocumentHandler()
        self.conversation_handler = ConversationHandler()

    def _render_metrics_with_units_as_json(self, metrics: dict[str, Any]) -> dict:
        """
        Renders metrics with simple key-value pairs and descriptions in JSON format.
        """
        rendered_data = {}

        if "item" in metrics:
            item_metrics = metrics["item"]
            rendered_data["items"] = {
                "total_items": {
                    "value": item_metrics.get("total_items", 0),
                    "description": "Total number of items processed",
                },
                "success_items": {
                    "value": item_metrics.get("success_items", 0),
                    "description": "Successfully processed items",
                },
                "failed_items": {
                    "value": item_metrics.get("failed_items", 0),
                    "description": "Failed to process items",
                },
                "mapping_accuracy": {
                    "value": f"{float(item_metrics.get('mapping_accuracy', 0)) * 100:.1f}%",
                    "description": "Mapping accuracy score",
                },
                "consistency_accuracy": {
                    "value": f"{float(item_metrics.get('consistency_accuracy', 0)) * 100:.1f}%",
                    "description": "Consistency accuracy score",
                },
                "success_rate": {
                    "value": f"{float(item_metrics.get('success_rate', 0)) * 100:.1f}%",
                    "description": "Overall success rate",
                },
                "quality_pipeline_score": {
                    "value": f"{float(item_metrics.get('quality_pipeline_score', 0)) * 100:.1f}%",
                    "description": "Quality pipeline assessment score",
                },
                "processing_time": {
                    "value": f"{float(item_metrics.get('processing_time', 0)):.3f} seconds",
                    "description": "Total processing time",
                },
            }

        if "field" in metrics:
            field_metrics = metrics["field"]
            rendered_data["fields"] = {
                "total_fields": {
                    "value": field_metrics.get("total_fields", 0),
                    "description": "Total number of fields processed",
                },
                "success_fields": {
                    "value": field_metrics.get("success_fields", 0),
                    "description": "Successfully processed fields",
                },
                "accuracy": {
                    "value": f"{float(field_metrics.get('accuracy', 0)) * 100:.1f}%",
                    "description": "Field processing accuracy",
                },
            }

        if "table" in metrics:
            table_metrics = metrics["table"]
            rendered_data["tables"] = {
                "total_tables": {
                    "value": table_metrics.get("total_tables", 0),
                    "description": "Total number of tables processed",
                },
                "total_extracted_rows": {
                    "value": table_metrics.get("total_extracted_rows", 0),
                    "description": "Total rows extracted from tables",
                },
                "success_extracted_rows": {
                    "value": table_metrics.get("success_extracted_rows", 0),
                    "description": "Successfully extracted rows",
                },
                "structure_accuracy": {
                    "value": f"{float(table_metrics.get('structure_accuracy', 0)) * 100:.1f}%",
                    "description": "Table structure accuracy",
                },
                "table_extract_completeness": {
                    "value": f"{float(table_metrics.get('table_extract_completeness', 0)) * 100:.1f}%",
                    "description": "Table extraction completeness",
                },
            }
        return rendered_data

    async def get_document_work_item_by_id(
        self,
        dwi_id: str,
    ) -> dict | None:
        pipeline = [
            {"$match": {"_id": dwi_id}},
            {
                "$lookup": {
                    "from": DocumentFormat.get_collection_name(),
                    "localField": "df_id",
                    "foreignField": "_id",
                    "as": "format_doc",
                },
            },
            {"$unwind": {"path": "$format_doc", "preserveNullAndEmptyArrays": True}},
            {
                "$lookup": {
                    "from": DocumentContent.get_collection_name(),
                    "let": {"dwi_id_var": "$_id"},
                    "pipeline": [
                        {
                            "$match": {
                                "$expr": {"$eq": ["$dwi_id", "$$dwi_id_var"]},
                                "state": DocumentContentState.EXTRACTED,
                            },
                        },
                    ],
                    "as": "content_doc",
                },
            },
            {"$unwind": {"path": "$content_doc", "preserveNullAndEmptyArrays": True}},
            {
                "$replaceRoot": {
                    "newRoot": {
                        "$mergeObjects": [
                            "$content_doc.extracted_content.fields",
                            {
                                "name": {"$last": {"$split": ["$doc_uri", "/"]}},
                                "doc_uri": "$doc_uri",
                                "format_name": "$format_doc.name",
                                "format_state": "$format_doc.state",
                                "last_run": "$last_run",
                                "first_added": "$created_at",
                                "dt_id": "$format_doc.dt_id",
                                "tables": "$content_doc.extracted_content.tables",
                            },
                        ],
                    },
                },
            },
        ]
        result_cursor = DocumentWorkItem.aggregate(pipeline)
        aggregation_result = await result_cursor.to_list(length=1)

        key_ids = [_id for _id in list(DetailedDocumentWorkItem.model_fields.keys()) if _id not in ["doc_uri", "dt_id"]]
        key_names = ["Name", "Format Name", "Format State", "Last Run", "First Added"]
        if not aggregation_result or not aggregation_result[0]:
            return None

        result_payload = aggregation_result[0]
        item = DetailedDocumentWorkItem(**result_payload).model_dump()

        presigned_url = await self.document_handler.create_presigned_urls(
            object_names=[item["doc_uri"]],
            expiration=settings.PRESIGN_URL_EXPIRATION,
            inline=True,
        )
        item["doc_uri"] = next(iter(presigned_url.values()))
        dt_id = item.pop("dt_id")
        dt_db = await DocumentType.get(dt_id)
        table_ids_mapping = {table.id: table.display_name for table in dt_db.tables}

        key_ids.extend([field.id for field in dt_db.fields.properties])
        key_names.extend([field.display_name for field in dt_db.fields.properties])

        missing_fields = set(key_ids) - set(item)
        item.update(dict.fromkeys(missing_fields, ""))

        # --- Add tables mapping logic here ---
        tables_data = []
        extracted_tables = result_payload.get("tables", [])
        dt_tables = getattr(dt_db, "tables", [])

        for idx, table in enumerate(extracted_tables):
            # Get corresponding table config from DocumentType
            if idx < len(dt_tables):
                dt_table = dt_tables[idx]
                column_keys = {col.id: col.display_name for col in dt_table.columns.properties}
            else:
                column_keys = {}

            table_rows = table.get("items", []) if "items" in table else table.get("columns", [])
            tables_data.append(
                {
                    "name": table_ids_mapping[table["id"]],
                    "items": table_rows,
                    "column_keys": column_keys,
                },
            )
        if "tables" in item:
            item.pop("tables")

        return {
            "item": item,
            "data_keys": dict(zip(key_ids, key_names, strict=False)),
            "tables": tables_data,
        }

    async def download_source_file(self, dwi_id: str) -> tuple[bool, io.BytesIO | None, str | None]:
        """
        Downloads a file from MinIO and returns a BytesIO stream and the original filename.
        """
        doc_work_item_db = await DocumentWorkItem.find_one(DocumentWorkItem.id == dwi_id)
        if not doc_work_item_db:
            self.logger.error(
                "event=document_not_found dwi_id=%s message=No document work item found for this dwi_id",
                dwi_id,
            )
            return False, None, None
        object_path = doc_work_item_db.doc_uri
        file_name = Path(object_path).name

        file_stream = await self.document_handler.download_document(object_path=object_path)
        if file_stream is None:
            self.logger.error(
                "event=download_failed dwi_id=%s message=Download returned None for object_path=%s",
                dwi_id,
                object_path,
            )
            return False, None, None

        self.logger.info(
            "event=download_success dwi_id=%s file_name=%s message=Download source file successfully",
            dwi_id,
            file_name,
        )
        return True, file_stream, file_name

    async def download_extracted_content(self, dwi_id: str) -> tuple[bool, io.BytesIO | None]:
        """
        Downloads extracted content with dwi_id.
        """
        document_content_db = await DocumentContent.find_one(DocumentContent.dwi_id == dwi_id)
        if document_content_db is None:
            self.logger.error(
                "event=document_not_found dwi_id=%s message=No document found for this dwi_id",
                dwi_id,
            )
            return False, None

        extracted_content = document_content_db.extracted_content.model_dump()

        json_data = orjson.dumps(extracted_content, option=orjson.OPT_INDENT_2)
        file_stream = io.BytesIO(json_data)
        return True, file_stream

    async def unified_download_multiple(
        self,
        dwi_ids: list[str],
        download_type: WorkItemDownloadType = WorkItemDownloadType.ALL,
    ) -> tuple[bool, io.BytesIO | None, str | None]:
        """
        Unified download for multiple DWIs as a single ZIP. Returns success, zip stream, filename.
        """
        if not dwi_ids:
            return False, None, None
        normalized = (download_type or WorkItemDownloadType.ALL).value.lower()
        if normalized not in {"source", "content", "logs", "all"}:
            return False, None, None

        async def fetch_for_one(dwi_id: str) -> tuple[str, dict]:
            results: dict[str, tuple] = {}
            if normalized in {"source", "all"}:
                results["source"] = await self.download_source_file(dwi_id)
            if normalized in {"content", "all"}:
                results["content"] = await self.download_extracted_content(dwi_id)
            if normalized in {"logs", "all"}:
                results["logs"] = await self.download_logs(dwi_id)
            return dwi_id, results

        async with asyncio.TaskGroup() as tg:
            tasks = [tg.create_task(fetch_for_one(dwi_id)) for dwi_id in dwi_ids]

        aggregated = [t.result() for t in tasks]

        zip_buffer = io.BytesIO()
        n_written = 0
        with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for dwi_id, results in aggregated:
                base_dir = f"dwi_{dwi_id}"
                if "source" in results:
                    ok, file_stream, file_name = results["source"]  # type: ignore[assignment]
                    if ok and file_stream is not None and file_name:
                        zf.writestr(f"{base_dir}/source/{file_name}", file_stream.getvalue())
                        n_written += 1
                if "content" in results:
                    ok_c, file_stream_c = results["content"]  # type: ignore[assignment]
                    if ok_c and file_stream_c is not None:
                        zf.writestr(f"{base_dir}/extracted_content_{dwi_id}.json", file_stream_c.getvalue())
                        n_written += 1
                if "logs" in results:
                    ok_l, file_stream_l = results["logs"]  # type: ignore[assignment]
                    if ok_l and file_stream_l is not None:
                        zf.writestr(f"{base_dir}/logs_{dwi_id}.json", file_stream_l.getvalue())
                        n_written += 1

        if n_written == 0:
            return False, None, None

        zip_buffer.seek(0)
        file_name = "work_items.zip" if len(dwi_ids) > 1 else f"work_item_{dwi_ids[0]}.zip"
        return True, zip_buffer, file_name

    async def download_logs(self, dwi_id: str) -> tuple[bool, io.BytesIO | None]:
        """
        Downloads extracted logs with dwi_id.
        """
        document_content_db = await DocumentContent.find_one(DocumentContent.dwi_id == dwi_id)
        if document_content_db is None:
            self.logger.error(
                "event=document_not_found dwi_id=%s message=No document found for this dwi_id",
                dwi_id,
            )
            return False, None

        metrics = self._render_metrics_with_units_as_json(document_content_db.metadata["metrics"])

        data = {
            "report_info": {
                "dwi_id": dwi_id,
                "generated_at": datetime.now(UTC).astimezone().isoformat(),
                "report_type": "Document Processing Metadata",
            },
            "logs": document_content_db.metadata["logs"],
            "metrics": metrics,
        }

        json_data = orjson.dumps(data, option=orjson.OPT_INDENT_2)
        file_stream = io.BytesIO(json_data)
        return True, file_stream

    async def delete_document_work_item_by_id(self, dwi_id: str) -> bool:
        """
        Delete a Document Work Item by its ID, including its content and file in MinIO.
        """
        dwi_db = await DocumentWorkItem.get(dwi_id)
        if dwi_db is None:
            self.logger.debug(
                'event=deleting-document-work-item-by-id-failed message="Not found document work item with id: dwi_id=%s"',
                dwi_id,
            )
            return False

        dc_db = await DocumentContent.find_one(DocumentContent.dwi_id == dwi_id)
        if dc_db is not None:
            await dc_db.delete()

        await dwi_db.delete()
        await self.document_handler.delete_document(object_path=dwi_db.doc_uri)
        return True

    async def delete_document_work_items_by_ids(
        self,
        dwi_ids: list[str],
    ) -> bool:
        """
        Delete multiple Document Work Items concurrently.
        Returns a dict mapping dwi_id to True (success) or False (fail).
        """
        work_items = await DocumentWorkItem.find(
            In(DocumentWorkItem.id, dwi_ids),
            projection_model=DocumentWorkItemDeleteQuery,
        ).to_list()

        if not work_items:
            return False

        n_deleted_dc = await DocumentContent.find(In(DocumentContent.dwi_id, dwi_ids)).delete()

        if n_deleted_dc.deleted_count < 0:
            return False

        # Delete Conversation when DWI config in it
        conv_dbs = await Conversation.find(In(Conversation.dwi_id, dwi_ids)).to_list()
        await self.conversation_handler.delete_conversations_by_ids(
            conv_ids=[conv.id for conv in conv_dbs],
        )
        n_deleted_dwi = await DocumentWorkItem.find(In(DocumentWorkItem.id, dwi_ids)).delete()

        if n_deleted_dwi.deleted_count < 0:
            return False

        await self.document_handler.delete_documents(
            object_paths=[work_item.doc_uri for work_item in work_items],
        )
        return True
