import urllib
from collections.abc import AsyncGenerator

import orjson
from fastapi import BackgroundTasks, Depends, Form, Path, Query, Request, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from fastapi.routing import APIRouter

from handlers.document_type import DocumentTypeChecker
from helpers.jwt_auth import require_any_scope_cached, require_scopes_cached
from initializer import dt_handler, redis_pubsub_manager
from schemas.document_type import DocumentTypeUpdateDisplay
from schemas.response import BasicResponse
from utils.enums import APIScope, DocWorkItemState, RedisChannelName, TimeRangeFilter

router = APIRouter(prefix="/document-type", dependencies=[])


async def event_generator(dt_id: str, request: Request) -> AsyncGenerator[bytes] | None:
    channel = f"{RedisChannelName.DOCUMENT_TYPE}:{dt_id}"

    async for message in redis_pubsub_manager.get_messages(channel):
        if await request.is_disconnected():
            break
        yield f"data: {orjson.dumps(message).decode('utf-8')}\n\n"


@router.get(
    "",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_any_scope_cached(APIScope.DOCUMENT_READ, APIScope.DOCUMENT_PROCESSING)),
    ],
)
async def get_all_document_types(
    response: Response,
    q: str = "",
    page: int = 1,
    page_size: int = 10,
) -> BasicResponse:
    """
    Retrieve a paginated list of all document types.

    Supports searching by query and pagination.

    **Required Scopes:** `document_read` or `document_processing`
    """
    page_data = await dt_handler.get_all_document_types(
        q=q,
        page=page,
        page_size=page_size,
    )
    if page_data is None:
        resp = BasicResponse(
            status="failed",
            message="Fetch all document types failed",
            data=None,
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
    else:
        resp = BasicResponse(
            status="success",
            message="Fetch all document types successfully",
            data=page_data.model_dump(),
        )
        response.status_code = status.HTTP_200_OK
    return resp


@router.get(
    "/{dt_id}/dashboard",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_scopes_cached(APIScope.DOCUMENT_READ)),
    ],
)
async def get_work_items_by_dt_id(
    response: Response,
    dt_id: str,
    q: str = "",
    states: list[DocWorkItemState] = Query(description="List states to filter", default_factory=list),
    time_range: TimeRangeFilter | None = None,
    page: int = 1,
    page_size: int = 10,
) -> BasicResponse:
    """
    Retrieve a paginated list of work items for a specific document type.

    Supports searching by query, filtering by states, time range, and pagination.

    **Required Scopes:** `document_read`
    """
    page_data = await dt_handler.get_work_items_by_dt_id(
        dt_id=dt_id,
        q=q,
        states=states,
        time_range=time_range,
        page=page,
        page_size=page_size,
    )
    if page_data is None:
        resp = BasicResponse(
            status="failed",
            message="Fetch all work items failed",
            data=None,
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
    else:
        resp = BasicResponse(
            status="success",
            message="Fetch all work items successfully",
            data=page_data.model_dump(),
        )
        response.status_code = status.HTTP_200_OK
    return resp


@router.get(
    "/list-names",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_any_scope_cached(APIScope.DOCUMENT_READ, APIScope.DOCUMENT_PROCESSING)),
    ],
)
async def get_all_names_document_type(
    response: Response,
    filter_active: bool = True,
) -> BasicResponse:
    """
    Retrieve a list of all document type names.

    **Required Scopes:** `document_read` or `document_processing`
    """
    dt_names = await dt_handler.get_all_names_document_types(filter_active=filter_active)
    if dt_names is None:
        resp = BasicResponse(
            status="failed",
            message="Failed to fetch document all type names",
            data=None,
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
    else:
        resp = BasicResponse(
            status="success",
            message="Return document type names list successfully",
            data=[dt_name.model_dump() for dt_name in dt_names],
        )
        response.status_code = status.HTTP_200_OK
    return resp


@router.post(
    "",
    response_model=BasicResponse,
    dependencies=[
        Depends(DocumentTypeChecker()),
        Depends(require_scopes_cached(APIScope.DOCUMENT_ADMIN)),
    ],
)
async def create_document_type(
    response: Response,
    dt_file: UploadFile,
    dt_name: str = Form(),
) -> BasicResponse:
    """
    Create a new document type.

    This endpoint allows for the creation of a new document type by uploading a definition file.

    **Required Scopes:** `document_admin`
    """
    dt_object_data = await dt_handler.create_document_type(dt_name=dt_name, dt_file=dt_file)
    if dt_object_data is None:
        resp = BasicResponse(
            status="failed",
            message="Failed to create new document type",
            data=None,
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
    else:
        resp = BasicResponse(
            status="success",
            message="New document type created successfully",
            data=dt_object_data,
        )

        response.status_code = status.HTTP_201_CREATED
    return resp


@router.get(
    "/{dt_id}",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_any_scope_cached(APIScope.DOCUMENT_READ, APIScope.DOCUMENT_PROCESSING)),
    ],
)
async def get_document_type(
    response: Response,
    dt_id: str,
) -> BasicResponse:
    """
    Retrieve a document type by its ID.

    Returns the details of a specific document type.

    **Required Scopes:** `document_read` or `document_processing`
    """
    document_type = await dt_handler.get_document_type_by_id(
        dt_id=dt_id,
    )
    if document_type is None:
        resp = BasicResponse(
            status="failed",
            message=f"Failed to fetch document type with id: {dt_id}",
            data=None,
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
    else:
        resp = BasicResponse(
            status="success",
            message="Document type retrieved successfully",
            data=document_type.model_dump(),
        )

        response.status_code = status.HTTP_200_OK
    return resp


@router.put(
    "/{dt_id}",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_scopes_cached(APIScope.DOCUMENT_ADMIN)),
    ],
)
async def save_configuration(
    response: Response,
    dt_id: str,
    dt_update: DocumentTypeUpdateDisplay,
) -> BasicResponse:
    """
    Save the configuration for a document type.

    This endpoint allows for updating the display configuration of an existing document type.

    **Required Scopes:** `document_admin`
    """
    dt_id = await dt_handler.save_configuration_document_type(
        dt_id=dt_id,
        dt_update=dt_update,
    )
    if dt_id is None:
        resp = BasicResponse(
            status="failed",
            message=f"Document type not found with id: {dt_id}",
            data=None,
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
    else:
        resp = BasicResponse(
            status="success",
            message="Document type saved successfully",
            data=dt_id,
        )

        response.status_code = status.HTTP_200_OK
    return resp


@router.get(
    "/{dt_id}/document-format",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_any_scope_cached(APIScope.DOCUMENT_READ, APIScope.DOCUMENT_PROCESSING)),
    ],
)
async def get_document_format_by_dt_id(
    response: Response,
    dt_id: str,
    q: str = "",
    page: int = 1,
    page_size: int = 10,
) -> BasicResponse:
    """
    Retrieve a paginated list of document formats for a specific document type.

    Supports searching by query and pagination.

    **Required Scopes:** `document_read` or `document_processing`
    """
    page_data = await dt_handler.get_df_by_dt_id(
        dt_id=dt_id,
        q=q,
        page=page,
        page_size=page_size,
    )
    if page_data is None:
        resp = BasicResponse(
            status="failed",
            message=f"Fetch all document format failed with dt_id: {dt_id}",
            data=None,
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
    else:
        resp = BasicResponse(
            status="success",
            message="Fetch all document format successfully",
            data=page_data.model_dump(),
        )

        response.status_code = status.HTTP_200_OK
    return resp


@router.get(
    "/{dt_id}/training",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_scopes_cached(APIScope.DOCUMENT_READ)),
    ],
)
async def get_df_training_by_dt_id(
    response: Response,
    dt_id: str,
    q: str = "",
    states: list[DocWorkItemState] = Query(description="List states to filter", default_factory=list),
    time_range: TimeRangeFilter | None = None,
    page: int = 1,
    page_size: int = 10,
) -> BasicResponse:
    """
    Retrieve a paginated list of document formats in training for a specific document type.

    Supports searching by query, filtering by states, time range, and pagination.

    **Required Scopes:** `document_read`
    """
    page_data = await dt_handler.get_df_training_by_dt_id(
        dt_id=dt_id,
        q=q,
        states=states,
        time_range=time_range,
        page=page,
        page_size=page_size,
    )
    if page_data is None:
        resp = BasicResponse(
            status="failed",
            message=f"Fetch all document format in Traininig failed with dt_id: {dt_id}",
            data=None,
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
    else:
        resp = BasicResponse(
            status="success",
            message="Fetch all document format in Training successfully",
            data=page_data.model_dump(),
        )

        response.status_code = status.HTTP_200_OK
    return resp


@router.post(
    "/{dt_id}/activate",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_scopes_cached(APIScope.DOCUMENT_ADMIN)),
    ],
)
async def activate_document_type_by_id(
    response: Response,
    dt_id: str,
    dt_update: DocumentTypeUpdateDisplay,
    background_tasks: BackgroundTasks,
) -> BasicResponse:
    """
    Activate a document type by its ID.

    This endpoint initiates a background activation process for a specified document type.

    **Required Scopes:** `document_admin`
    """
    is_activated = await dt_handler.activate_document_type_by_id(
        dt_id=dt_id,
        dt_update=dt_update,
        background_tasks=background_tasks,
    )
    if not is_activated:
        resp = BasicResponse(
            status="failed",
            message=f"Start activate document type failed for document format with id: {dt_id}",
            data=None,
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
    else:
        resp = BasicResponse(
            status="success",
            message="Activate document type started in background successfully",
            data=dt_id,
        )
        response.status_code = status.HTTP_202_ACCEPTED
    return resp


@router.get(
    "/{dt_id}/stream",
    dependencies=[
        Depends(require_scopes_cached(APIScope.DOCUMENT_READ)),
    ],
)
def stream(
    dt_id: str,
    request: Request,
) -> StreamingResponse:
    """
    Stream events for a specific document type using Server-Sent Events.

    **Required Scopes:** `document_read`
    """
    return StreamingResponse(
        event_generator(dt_id, request),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no"},
    )


@router.delete(
    "/{dt_id}",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_scopes_cached(APIScope.DOCUMENT_ADMIN)),
    ],
)
async def delete_document_type_by_id(
    response: Response,
    dt_id: str,
) -> BasicResponse:
    """
    Delete a document type by its ID.

    This endpoint allows for the permanent deletion of a document type.

    **Required Scopes:** `document_admin`
    """
    is_deleted = await dt_handler.delete_document_type_by_id(
        dt_id=dt_id,
    )
    if not is_deleted:
        resp = BasicResponse(
            status="failed",
            message=f"Delete document type failed with dt_id: {dt_id}",
            data=None,
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
    else:
        resp = BasicResponse(
            status="success",
            message="Delete document type successfully",
            data=dt_id,
        )

        response.status_code = status.HTTP_200_OK
    return resp


@router.post(
    "/validate-name",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_scopes_cached(APIScope.DOCUMENT_ADMIN)),
    ],
)
async def check_document_type_name_exists(
    response: Response,
    dt_name: str,
) -> BasicResponse:
    """
    Check if a document type name already exists.

    This endpoint validates if a document type name is unique.

    **Required Scopes:** `document_admin`
    """
    is_existed = await dt_handler.is_document_type_exists(
        dt_name=dt_name,
    )
    if is_existed:
        resp = BasicResponse(
            status="failed",
            message=f"Document type is existed with dt_name: {dt_name}",
            data=None,
        )
        response.status_code = status.HTTP_409_CONFLICT
    else:
        resp = BasicResponse(
            status="success",
            message="Validate document type name successfully",
            data=dt_name,
        )

        response.status_code = status.HTTP_200_OK
    return resp


@router.get(
    "/{dt_id}/export",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_scopes_cached(APIScope.DOCUMENT_ADMIN)),
    ],
)
async def export_document_type(
    response: Response,
    dt_id: str,
) -> StreamingResponse | BasicResponse:
    """
    Export document type by ID.

    This endpoint allows for exporting the configuration and data of a specific document type as a ZIP file.

    **Required Scopes:** `document_admin`
    """
    zip_buffer = await dt_handler.export_document_type_as_zip(dt_id)

    if zip_buffer is None:
        resp = BasicResponse(
            status="failed",
            message="Failed to export document type",
            data=None,
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
        return resp

    filename = f"document_type_{dt_id}.zip" if dt_id else "document_types_export.zip"

    encoded_filename = urllib.parse.quote(filename, safe="")
    content_disposition = f"attachment; filename=\"{filename}\"; filename*=UTF-8''{encoded_filename}"

    response.status_code = status.HTTP_200_OK
    return StreamingResponse(
        content=zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": content_disposition},
    )


@router.post(
    "/import",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_scopes_cached(APIScope.DOCUMENT_ADMIN)),
    ],
)
async def import_document_type(
    response: Response,
    dt_name: str,
    file: UploadFile,
) -> BasicResponse:
    """
    Import document type from a ZIP file containing JSON data and files.

    This endpoint allows for importing a document type's configuration and data from a ZIP file.

    **Required Scopes:** `document_admin`
    """
    if not file.filename.endswith(".zip"):
        resp = BasicResponse(
            status="failed",
            message="File must be a ZIP file or JSON file",
            data=None,
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
        return resp

    result = await dt_handler.import_document_type(dt_name, file)
    if not result:
        resp = BasicResponse(
            status="failed",
            message="Failed to import Document type. ",
            data=None,
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
        return resp

    resp = BasicResponse(
        status="success",
        message="Import document type successfully.",
        data=result,
    )
    response.status_code = status.HTTP_200_OK

    return resp


@router.get(
    "/{dt_id}/document-format/list-names",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_any_scope_cached(APIScope.DOCUMENT_READ, APIScope.DOCUMENT_PROCESSING)),
    ],
)
async def get_document_format_names(
    response: Response,
    dt_id: str = Path(..., description="Document Type ID"),
) -> BasicResponse:
    """
    Get all document format names and IDs for a given document type.
    """
    result = await dt_handler.get_all_names_document_formats_by_dt_id(dt_id)
    resp = BasicResponse(
        status="success",
        message="Fetch document format names successfully",
        data=[df.model_dump() for df in result],
    )
    response.status_code = status.HTTP_200_OK
    return resp
