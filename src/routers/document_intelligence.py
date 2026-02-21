from typing import Annotated

import orjson
from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from pydantic import ValidationError

from helpers.jwt_auth import require_scopes_cached
from initializer import di_handler
from schemas.document_intelligence import AnnotationConfig
from schemas.response import BasicResponse
from utils.enums import APIScope

router = APIRouter(prefix="/document-intelligence")


@router.post(
    "/discover-annotations",
    dependencies=[
        Depends(require_scopes_cached(APIScope.DOCUMENT_INTELLIGENCE)),
    ],
)
async def discover_annotations(
    response: Response,
    dt_id: Annotated[str, Form(..., description="Document Type ID")],
    zip_file: Annotated[UploadFile, File(description="ZIP file containing document images")],
    annotation_config: Annotated[str, Form(..., description="JSON string containing field and tables data")],
) -> BasicResponse:
    """
    Discover annotated images to suggest document schema.

    This endpoint processes a ZIP file of document images and an annotation configuration
    to suggest a document schema using LLM.

    **Required Scopes:** `document_intelligence`
    """
    try:
        # Parse and validate JSON configuration
        config_dict = orjson.loads(annotation_config)
        annotation_config = AnnotationConfig(**config_dict)

        # call handler to use LLM for document schema extraction
        document_schema = await di_handler.suggest_document_schema(
            dt_id=dt_id,
            zip_file=zip_file,
            config=annotation_config,
        )

        if document_schema is None:
            resp = BasicResponse(
                status="failed",
                message="Failed to discover annotations",
                data=None,
            )
            response.status_code = status.HTTP_400_BAD_REQUEST
        else:
            resp = BasicResponse(
                status="success",
                message="Document type saved successfully",
                data=document_schema.model_dump(),
            )

            response.status_code = status.HTTP_200_OK
    except orjson.JSONDecodeError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid JSON in annotation_config: {e!s}",
        ) from e
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid configuration format: {e!s}",
        ) from e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) from e
    return resp


@router.post(
    "/discover-mapping",
    dependencies=[
        Depends(require_scopes_cached(APIScope.DOCUMENT_INTELLIGENCE)),
    ],
)
async def discover_mapping(
    response: Response,
    dt_id: Annotated[str, Form(description="The id of document type to process")],
    df_id: Annotated[str, Form(description="The id of document format to process")],
    zip_file: Annotated[UploadFile, File(description="ZIP file containing document images")],
    annotation_config: Annotated[str, Form(description="User annotated prompt/instructions")],
) -> BasicResponse:
    """
    Discover and recommend schema mappings from document images.

    This endpoint processes a ZIP file of document images and an annotation configuration
    to suggest schema mappings for a given document type and format.

    **Required Scopes:** `document_intelligence`
    """

    recommended_format = await di_handler.generate_document_format_schema(
        dt_id=dt_id,
        df_id=df_id,
        zip_file=zip_file,
        annotation_config=annotation_config,
    )

    if recommended_format is None:
        resp = BasicResponse(
            status="failed",
            message="Failed to discover mapping fields/tables",
            data=None,
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
    else:
        resp = BasicResponse(
            status="success",
            message="Discover mapping fields/tables successfully",
            data=recommended_format.model_dump(),
        )

        response.status_code = status.HTTP_200_OK
    return resp


@router.post(
    "/extract-content",
    dependencies=[
        Depends(require_scopes_cached(APIScope.DOCUMENT_PROCESSING)),
    ],
)
async def extract_content(
    response: Response,
    dt_id: Annotated[str, Form(description="The ID of the document type")],
    df_id: Annotated[str, Form(description="The ID of the document format")],
    file: Annotated[UploadFile, File(description="The file to extract content from")],
) -> BasicResponse:
    """
    Extract content from an uploaded file using the specified document type and format.

    Args:
        dt_id: The ID of the document type.
        df_id: The ID of the document format.
        file: The uploaded file (e.g., PDF, image) for content extraction.

    Returns:
        BasicResponse with status and content:
        - status: "success" or "failed"
        - message: Description of the result
        - data: Extracted content and metadata if successful, None if failed

    **Required Scopes:** `document_processing`
    """
    extracted_data = await di_handler.extract_content_from_file(
        dt_id=dt_id,
        df_id=df_id,
        file=file,
    )

    if extracted_data is None:
        resp = BasicResponse(
            status="failed",
            message="Failed to extract content from the file",
            data=None,
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
    else:
        resp = BasicResponse(
            status="success",
            message="Content extracted successfully",
            data=extracted_data,
        )
        response.status_code = status.HTTP_200_OK
    return resp


@router.post(
    "/extract-content/batch",
    dependencies=[
        Depends(require_scopes_cached(APIScope.DOCUMENT_PROCESSING)),
    ],
)
async def extract_content_batch(
    response: Response,
    dt_id: Annotated[str, Form(description="The ID of the document type")],
    df_id: Annotated[str, Form(description="The ID of the document format")],
    files: Annotated[list[UploadFile], File(description="The files to extract content from")],
) -> BasicResponse:
    """
    Extract content from multiple uploaded files using the specified document type and format.

    Returns a list with per-file results in input order.

    **Required Scopes:** `document_processing`
    """
    extracted_list = await di_handler.extract_content_from_files(
        dt_id=dt_id,
        df_id=df_id,
        files=files,
    )

    if extracted_list is None:
        resp = BasicResponse(
            status="failed",
            message="Failed to extract content from files",
            data=None,
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
    else:
        resp = BasicResponse(
            status="success",
            message="Content extracted successfully",
            data=extracted_list,
        )
        response.status_code = status.HTTP_200_OK
    return resp
