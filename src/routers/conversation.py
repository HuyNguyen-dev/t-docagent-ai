from fastapi import Depends, File, HTTPException, Response, UploadFile, status
from fastapi.routing import APIRouter

from helpers.jwt_auth import require_scopes_cached
from initializer import conv_handler
from schemas.conversation import ConversationDownloadRequest, ConversationInput, ConversationUpdateName
from schemas.response import BasicResponse
from utils.enums import APIScope

router = APIRouter(prefix="/conversation", dependencies=[])


@router.post(
    "",
    dependencies=[
        Depends(require_scopes_cached(APIScope.CONVERSATION_ADMIN)),
    ],
)
async def create_new_conversations(
    response: Response,
    conv_input: ConversationInput,
) -> BasicResponse:
    """
    Create new conversations.

    This endpoint allows for the creation of one or more new conversations.

    **Required Scopes:** `conversation_admin`
    """
    new_convs = await conv_handler.create_new_conversations(conv_input=conv_input)
    if new_convs is None or None in new_convs:
        resp = BasicResponse(
            status="failed",
            message="Create new conversations failed",
            data=None,
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
    else:
        resp = BasicResponse(
            status="success",
            message="New conversations created successfully",
            data=new_convs,
        )
        response.status_code = status.HTTP_201_CREATED
    return resp


@router.put(
    "/{conv_id}/name",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_scopes_cached(APIScope.CONVERSATION_ADMIN)),
    ],
)
async def update_conversation_name(
    response: Response,
    conv_id: str,
    conv_update: ConversationUpdateName,
) -> BasicResponse:
    """
    Update the name of a conversation.

    This endpoint allows for changing the name of an existing conversation.

    **Required Scopes:** `conversation_admin`
    """
    success = await conv_handler.update_conversation_name(
        conv_id=conv_id,
        new_name=conv_update.name,
    )
    if not success:
        resp = BasicResponse(
            status="failed",
            message=f"Failed to update conversation name for id: {conv_id}",
            data=None,
        )
        response.status_code = status.HTTP_404_NOT_FOUND
    else:
        resp = BasicResponse(
            status="success",
            message="Conversation name updated successfully",
            data={"conv_id": conv_id, "name": conv_update.name},
        )
        response.status_code = status.HTTP_200_OK
    return resp


@router.post(
    "/{conv_id}/files/download",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_scopes_cached(APIScope.CONVERSATION_READ)),
    ],
)
async def download_conversation_files(
    response: Response,
    conv_id: str,
    download_request: ConversationDownloadRequest,
) -> BasicResponse:
    """
    Generate download URLs from a list of asset URIs in a conversation.

    Returns a list of presigned URLs corresponding to the input URIs.

    **Required Scopes:** `conversation_read`
    """
    urls = await conv_handler.get_download_urls_for_assets(conv_id=conv_id, asset_uris=download_request.asset_uris)
    if urls is None:
        resp = BasicResponse(
            status="failed",
            message="Failed to generate download URLs",
            data=None,
        )
        response.status_code = status.HTTP_404_NOT_FOUND
    else:
        resp = BasicResponse(
            status="success",
            message="Download URLs generated successfully",
            data=urls,
        )
        response.status_code = status.HTTP_200_OK
    return resp


@router.delete(
    "/{conv_id}",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_scopes_cached(APIScope.CONVERSATION_ADMIN)),
    ],
)
async def delete_conversation(
    response: Response,
    conv_id: str,
) -> BasicResponse:
    """
    Delete a conversation by its ID.

    This endpoint allows for the permanent deletion of a conversation.

    **Required Scopes:** `conversation_admin`
    """
    success = await conv_handler.delete_conversation(conv_id=conv_id)
    if not success:
        resp = BasicResponse(
            status="failed",
            message="Delete conversation was failed",
            data=None,
        )
        response.status_code = status.HTTP_404_NOT_FOUND
    else:
        resp = BasicResponse(
            status="success",
            message="Conversation was deleted successfully",
            data={"conv_id": conv_id},
        )
        response.status_code = status.HTTP_200_OK
    return resp


@router.get(
    "/{conv_id}/history",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_scopes_cached(APIScope.CONVERSATION_READ)),
    ],
)
async def get_history(
    response: Response,
    conv_id: str,
    limit: int = 10,
    offset: int = 0,
) -> BasicResponse:
    """
    Get the conversation history for a specific conversation.

    **Required Scopes:** `conversation_read`
    """
    try:
        history = await conv_handler.get_conversation_history(
            conv_id,
            limit=limit,
            offset=offset,
        )
        if history is None:
            resp = BasicResponse(
                status="failed",
                message="Failed to discover annotations",
                data=None,
            )
            response.status_code = status.HTTP_400_BAD_REQUEST
        else:
            resp = BasicResponse(
                status="success",
                message="Successfully retrieved conversation history",
                data=history.model_dump(),
            )
            response.status_code = status.HTTP_200_OK
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving conversation history: {e!s}",
        ) from e
    return resp


@router.get(
    "/{conv_id}/files",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_scopes_cached(APIScope.CONVERSATION_READ)),
    ],
)
async def get_conversation_files(
    response: Response,
    conv_id: str,
) -> BasicResponse:
    """
    Get all files associated with a conversation.

    **Required Scopes:** `conversation_read`
    """
    files = await conv_handler.get_conversation_files(conv_id=conv_id)
    if files is None:
        resp = BasicResponse(
            status="failed",
            message="Failed to retrieve conversation files",
            data=None,
        )
        response.status_code = status.HTTP_404_NOT_FOUND
    else:
        resp = BasicResponse(
            status="success",
            message="Conversation files retrieved successfully",
            data=files,
        )
        response.status_code = status.HTTP_200_OK
    return resp


@router.post(
    "/{conv_id}/files",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_scopes_cached(APIScope.CONVERSATION_READ)),
    ],
)
async def upload_conversation_files(
    response: Response,
    conv_id: str,
    files: list[UploadFile] = File(...),
) -> BasicResponse:
    """
    Upload one or more files/assets to a conversation.

    Accepts multipart/form-data files and returns a list of attachment metadata.

    **Required Scopes:** `conversation_read`
    """
    attachments = await conv_handler.upload_asset_to_conversation(conv_id=conv_id, files=files)
    if attachments is None:
        resp = BasicResponse(
            status="failed",
            message="Failed to upload files/assets to conversation",
            data=None,
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
    else:
        resp = BasicResponse(
            status="success",
            message="Files/assets uploaded successfully",
            data=[a.model_dump() for a in attachments],
        )
        response.status_code = status.HTTP_201_CREATED
    return resp


@router.delete(
    "/{conv_id}/files",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_scopes_cached(APIScope.CONVERSATION_READ)),
    ],
)
async def delete_conversation_file(
    response: Response,
    conv_id: str,
    asset_uri: str,
) -> BasicResponse:
    """
    Delete an file/asset from a conversation by its uri returned from upload.

    **Required Scopes:** `conversation_read`
    """
    success = await conv_handler.delete_asset_from_conversation(conv_id=conv_id, asset_uri=asset_uri)
    if not success:
        resp = BasicResponse(
            status="failed",
            message="Failed to delete file/asset from conversation",
            data=None,
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
    else:
        resp = BasicResponse(
            status="success",
            message="File/asset deleted successfully",
            data={"conv_id": conv_id, "asset_uri": asset_uri},
        )
        response.status_code = status.HTTP_200_OK
    return resp
