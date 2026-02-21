import urllib.parse

from fastapi import Body, Depends, Response, status
from fastapi.responses import StreamingResponse
from fastapi.routing import APIRouter

from helpers.jwt_auth import require_scopes_cached
from initializer import dwi_handler
from schemas.response import BasicResponse
from utils.enums import APIScope, WorkItemDownloadType

router = APIRouter(prefix="/work-item", dependencies=[])


@router.get(
    "/{dwi_id}",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_scopes_cached(APIScope.WORK_ITEM_READ)),
    ],
)
async def get_document_work_item_by_id(
    response: Response,
    dwi_id: str,
) -> BasicResponse:
    """
    Retrieve a document work item by its ID.

    Returns the details of a specific document work item.

    **Required Scopes:** `work_item_read`
    """
    document_work_item = await dwi_handler.get_document_work_item_by_id(dwi_id=dwi_id)
    if document_work_item is None:
        response.status_code = status.HTTP_404_NOT_FOUND
        return BasicResponse(
            status="failed",
            message=f"Document work item not found with dwi_id: {dwi_id}",
            data=None,
        )
    response.status_code = status.HTTP_200_OK
    return BasicResponse(
        status="success",
        message=f"Document work item found with dwi_id: {dwi_id}",
        data=document_work_item,
    )


@router.post(
    "/download",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_scopes_cached(APIScope.WORK_ITEM_DOWNLOAD)),
    ],
)
async def download_multiple_work_items(
    response: Response,
    dwi_ids: list[str] = Body(..., embed=True),
    download_type: WorkItemDownloadType = WorkItemDownloadType.ALL,
) -> StreamingResponse | BasicResponse:
    """
    Download multiple work items as a single ZIP.

    Body: { "dwi_ids": ["id1", "id2", ...] }
    Query: type=source|content|logs|all (default all)
    """
    if not dwi_ids:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return BasicResponse(status="failed", message="dwi_ids is required", data=None)

    success, zip_stream, file_name = await dwi_handler.unified_download_multiple(dwi_ids, download_type)
    if not success or zip_stream is None or not file_name:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return BasicResponse(status="failed", message="No files available to download", data=None)
    encoded_filename = urllib.parse.quote(file_name, safe="")
    content_disposition = f"attachment; filename=\"{file_name}\"; filename*=UTF-8''{encoded_filename}"

    response.status_code = status.HTTP_200_OK
    return StreamingResponse(
        content=zip_stream,
        media_type="application/zip",
        headers={"Content-Disposition": content_disposition},
    )


@router.delete(
    "",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_scopes_cached(APIScope.WORK_ITEM_ADMIN)),
    ],
)
async def delete_multi_work_items(
    response: Response,
    dwi_ids: list[str] = Body(..., embed=True),
) -> BasicResponse:
    """
    Delete multiple Document Work Items by their IDs.

    This endpoint allows for the permanent deletion of one or more document work items.

    **Required Scopes:** `work_item_admin`
    """
    delete_result = await dwi_handler.delete_document_work_items_by_ids(dwi_ids)
    if not delete_result:
        response.status_code = status.HTTP_204_NO_CONTENT
        return BasicResponse(
            status="failed",
            message="No work items were deleted.",
            data=delete_result,
        )
    response.status_code = status.HTTP_200_OK
    return BasicResponse(
        status="success",
        message="Delete work items completed.",
        data=delete_result,
    )
