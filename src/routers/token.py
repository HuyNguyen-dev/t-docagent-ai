from typing import Annotated

from fastapi import Depends, Query, Response, status
from fastapi.routing import APIRouter

from handlers.token import TokenHandler
from helpers.jwt_auth import get_current_user_unified_cached, require_scopes_cached
from schemas.response import BasicResponse
from schemas.token import TokenCreateRequest
from schemas.user import UserResponse
from utils.enums import APIScope

router = APIRouter(prefix="/tokens")
token_handler = TokenHandler()


@router.post(
    "",
    response_model=BasicResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "Token created successfully"},
        400: {"description": "Invalid request or insufficient permissions"},
        401: {"description": "Authentication required"},
        403: {"description": "Insufficient scopes"},
    },
    dependencies=[
        Depends(require_scopes_cached(APIScope.TOKEN_ADMIN)),
    ],
)
async def create_token(
    response: Response,
    token_request: TokenCreateRequest,
    current_user: Annotated[UserResponse, Depends(get_current_user_unified_cached)],
) -> BasicResponse:
    """
    Create a new access token with specified scopes.

    This endpoint allows users to create new access tokens for API access.
    The token will be granted only scopes that the user already has permission for.

    **Required Scopes:** `token_admin`
    """
    try:
        token_data = await token_handler.create_token(current_user, token_request)
        return BasicResponse(
            status="success",
            data=token_data.model_dump(),
            message="Create token with scopes successfully",
        )
    except ValueError as e:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return BasicResponse(
            status="failed",
            message=str(e),
        )


@router.get(
    "",
    response_model=BasicResponse,
    responses={
        200: {"description": "Tokens retrieved successfully"},
        401: {"description": "Authentication required"},
        403: {"description": "Insufficient scopes"},
    },
    dependencies=[
        Depends(require_scopes_cached(APIScope.TOKEN_ADMIN)),
    ],
)
async def list_tokens(
    current_user: Annotated[UserResponse, Depends(get_current_user_unified_cached)],
    page: int = Query(1, ge=1, description="Page number to retrieve"),
    page_size: int = Query(20, ge=1, le=100, description="Number of tokens per page"),
    status_filter: str | None = Query(None, regex="^(active|expired|revoked)$", description="Filter by token status"),
) -> BasicResponse:
    """
    List all access tokens for the current user.

    Returns a paginated list of the user's access tokens with their metadata.
    Supports filtering by token status.

    **Required Scopes:** `token_admin`
    """
    token_page = await token_handler.get_user_tokens(
        user_id=str(current_user.id),
        page=page,
        page_size=page_size,
        status_filter=status_filter,
    )
    return BasicResponse(
        status="success",
        message="Get user tokens successfully",
        data=token_page.model_dump(),
    )


@router.get(
    "/{token_id}",
    response_model=BasicResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Token details retrieved successfully"},
        401: {"description": "Authentication required"},
        403: {"description": "Insufficient scopes"},
        404: {"description": "Token not found"},
    },
    dependencies=[
        Depends(require_scopes_cached(APIScope.TOKEN_ADMIN)),
    ],
)
async def get_token_details(
    token_id: str,
    response: Response,
    current_user: Annotated[UserResponse, Depends(get_current_user_unified_cached)],
) -> BasicResponse:
    """
    Retrieve details of a specific access token.

    Returns the full metadata for a single access token identified by its ID.

    **Required Scopes:** `token_admin`
    """
    try:
        token_details = await token_handler.get_token_details(token_id, str(current_user.id))
        return BasicResponse(
            data=token_details.model_dump(),
            status="success",
            message="Get token details successfully",
        )
    except ValueError as e:
        response.status_code = status.HTTP_404_NOT_FOUND
        return BasicResponse(
            status="failed",
            message=str(e),
        )


@router.delete(
    "/{token_id}/revoke",
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Token revoked successfully"},
        400: {"description": "Token already revoked"},
        401: {"description": "Authentication required"},
        403: {"description": "Insufficient scopes"},
        404: {"description": "Token not found"},
    },
    dependencies=[
        Depends(require_scopes_cached(APIScope.TOKEN_ADMIN, APIScope.TOKEN_ROTATE)),
    ],
)
async def revoke_token(
    token_id: str,
    response: Response,
    current_user: Annotated[UserResponse, Depends(get_current_user_unified_cached)],
) -> BasicResponse:
    """
    Revoke (deactivate) an access token.

    Revokes the specified token, making it unusable for API access.
    Revoked tokens can still be viewed but cannot be used for authentication.

    **Required Scopes:** `token_admin` OR `token_rotate`
    """
    is_revoke = await token_handler.revoke_token(token_id, str(current_user.id))
    if is_revoke:
        response.status_code = status.HTTP_200_OK
        return BasicResponse(
            message="Token revoked successfully",
            data=True,
            status="success",
        )

    response.status_code = status.HTTP_404_NOT_FOUND
    return BasicResponse(message="Token not found")


@router.delete(
    "/{token_id}",
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Token deleted successfully"},
        400: {"description": "Cannot delete active token"},
        401: {"description": "Authentication required"},
        403: {"description": "Insufficient scopes"},
        404: {"description": "Token not found"},
    },
    dependencies=[
        Depends(require_scopes_cached(APIScope.TOKEN_ADMIN)),
    ],
)
async def delete_token(
    token_id: str,
    response: Response,
    current_user: Annotated[UserResponse, Depends(get_current_user_unified_cached)],
) -> BasicResponse:
    """
    Delete an access token.

    Permanently deletes a token. Only revoked or expired tokens can be deleted.

    **Required Scopes:** `token_admin`
    """
    is_delete = await token_handler.delete_token(token_id, str(current_user.id))
    if is_delete:
        response.status_code = status.HTTP_200_OK
        return BasicResponse(
            message="Token deleted successfully",
            data=True,
            status="success",
        )

    response.status_code = status.HTTP_404_NOT_FOUND
    return BasicResponse(message="Token not found")


@router.get(
    "/statistics/dashboard",
    responses={
        200: {"description": "Token statistics retrieved successfully"},
        401: {"description": "Authentication required"},
        403: {"description": "Insufficient scopes"},
    },
)
async def get_token_statistics(
    current_user: Annotated[UserResponse, Depends(get_current_user_unified_cached)],
) -> BasicResponse:
    """
    Get token usage statistics for the dashboard.

    Returns statistics about the user's tokens including counts by status
    and usage metrics for dashboard display.

    **Required Scopes:** `token_admin`
    """
    stats = await token_handler.get_token_statistics(str(current_user.id))
    return BasicResponse(data=stats, status="success", message="Get token statistics successfully")
