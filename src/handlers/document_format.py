import asyncio
import mimetypes
import re
from datetime import datetime
from pathlib import Path

from beanie.operators import In
from fastapi import BackgroundTasks, Form, HTTPException, UploadFile, status

from agents.training_agent.agent import ExtractionAgent
from config import settings
from handlers.conversation import ConversationHandler
from handlers.document import DocumentHandler
from models.conversation import Conversation
from models.document_content import DocumentContent
from models.document_format import DocumentFormat
from models.document_type import DocumentType
from models.document_work_item import DocumentWorkItem
from schemas.document_format import DocumentFormatResponse, DocumentFormatUpdate, DocumentFormatUpdateDisplay
from schemas.document_work_item import DocumentWorkItemDeleteQuery
from utils.constants import DEFAULT_WORK_ITEMS_FOLDER, TIMEZONE
from utils.enums import DocumentFormatState, DocWorkItemStage, DocWorkItemState
from utils.logger.custom_logging import LoggerMixin


class DocumentFormatChecker(LoggerMixin):
    async def __call__(
        self,
        dt_id: str = Form(description="The ID of document type associated new document format"),
        df_name: str = Form(description="The name of new document format"),
    ) -> str | HTTPException:
        """Check if document format name already exists."""
        existing_df = await DocumentFormat.find_one(
            DocumentFormat.name
            == {
                "$regex": f"^{re.escape(df_name)}$",
                "$options": "i",
            },
            DocumentFormat.dt_id == dt_id,
        )
        if existing_df:
            self.logger.warning(
                "event=document-format-name-already-exists df_name=%s",
                df_name,
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Document format with name '{df_name}' already exists",
            )
        return df_name


class DocumentFormatHandler(LoggerMixin):
    def __init__(self) -> None:
        self.document_handler = DocumentHandler()
        self.conversation_handler = ConversationHandler()
        super().__init__()

    def _validate_requirement_fields(
        self,
        df_update: DocumentFormatUpdateDisplay,
        dt_db: DocumentType,
    ) -> tuple[bool, list[str]]:
        errors: list[str] = []
        # Validate fields required
        required_fields = set(dt_db.fields.required)
        provided_fields = {field.mapped_to for field in df_update.fields}

        missing_fields = required_fields - provided_fields
        if missing_fields:
            errors.append(f"Missing required fields: {missing_fields}")

        format_tables_map = {table.id: table for table in df_update.tables}
        for require_table in dt_db.tables:
            # Find the corresponding table schema in the Document Type
            format_table_schema = format_tables_map.get(require_table.id)
            if not format_table_schema:
                errors.append(f"Table '{require_table.id}': Not found in input Document Format. Missing all columns")
                continue
            # Get the set of required column IDs for this table from the Document Type
            required_columns = set(require_table.columns.required)
            provided_columns = {col.mapped_to for col in format_table_schema.columns}

            missing_columns = required_columns - provided_columns
            if missing_columns:
                errors.append(f"Table '{require_table.display_name}': Missing required column: '{missing_columns}'")

        return len(errors) == 0, errors

    async def create_document_format(
        self,
        dt_id: str,
        df_name: str,
        df_file: UploadFile,
    ) -> dict | None:
        self.logger.info(
            "event=starting-creating-new-document-format dt_id=%s df_name=%s",
            dt_id,
            df_name,
        )
        # Validate df_name
        if not df_name.strip():
            self.logger.error(
                'event=creating-new-document-format-failed message="Invalid document format name" df_name=%s',
                df_name,
            )
            return None

        # Check if document type exists
        dt_db = await DocumentType.find_one(DocumentType.id == dt_id)
        if not dt_db:
            self.logger.error(
                'event=creating-new-document-format-failed message="Not existing document type"dt_id=%s',
                dt_id,
            )
            return None

        # Check for duplicata DF name within same dt_id
        df_db = await DocumentFormat.find_one(
            DocumentFormat.name == df_name,
            DocumentFormat.dt_id == dt_id,
        )
        if df_db:
            self.logger.error(
                'event=creating-new-document-format-failed message="Duplicate document format dt_id=%s df_name=%s"',
                dt_id,
                df_name,
            )
            return None

        # Process file (save to storage and get URI)
        object_path = await self.document_handler.upload_document(
            file=df_file,
            document_type_name=dt_db.name,
            document_format_name=df_name,
            original_filename=df_file.filename,
        )
        if object_path is None:
            self.logger.error(
                "event=document-upload-failed file_name=%s document_format_name=%s",
                df_file.filename,
                df_name,
            )
            return None
        presigned_url = await self.document_handler.create_presigned_urls(
            object_names=[object_path],
            expiration=settings.PRESIGN_URL_EXPIRATION,
            response_content_type=df_file.content_type,
            inline=True,
        )
        # Save DF object
        new_df = DocumentFormat(
            name=df_name,
            dt_id=dt_id,
            doc_uri=object_path,
        )
        source_df_path = Path(new_df.doc_uri)
        dwi_doc_uri = source_df_path.parent / DEFAULT_WORK_ITEMS_FOLDER / source_df_path.name

        is_dwi_coppied = await self.document_handler.copy_document(
            source_object_path=new_df.doc_uri,
            destination_object_path=str(dwi_doc_uri),
        )
        if not is_dwi_coppied:
            return None

        doc_work_item = DocumentWorkItem(
            df_id=new_df.id,
            doc_uri=str(dwi_doc_uri),
            state=DocWorkItemState.IN_PROCESS,
        )
        await new_df.insert()
        await doc_work_item.insert()
        return {
            "df_id": new_df.id,
            "df_name": new_df.name,
            "doc_uri": next(iter(presigned_url.values())),
        }

    async def get_document_format_by_id(
        self,
        df_id: str,
    ) -> DocumentFormatResponse | None:
        df_db = await DocumentFormat.find_one(DocumentFormat.id == df_id)
        if df_db is None:
            self.logger.debug(
                'event=retrieving-document-format-by-id-failed message="Not found document format with id: df_id=%s"',
                df_id,
            )
            return None
        doc_format_resp = DocumentFormatResponse.model_validate(df_db.model_dump())
        content_type, _ = mimetypes.guess_type(df_db.doc_uri)
        presigned_url = await self.document_handler.create_presigned_urls(
            object_names=[df_db.doc_uri],
            expiration=settings.PRESIGN_URL_EXPIRATION,
            response_content_type=content_type,
        )
        doc_format_resp.doc_uri = next(iter(presigned_url.values())) 
        #  "Replace http://10.254.1.72:9002/ => Domain https://docagent.tmainnovation.vn/"
        #  create_presigned_urls                     urls[object_name] = url 
        return doc_format_resp

    async def update_document_format_by_id(
        self,
        df_id: str,
        df_update: DocumentFormatUpdateDisplay,
    ) -> tuple[bool, str | None]:
        df_db = await DocumentFormat.find_one(DocumentFormat.id == df_id)
        if df_db is None:
            self.logger.debug(
                "event=updating-document-format-by-id-failed message=Not found document format with id: df_id=%s",
                df_id,
            )
            return False, None

        dt_db = await DocumentType.find_one(DocumentType.id == df_db.dt_id)
        # Validate requirement fields
        is_valid, errors = self._validate_requirement_fields(
            df_update=df_update,
            dt_db=dt_db,
        )

        if not is_valid:
            self.logger.warning(
                'event=updating-document-format-by-id-failed message="Some field requirement has missing" errors=%s',
                errors,
            )
            return False, ". ".join(errors)

        df_update = DocumentFormatUpdate.model_validate(df_update.model_dump())
        update_df_data = df_update.model_dump(exclude_unset=True, exclude_none=True)
        update_df_data["state"] = DocumentFormatState.IN_TRAINING
        update_df_data["last_updated"] = datetime.now(TIMEZONE)
        await df_db.update({"$set": update_df_data})

        # Mark Work Item of Document Format is Training Failed
        source_df_path = Path(df_db.doc_uri)
        dwi_doc_uri = source_df_path.parent / DEFAULT_WORK_ITEMS_FOLDER / source_df_path.name
        dwi_db = await DocumentWorkItem.find_one(DocumentWorkItem.doc_uri == str(dwi_doc_uri))
        if dwi_db is not None:
            await dwi_db.update(
                {
                    "$set": {
                        "stage": DocWorkItemStage.TRAINING,
                        "state": DocWorkItemState.COMPLETED,
                    },
                },
            )
        else:
            self.logger.warning(
                'event=updating-document-format-by-id-failed message="Not found work item of document format" df_id=%s',
                df_id,
            )
            doc_work_item = DocumentWorkItem(
                df_id=df_db.id,
                doc_uri=str(dwi_doc_uri),
                state=DocWorkItemState.COMPLETED,
            )
            is_dwi_coppied = await self.document_handler.copy_document(
                source_object_path=df_db.doc_uri,
                destination_object_path=str(dwi_doc_uri),
            )
            if not is_dwi_coppied:
                return False, None
            await doc_work_item.insert()
        return True, df_db.id

    async def delete_document_format_by_id(
        self,
        df_id: str,
    ) -> bool:
        df_db = await DocumentFormat.find_one(DocumentFormat.id == df_id)
        if df_db is None:
            self.logger.debug(
                'event=deleting-document-format-by-id-failed message="Not found document format with id: df_id=%s"',
                df_id,
            )
            return False
        # Fetch all Work Item by df_id
        work_items = await DocumentWorkItem.find(
            DocumentWorkItem.df_id == df_id,
            projection_model=DocumentWorkItemDeleteQuery,
        ).to_list()

        dwi_ids = [work_item.id for work_item in work_items]
        if dwi_ids:
            n_deleted_dc = await DocumentContent.find(In(DocumentContent.dwi_id, dwi_ids)).delete()
            if n_deleted_dc.deleted_count < 0:
                return False

        # Delete Conversation when DWI config in it
        conv_dbs = await Conversation.find(In(Conversation.dwi_id, dwi_ids)).to_list()
        await self.conversation_handler.delete_conversations_by_ids(
            conv_ids=[conv.id for conv in conv_dbs],
        )

        n_deleted_dwi = await DocumentWorkItem.find(
            In(DocumentWorkItem.id, dwi_ids),
        ).delete()
        if n_deleted_dwi.deleted_count < 0:
            return False
        # Remove all doc_uri run document work item
        await self.document_handler.delete_documents(
            object_paths=[work_item.doc_uri for work_item in work_items],
        )
        await df_db.delete()
        await self.document_handler.delete_document(
            object_path=df_db.doc_uri,
        )
        return True

    async def delete_document_formats_by_ids(
        self,
        df_ids: list[str],
    ) -> dict[str, bool]:
        """
        Delete multiple document formats concurrently.
        Returns a dict mapping df_id to True (success) or False (fail).
        """
        results: dict[str, bool] = {}

        async def delete_one(df_id: str) -> None:
            try:
                result = await self.delete_document_format_by_id(df_id)
                results[df_id] = result
            except Exception:
                self.logger.exception(
                    "event=deleting-multi-document-format-failed df_id=%s",
                    df_id,
                )
                results[df_id] = False

        async with asyncio.TaskGroup() as tg:
            for df_id in df_ids:
                tg.create_task(delete_one(df_id))
        return results

    async def train_document_format_by_id(
        self,
        df_id: str,
        background_tasks: BackgroundTasks,
        df_update: DocumentFormatUpdateDisplay | None = None,
    ) -> bool:
        df_db = await DocumentFormat.find_one(DocumentFormat.id == df_id)
        if df_db is None:
            self.logger.debug(
                'event=fetch-document-format-by-id-failed message="Not found document format with id: df_id=%s"',
                df_id,
            )
            return False
        dt_db = await DocumentType.find_one(DocumentType.id == df_db.dt_id)
        if dt_db is None:
            self.logger.debug(
                'event=fetch-document-type-by-df-id-failed message="Not found document type with id: df_id=%s"',
                df_db.dt_id,
            )
            return False
        source_df_path = Path(df_db.doc_uri)
        dwi_doc_uri = source_df_path.parent / DEFAULT_WORK_ITEMS_FOLDER / source_df_path.name
        dwi_db = await DocumentWorkItem.find_one(DocumentWorkItem.doc_uri == str(dwi_doc_uri))
        if dwi_db is None:
            self.logger.debug(
                'event=fetch-document-work-item-by-df-id-failed message="Not found document work item with id: df_id=%s"',
                df_db.dt_id,
            )
            doc_work_item = DocumentWorkItem(
                df_id=df_db.id,
                doc_uri=str(dwi_doc_uri),
                state=DocWorkItemState.COMPLETED,
            )
            is_dwi_coppied = await self.document_handler.copy_document(
                source_object_path=df_db.doc_uri,
                destination_object_path=str(dwi_doc_uri),
            )
            if not is_dwi_coppied:
                return False
            dwi_db = await doc_work_item.insert()

        if df_update is not None:
            is_updated, msg_data = await self.update_document_format_by_id(
                df_id=df_id,
                df_update=df_update,
            )
            if not is_updated:
                self.logger.error(
                    'event=update-document-format-by-df-id-failed message="%s"',
                    msg_data,
                )
                return False

        extraction_agent = await ExtractionAgent.create()
        await extraction_agent.update_status_document_work_item(
            dwi_id=dwi_db.id,
            stage=DocWorkItemStage.EXTRACTION,
            state=DocWorkItemState.IN_PROCESS,
        )
        await extraction_agent.put_event_message(
            dt_db.id,
            message={
                "dwi": dwi_db.id,
                "state": DocWorkItemState.IN_PROCESS.value,
            },
        )

        background_tasks.add_task(
            extraction_agent.run,
            dt_name=dt_db.name,
            df_name=df_db.name,
            doc_uri=dwi_db.doc_uri,
        )
        return True

    async def change_state_document_format_by_ids(
        self,
        df_ids: list[str],
        state: DocumentFormatState,
        background_tasks: BackgroundTasks,
    ) -> bool:
        n_df_updated = await DocumentFormat.find(
            In(DocumentFormat.id, df_ids),
        ).update_many(
            {"$set": {"state": state}},
        )
        if n_df_updated.modified_count < len(df_ids):
            self.logger.warning(
                'event=change-state-document-format-by-ids-failed message="Some df_ids not updated success"',
            )
        if state == DocumentFormatState.RETRAIN:
            results = [True]
            try:
                async with asyncio.TaskGroup() as task_group:
                    _ = [
                        task_group.create_task(
                            self.train_document_format_by_id(
                                df_id=df_id,
                                background_tasks=background_tasks,
                            ),
                        )
                        for df_id in df_ids
                    ]
            except* Exception as eg:
                # Handle ExceptionGroup from TaskGroup or other exceptions
                for exc in eg.exceptions if isinstance(eg, BaseExceptionGroup) else [eg]:
                    self.logger.exception(
                        "event=change-state-document-format-by-ids-failed "
                        'error="%s" message="Failed to change state document formats to RETRAIN"',
                        str(exc),
                    )
                results.append(False)
            return all(results)
        return True

    async def is_document_format_exists(self, dt_id: str, df_name: str) -> bool:
        """Check if document format name already exists."""
        existing_df = await DocumentFormat.find_one(
            DocumentFormat.name
            == {
                "$regex": f"^{re.escape(df_name)}$",
                "$options": "i",
            },
            DocumentFormat.dt_id == dt_id,
        )
        if existing_df:
            self.logger.warning(
                "event=document-format-name-already-exists df_name=%s",
                df_name,
            )
            return True
        return False
