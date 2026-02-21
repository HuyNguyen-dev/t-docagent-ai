import base64
import datetime
import io
import mimetypes
from pathlib import Path

import aiofiles
from fastapi import UploadFile
from miniopy_async.commonconfig import CopySource
from miniopy_async.deleteobjects import DeleteObject
from miniopy_async.error import S3Error

from config import settings
from initializer import minio_client
from utils.constants import DEFAULT_BUCKET, DEFAULT_INTAKE_FOLDER, DEFAULT_WORKSPACE_ID
from utils.logger.custom_logging import LoggerMixin


class DocumentHandler(LoggerMixin):
    """
    Handler for interacting with MinIO, supporting structured document ingestion and management
    matching the Document Intelligence Multimodal Extraction Service S3 folder structure.
    """

    def _make_path(
        self,
        intake_folder: str = DEFAULT_INTAKE_FOLDER,
        workspace_id: str = DEFAULT_WORKSPACE_ID,
        document_type_name: str | None = None,
        document_format_name: str | None = None,
        filename: str = "",
    ) -> str:
        path = f"{intake_folder}/{workspace_id}/"
        if document_type_name:
            path += f"{document_type_name}/"
            if document_format_name:
                path += f"{document_format_name}/"
        if filename:
            path += filename
        return path

    async def upload_document(
        self,
        file: UploadFile | None = None,
        file_path: Path | None = None,
        bucket: str = DEFAULT_BUCKET,
        intake_folder: str = DEFAULT_INTAKE_FOLDER,
        workspace_id: str = DEFAULT_WORKSPACE_ID,
        document_type_name: str | None = None,
        document_format_name: str | None = None,
        original_filename: str | None = None,
    ) -> str | None:
        """
        Upload a document to MinIO using the structured path.
        Ensures the bucket exists before uploading.
        Uses the original filename if provided, otherwise uses the file_path name.

        Args:
            file: The file to upload
            bucket: The MinIO bucket name
            intake_folder: The intake folder path
            workspace_id: The workspace identifier
            document_type_name: Optional document type
            document_format_name: Optional document format
            original_filename: Optional original filename to use

        Returns:
            str: object path of the file upload on minio
        """
        try:
            # Read file
            if file is None and file_path is None:
                self.logger.error(
                    'event=upload-file-failed message=Failed to upload file to bucket %serror="Missing input file or file_path"',
                    bucket,
                )
            if isinstance(file_path, Path):
                async with aiofiles.open(file_path, mode="rb") as f:
                    file_content = await f.read()
                content_type, _ = mimetypes.guess_type(file_path)
                filename = file_path.name
            else:
                file_content = await file.read()
                content_type = file.content_type
                filename = file.filename

            # Ensure bucket exists
            is_bucket_existed = await minio_client.bucket_exists(bucket)
            if not is_bucket_existed:
                await minio_client.make_bucket(bucket)

            # Upload bytes to MinIO
            filename = original_filename or filename
            object_path = self._make_path(
                intake_folder=intake_folder,
                workspace_id=workspace_id,
                document_type_name=document_type_name,
                document_format_name=document_format_name,
                filename=filename,
            )
            await minio_client.put_object(
                bucket_name=bucket,
                object_name=object_path,
                data=io.BytesIO(file_content),
                length=len(file_content),
                content_type=content_type,
            )
        except S3Error:
            self.logger.exception(
                "event=upload-file-failed message=Failed to upload file %s to bucket %s",
                file.filename,
                bucket,
            )
            return None
        return object_path

    async def list_documents(
        self,
        bucket: str = DEFAULT_BUCKET,
        intake_folder: str = DEFAULT_INTAKE_FOLDER,
        workspace_id: str = DEFAULT_WORKSPACE_ID,
        document_type_name: str | None = None,
        document_format_name: str | None = None,
    ) -> list[str] | None:
        """
        List documents in the structured path. Supports filtering by type and format.

        Args:
            bucket: The MinIO bucket name
            intake_folder: The intake folder path
            workspace_id: The workspace identifier
            document_type_name: Optional document type to filter by
            document_format_name: Optional document format to filter by

        Returns:
            list[str] | None: List of object names if successful, None if listing fails
        """
        try:
            prefix = f"{intake_folder}/{workspace_id}/"
            if document_type_name:
                prefix += f"{document_type_name}/"
                if document_format_name:
                    prefix += f"{document_format_name}/"
            objects = await minio_client.list_objects(bucket, prefix=prefix, recursive=True)
        except S3Error:
            self.logger.exception(
                "event=list-objects-failed message=Failed to list objects in bucket %s with prefix %s",
                bucket,
                prefix,
            )
            return None
        return [obj.object_name for obj in objects]

    async def download_document(
        self,
        bucket: str = DEFAULT_BUCKET,
        object_path: str = "",
    ) -> io.BytesIO | None:
        """
        Download a document from MinIO and return it as a BytesIO stream.
        """
        try:
            response = await minio_client.get_object(bucket, object_path)
            file_bytes = await response.read()
            file_data = io.BytesIO(file_bytes)
        except S3Error:
            self.logger.exception(
                "event=download-failed message=Failed to download object from MinIO",
            )
            return None
        return file_data

    async def get_data_document(
        self,
        bucket: str = DEFAULT_BUCKET,
        object_path: str = "",
    ) -> str | None:
        """
        Retrieve data from a document in MinIO using streaming.

        Args:
            bucket: The MinIO bucket name.
            object_path: The path of the object in MinIO.

        Returns:
            str | None: The content of the file as a string, or None if failed.
        """
        try:
            response = await minio_client.get_object(bucket, object_path)
            data_bytes = await response.read()
        except S3Error:
            self.logger.exception(
                "event=retrieve-object-failed message=Failed to retrieve object %s from bucket %s",
                object_path,
                bucket,
            )
            return None
        return base64.b64encode(data_bytes).decode("utf-8")

    async def get_data_bytes_document(
        self,
        bucket: str = DEFAULT_BUCKET,
        object_path: str = "",
    ) -> bytes | None:
        """
        Retrieve data from a document in MinIO using streaming.

        Args:
            bucket: The MinIO bucket name.
            object_path: The path of the object in MinIO.

        Returns:
            bytes | None: The content of the file as a bytes, or None if failed.
        """
        try:
            response = await minio_client.get_object(bucket, object_path)
            data_bytes = await response.read()
        except S3Error:
            self.logger.exception(
                "event=retrieve-object-failed message=Failed to retrieve object %s from bucket %s",
                object_path,
                bucket,
            )
            return None
        return data_bytes

    async def delete_document(
        self,
        bucket: str = DEFAULT_BUCKET,
        object_path: str = "",
    ) -> bool:
        """
        Delete a document from MinIO.

        Args:
            bucket: The MinIO bucket name
            object_path: The path of the object in MinIO

        Returns:
            bool: True if deletion was successful, False if deletion failed
        """
        try:
            await minio_client.remove_object(bucket, object_path)
        except S3Error:
            self.logger.exception(
                "event=delete-object-failed message=Failed to delete object %s from bucket %s",
                object_path,
                bucket,
            )
            return False
        return True

    async def delete_documents(
        self,
        bucket: str = DEFAULT_BUCKET,
        object_paths: list[str] | None = None,
    ) -> bool:
        """
        Delete a document from MinIO.

        Args:
            bucket: The MinIO bucket name
            object_path: The path of the object in MinIO

        Returns:
            bool: True if deletion was successful, False if deletion failed
        """
        try:
            errors = await minio_client.remove_objects(
                bucket,
                delete_object_list=[DeleteObject(name=object_name) for object_name in object_paths],
            )
            for error in errors:
                self.logger.error(
                    "event=deleting-list-documents-failed error=%s",
                    error,
                )
        except S3Error:
            self.logger.exception("Failed to delete objects")
            return False
        return True

    async def create_presigned_urls(
        self,
        bucket: str = DEFAULT_BUCKET,
        object_names: list[str] | None = None,
        expiration: int | None = None,
        response_content_type: str | None = None,
        inline: bool = True,
    ) -> dict[str, str] | None:
        """
        Generate presigned URLs for a list of objects, optionally setting response content type and disposition.

        Args:
            bucket: The name of the bucket
            object_names: List of object names in the bucket
            expiration: The expiration time in seconds (defaults to PRESIGN_URL_EXPIRATION from settings)
            response_content_type: Optional override for 'Content-Type' on response
            inline: Whether to set 'Content-Disposition' to 'inline' or 'attachment'

        Returns:
            dict[str, str] | None: Dictionary of object names to their presigned URLs if successful, None if failed
        """
        if object_names is None:
            object_names = []

        try:
            urls = {}
            for object_name in object_names:
                response_headers = {}
                if response_content_type:
                    response_headers["response-content-type"] = response_content_type
                if inline:
                    response_headers["response-content-disposition"] = "inline"
                else:
                    response_headers["response-content-disposition"] = "attachment"

                url = await minio_client.presigned_get_object(
                    bucket,
                    object_name,
                    expires=datetime.timedelta(seconds=expiration or settings.PRESIGN_URL_EXPIRATION),
                    response_headers=response_headers,
                )
                if url:
                    url = url.replace("http://10.254.1.72:9002", "https://docagent.tmainnovation.vn")
                    urls[object_name] = url
        except S3Error:
            self.logger.exception(
                "event=generate-presigned-urls-failed message=Failed to generate presigned URLs for bucket %s",
                bucket,
            )
            return None
        return urls

    async def copy_document(
        self,
        bucket: str = DEFAULT_BUCKET,
        source_object_path: str = "",
        destination_object_path: str = "",
    ) -> bool:
        """
        Copy a document from one location to another.

        Args:
            bucket: The MinIO bucket name
            source_object_path: The path of the object in MinIO
            destination_object_path: The path where the object will be copied to

        Returns:
            ObjectWriteResult | None: The result of the copy operation if successful, None if copy failed
        """
        if not source_object_path and not destination_object_path:
            self.logger.error(
                "event=copy-document-failed message=Please provide source and destination paths",
            )
            return False
        try:
            copy_source_obj = CopySource(bucket_name=bucket, object_name=source_object_path)
            await minio_client.copy_object(
                bucket_name=bucket,  # Destination bucket name
                object_name=destination_object_path,  # Destination object name
                source=copy_source_obj,  # Alternative using CopySource object
            )
        except S3Error:
            self.logger.exception(
                "event=copy-object-failed message=Failed to copy object %s from bucket %s",
                source_object_path,
                bucket,
            )
            return False
        return True
