from fastapi import BackgroundTasks, Body, Depends, Form, Response, UploadFile, status
from fastapi.routing import APIRouter

from handlers.document_format import DocumentFormatChecker
from helpers.jwt_auth import require_scopes_cached
from initializer import df_handler
from schemas.document_format import DocumentFormatUpdateDisplay, DocumentFormatUpdateState
from schemas.response import BasicResponse
from utils.enums import APIScope

router = APIRouter(prefix="/document-format", dependencies=[])


@router.post(
    "",
    response_model=BasicResponse,
    dependencies=[
        Depends(DocumentFormatChecker()),
        Depends(require_scopes_cached(APIScope.DOCUMENT_ADMIN)),
    ],
)
async def create_document_format(
    response: Response,
    df_file: UploadFile,
    dt_id: str = Form(description="The ID of document type associated new document format"),
    df_name: str = Form(description="The name of new document format"),
) -> BasicResponse:
    """
    Create a new document format.

    This endpoint allows for the creation of a new document format,
    associating it with a document type and uploading a definition file.

    **Required Scopes:** `document_admin`
    """
    df_object_data = await df_handler.create_document_format(dt_id=dt_id, df_name=df_name, df_file=df_file)
    if df_object_data is None:
        resp = BasicResponse(
            status="failed",
            message="Document format created failed",
            data=None,
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
    else:
        resp = BasicResponse(
            status="success",
            message="Document format created successfully",
            data=df_object_data,
        )
        response.status_code = status.HTTP_201_CREATED
    return resp


@router.get(
    "/{df_id}",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_scopes_cached(APIScope.DOCUMENT_READ)),
    ],
)
async def get_document_format_by_id(
    response: Response,
    df_id: str,
) -> BasicResponse:
    """
    Retrieve a document format by its ID.

    Returns the details of a specific document format.

    **Required Scopes:** `document_read`
    """
    document_format = await df_handler.get_document_format_by_id(df_id=df_id)
    if document_format is None:
        resp = BasicResponse(
            status="failed",
            message=f"Failed to fetch document format with id: {df_id}",
            data=None,
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
    else:
        resp = BasicResponse(
            status="success",
            message="Document format retrieved successfully",
            data=document_format.model_dump(),
        )
        response.status_code = status.HTTP_200_OK
    return resp


@router.put(
    "/{df_id}",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_scopes_cached(APIScope.DOCUMENT_ADMIN)),
    ],
)
async def update_document_format_by_id(
    response: Response,
    df_id: str,
    df_update: DocumentFormatUpdateDisplay,
) -> BasicResponse:
    """
    Update a document format by its ID.

    This endpoint allows for updating the display properties of an existing document format.

    **Required Scopes:** `document_admin`
    """
    is_updated, msg_data = await df_handler.update_document_format_by_id(df_id=df_id, df_update=df_update)
    if msg_data is None:
        resp = BasicResponse(
            status="failed",
            message=f"Failed to update document format with id: {df_id}",
            data=None,
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
    elif not is_updated:
        resp = BasicResponse(
            status="failed",
            message=msg_data,
            data=None,
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
    else:
        resp = BasicResponse(
            status="success",
            message="Document format updated successfully",
            data=msg_data,
        )
        response.status_code = status.HTTP_200_OK
    return resp


@router.delete(
    "",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_scopes_cached(APIScope.DOCUMENT_ADMIN)),
    ],
)
async def delete_document_format_by_ids(
    response: Response,
    df_ids: list[str] = Body(..., embed=True),
) -> BasicResponse:
    """
    Delete document formats by their IDs.

    This endpoint allows for the permanent deletion of one or more document formats.

    **Required Scopes:** `document_admin`
    """
    delete_status = await df_handler.delete_document_formats_by_ids(df_ids=df_ids)
    resp = BasicResponse(
        status="success",
        message="Document format deleted successfully",
        data=delete_status,
    )
    response.status_code = status.HTTP_200_OK
    return resp


@router.post(
    "/{df_id}/train",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_scopes_cached(APIScope.DOCUMENT_ADMIN)),
    ],
)
async def train_document_format_by_id(
    response: Response,
    df_id: str,
    df_update: DocumentFormatUpdateDisplay,
    background_tasks: BackgroundTasks,
) -> BasicResponse:
    """
    Start training for a document format by its ID.

    This endpoint initiates a background training process for a specified document format.

    **Required Scopes:** `document_admin`
    """
    is_run = await df_handler.train_document_format_by_id(
        df_id=df_id,
        df_update=df_update,
        background_tasks=background_tasks,
    )
    if not is_run:
        resp = BasicResponse(
            status="failed",
            message=f"Start training failed for document format with id: {df_id}",
            data=None,
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
    else:
        resp = BasicResponse(
            status="success",
            message="Training started in background successfully",
            data=df_id,
        )
        response.status_code = status.HTTP_202_ACCEPTED
    return resp


@router.put(
    "/state/update",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_scopes_cached(APIScope.DOCUMENT_ADMIN)),
    ],
)
async def change_state_document_format_by_ids(
    response: Response,
    update_state: DocumentFormatUpdateState,
    background_tasks: BackgroundTasks,
) -> BasicResponse:
    """
    Change the state of document formats by their IDs.

    This endpoint allows for updating the processing state of one or more document formats.

    **Required Scopes:** `document_admin`
    """
    is_updated = await df_handler.change_state_document_format_by_ids(
        df_ids=update_state.df_ids,
        state=update_state.state,
        background_tasks=background_tasks,
    )
    if not is_updated:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return BasicResponse(
            status="failed",
            message="Document format state update failed",
            data=None,
        )

    response.status_code = status.HTTP_200_OK
    return BasicResponse(
        status="success",
        message="Document format state updated successfully",
        data=update_state.df_ids,
    )


@router.post(
    "/validate-name",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_scopes_cached(APIScope.DOCUMENT_ADMIN)),
    ],
)
async def check_document_format_name_exists(
    response: Response,
    dt_id: str,
    df_name: str,
) -> BasicResponse:
    """
    Check if a document format name already exists for a given document type.

    This endpoint validates if a document format name is unique within a specific document type.

    **Required Scopes:** `document_admin`
    """
    is_existed = await df_handler.is_document_format_exists(
        dt_id=dt_id,
        df_name=df_name,
    )
    if is_existed:
        resp = BasicResponse(
            status="failed",
            message=f"Document format is existed with df_name: {df_name}",
            data=None,
        )
        response.status_code = status.HTTP_409_CONFLICT
    else:
        resp = BasicResponse(
            status="success",
            message="Validate document format name successfully",
            data=df_name,
        )

        response.status_code = status.HTTP_200_OK
    return resp
