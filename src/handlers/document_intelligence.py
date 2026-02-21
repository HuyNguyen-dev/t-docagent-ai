from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import orjson
from fastapi import UploadFile
from PIL import Image
from pydantic import BaseModel

from agents.training_agent.agent import ExtractionAgent
from config import settings
from handlers.document import DocumentHandler
from handlers.llm_configuration import LLMConfigurationHandler
from helpers.llm.vision import VisionLLMService
from models.document_format import DocumentFormat
from models.document_type import DocumentType
from models.document_work_item import DocumentWorkItem
from schemas.document_format import (
    BaseMappingProperty,
    DocumentFormatField,
    DocumentFormatResponse,
    DocumentFormatTable,
)
from schemas.document_intelligence import AnnotationConfig, DocumentFormatGenSchema, DocumentGenSchema
from schemas.document_type import (
    BaseProperty,
    DocumentTypeFields,
    DocumentTypeResponse,
    DocumentTypeTable,
)
from settings.prompts.document_intelligence import (
    DISCOVER_ANNOTATIONS_SYSTEM_PROMPT,
    GENERATE_DOCUMENT_FORMAT_SYSTEM_PROMPT,
)
from utils.constants import DEFAULT_EXTRACTION_FILE_FOLDER, DEFAULT_WORK_ITEMS_FOLDER, KEY_SCHEMA_DISCOVERY_CONFIG, TIMEZONE
from utils.enums import DocumentFormatState, DocWorkItemState
from utils.image import convert_pil_to_base64, validate_zip_file
from utils.logger.custom_logging import LoggerMixin

llm_handler = LLMConfigurationHandler()


class DocumentIntelligenceHandler(LoggerMixin):
    def __init__(self, vision_service: VisionLLMService | None = None) -> None:
        self.document_handler = DocumentHandler()
        self.vision_service = vision_service
        super().__init__()

    @classmethod
    async def create(cls) -> "DocumentIntelligenceHandler":
        owner_config = await llm_handler.get_owner_llm_config()
        if owner_config is None:
            return cls()

        vision_service = VisionLLMService(
            **llm_handler.get_llm_config_by_key(
                owner_config=owner_config,
                key=KEY_SCHEMA_DISCOVERY_CONFIG,
            ),
        )
        return cls(vision_service)

    async def refresh_vision_service(self) -> None:
        owner_config = await llm_handler.get_owner_llm_config()
        if owner_config is None:
            return

        self.vision_service = VisionLLMService(
            **llm_handler.get_llm_config_by_key(
                owner_config=owner_config,
                key=KEY_SCHEMA_DISCOVERY_CONFIG,
            ),
        )
        return

    async def _get_vision_response(
        self,
        system_message: str,
        images: list[Image.Image],
        output_parser: BaseModel,
        **kwargs: any,
    ) -> BaseModel | None:
        """Get response from vision model.

        Args:
            vision_service: Vision service instance
            document_type: Document type configuration
            images: List of document images
            annotation_config: User annotated prompt

        Returns:
            Parsed minimal document format or None if error occurs
        """
        # Convert all images to base64 with PNG format for better quality
        base64_images = [convert_pil_to_base64(img, img_format="PNG") for img in images]

        if len(images) != len(base64_images):
            self.logger.error(
                'event=image-count-mismatch message="Number of images (%d) must match number of base64 strings (%d)"',
                len(images),
                len(base64_images),
            )
            return None

        if self.vision_service is None or self.vision_service.llm is None:
            return None

        return await self.vision_service.acall(
            system_message=system_message,
            base64_images=base64_images,
            output_parser=output_parser,
            is_pdf=False,
            **kwargs,
        )

    def _add_system_metadata(self, response_dict: dict[str, Any]) -> dict[str, Any] | None:
        """Add system-generated metadata to the response dictionary.

        Args:
            response_dict: Response dictionary to update

        Returns:
            Updated response dictionary with system metadata or None if error occurs
        """
        doc_id = f"df-{uuid4()!s}"
        current_time = datetime.now(TIMEZONE)
        response_dict.update(
            {
                "_id": doc_id,
                "id": doc_id,
                "created_at": current_time,
                "created_by": "system",
                "last_updated": current_time,
            },
        )
        return response_dict

    async def suggest_document_schema(
        self,
        dt_id: str,
        zip_file: UploadFile,
        config: AnnotationConfig,
    ) -> DocumentTypeResponse | None:
        """
        Process a list of images using the LLM model and return document schemas.
        """

        self.logger.info(
            'event=process-document-mapping message="Processing discover annotations request for file: %s"',
            zip_file.filename,
        )

        # Validate zip file
        is_valid, data_or_msg = await validate_zip_file(zip_file)
        if not is_valid:
            self.logger.debug(
                "event=zip-file-validation file_name=%s is_valid=%s",
                zip_file.filename,
                is_valid,
            )
            return None

        # Validate field config
        if not hasattr(config, "field") or not config.field:
            self.logger.debug(
                'event=missing-field-config message="Config missing field configuration"',
            )
        field_color = getattr(config.field, "color_name", "red")
        field_hex_code = getattr(config.field, "hex_code", "#E63C32")

        # Validate tables config
        if not hasattr(config, "tables") or not config.tables:
            self.logger.debug(
                'event=missing-table-config message="Config missing tables configuration"',
            )
            table_config = orjson.dumps([]).decode("utf-8")
        else:
            table_config = orjson.dumps([table.model_dump() for table in config.tables], option=orjson.OPT_INDENT_2)

        # Call LLM service
        document_schema: DocumentGenSchema = await self._get_vision_response(
            system_message=DISCOVER_ANNOTATIONS_SYSTEM_PROMPT,
            images=data_or_msg,
            output_parser=DocumentGenSchema,
            field_color=field_color,
            field_hex_code=field_hex_code,
            table_config=table_config,
        )
        if document_schema is None:
            return None

        dt_db = await DocumentType.find_one(DocumentType.id == dt_id)
        if dt_db is None:
            return None

        presigned_url = await self.document_handler.create_presigned_urls(
            object_names=[dt_db.doc_uri],
            expiration=settings.PRESIGN_URL_EXPIRATION,
            inline=True,
        )
        dt_db.fields = DocumentTypeFields(
            properties=[
                BaseProperty(
                    display_name=field_name,
                )
                for field_name in document_schema.fields
            ],
            required=[],
        )
        dt_db.tables = [
            DocumentTypeTable(
                display_name=table.table_name,
                description="",
                columns=DocumentTypeFields(
                    properties=[
                        BaseProperty(
                            display_name=column_name,
                        )
                        for column_name in table.columns
                    ],
                    required=[],
                ),
            )
            for table in document_schema.tables
        ]
        dt_db.last_updated = datetime.now(TIMEZONE)
        dt_db.auto_mapping = True
        doc_type_resp = DocumentTypeResponse.model_validate(dt_db.model_dump())
        doc_type_resp.doc_uri = next(iter(presigned_url.values()))
        await dt_db.save()
        return doc_type_resp

    async def generate_document_format_schema(
        self,
        dt_id: str,
        df_id: str,
        zip_file: UploadFile,
        annotation_config: str,
    ) -> DocumentFormatResponse:
        """Process document images and generate format mappings.

        Args:
            dt_id: The ID of the document type
            df_id: The ID of the document format
            zip_file: ZIP file containing images and optional annotations
            annotation_config: User annotated prompt/instructions

        Returns:
            Generated document format with mappings or None if error occurs
        """
        self.logger.info(
            'event=process-document-mapping message="Processing document mapping request for file: %s"',
            zip_file.filename,
        )

        # Validate zip file
        is_valid, data_or_msg = await validate_zip_file(zip_file)
        if not is_valid:
            self.logger.debug(
                "event=zip-file-validation file_name=%s is_valid=%s",
                zip_file.filename,
                is_valid,
            )
            return None

        dt_db = await DocumentType.find_one(DocumentType.id == dt_id)
        if dt_db is None:
            return None

        df_schema: DocumentFormatGenSchema = await self._get_vision_response(
            system_message=GENERATE_DOCUMENT_FORMAT_SYSTEM_PROMPT,
            images=data_or_msg,
            output_parser=DocumentFormatGenSchema,
            annotation_config=annotation_config,
            document_type=dt_db,
        )
        if df_schema is None:
            return None

        df_db = await DocumentFormat.find_one(DocumentFormat.id == df_id)
        if df_db is None:
            return None

        presigned_url = await self.document_handler.create_presigned_urls(
            object_names=[df_db.doc_uri],
            expiration=settings.PRESIGN_URL_EXPIRATION,
            inline=True,
        )

        df_db.fields = [
            DocumentFormatField(
                display_name=field.display_name,
                mapped_to=field.mapped_to,
            )
            for field in df_schema.fields
        ]
        df_db.tables = [
            DocumentFormatTable(
                id=table.id,
                columns=[
                    BaseMappingProperty(
                        display_name=column.display_name,
                        mapped_to=column.mapped_to,
                    )
                    for column in table.columns
                ],
            )
            for table in df_schema.tables
        ]
        df_db.last_updated = datetime.now(TIMEZONE)
        df_db.state = DocumentFormatState.IN_TRAINING
        df_resp = DocumentFormatResponse.model_validate(df_db.model_dump())
        df_resp.doc_uri = next(iter(presigned_url.values()))
        await df_db.save()
        source_df_path = Path(df_db.doc_uri)
        dwi_doc_uri = source_df_path.parent / DEFAULT_WORK_ITEMS_FOLDER / source_df_path.name
        dwi_db = await DocumentWorkItem.find_one(DocumentWorkItem.doc_uri == dwi_doc_uri)
        dwi_db.state = DocWorkItemState.COMPLETED
        await dwi_db.save()
        return df_resp

    async def extract_content_from_file(
        self,
        dt_id: str,
        df_id: str,
        file: UploadFile,
    ) -> dict | None:
        """
        Extract content from an uploaded file using ExtractionAgent.

        Args:
            dt_id: DocumentType ID
            df_id: DocumentFormat ID
            file: FastAPI UploadFile

        Returns:
            Extracted content and metadata, or None if error occurs.
        """
        # Step 1: Upload file to Minio and get URI
        self.logger.info(
            'event=extract-content-from-file message="Uploading file to Minio: %s"',
            file.filename,
        )
        doc_uri = await self.document_handler.upload_document(file=file, document_type_name=DEFAULT_EXTRACTION_FILE_FOLDER)
        if not doc_uri:
            self.logger.error(
                'event=minio-upload-failed message="Failed to upload file to Minio"',
            )
            return None

        # Step 2: Get DocumentType and DocumentFormat by ID
        dt_db = await DocumentType.find_one(DocumentType.id == dt_id)
        df_db = await DocumentFormat.find_one(DocumentFormat.id == df_id)
        if not dt_db or not df_db:
            self.logger.error(
                'event=extract-content-from-file-failed message="Document type or format not found"',
            )
            return None

        if df_db.state != DocumentFormatState.ACTIVATE:
            self.logger.error(
                'event=extract-content-from-file-failed '
                'message="Document Format %s not yet activated"',
                df_db.name,
            )
            return None

        # Step 3: Run extraction using ExtractionAgent
        extraction_agent = await ExtractionAgent.create()
        result = await extraction_agent.run_extraction_transiently(
            dt_name=dt_db.name,
            df_name=df_db.name,
            doc_uri=doc_uri,
        )
        if not result:
            self.logger.error(
                'event=extraction-failed message="ExtractionAgent failed to extract content"',
            )
            return None
        return result

    async def extract_content_from_files(
        self,
        dt_id: str,
        df_id: str,
        files: list[UploadFile],
    ) -> list[dict] | None:
        """
        Extract content from multiple uploaded files using ExtractionAgent batch.

        Returns list aligned with the input order, each item containing:
        - has_error: bool
        - extracted_content: ExtractedContent | None
        - metadata: dict
        - filename: str
        - doc_uri: str
        """
        if not files:
            return []

        # Upload files concurrently
        self.logger.info(
            'event=extract-content-from-files message="Uploading files to Minio" size=%d',
            len(files),
        )
        from asyncio import TaskGroup

        doc_uris: list[str | None] = [None] * len(files)
        filenames: list[str] = [f.filename for f in files]
        async with TaskGroup() as tg:
            for idx, f in enumerate(files):
                async def _upload(i: int, _f: UploadFile) -> None:
                    doc_uris[i] = await self.document_handler.upload_document(
                        file=_f,
                        document_type_name=DEFAULT_EXTRACTION_FILE_FOLDER,
                    )
                tg.create_task(_upload(idx, f))

        # Validate URIs
        if any(uri is None for uri in doc_uris):
            self.logger.error(
                'event=minio-upload-failed message="Failed to upload one or more files to Minio"',
            )
            return None

        # Get DocumentType and DocumentFormat by ID
        dt_db = await DocumentType.find_one(DocumentType.id == dt_id)
        df_db = await DocumentFormat.find_one(DocumentFormat.id == df_id)
        if not dt_db or not df_db:
            self.logger.error(
                'event=extract-content-from-files-failed message="Document type or format not found"',
            )
            return None

        if df_db.state != DocumentFormatState.ACTIVATE:
            self.logger.error(
                'event=extract-content-from-files-failed message="Document Format %s not yet activated"',
                df_db.name,
            )
            return None

        # Run batch extraction
        extraction_agent = await ExtractionAgent.create()
        batch_result = await extraction_agent.run_extraction_batch(
            dt_name=dt_db.name,
            df_name=df_db.name,
            doc_uris=[uri for uri in doc_uris if uri is not None],
        )
        if batch_result is None:
            self.logger.error(
                'event=batch-extraction-failed message="ExtractionAgent batch failed"',
            )
            return None

        # Attach filenames and uris to results (input order preserved)
        enriched: list[dict] = []
        for i, item in enumerate(batch_result):
            enriched.append(
                {
                    **item,
                    "filename": filenames[i],
                    "doc_uri": doc_uris[i],
                },
            )
        return enriched
