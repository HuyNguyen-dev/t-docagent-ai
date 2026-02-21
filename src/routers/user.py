from typing import Annotated

from fastapi import Depends, Query, Response, status
from fastapi.routing import APIRouter

from helpers.jwt_auth import get_current_user_unified_cached, require_any_scope_cached
from initializer import user_handler
from schemas.response import BasicResponse
from schemas.user import (
    UserCreateRequest,
    UserPasswordUpdateRequest,
    UserResponse,
    UserUpdateRequest,
)
from utils.enums import APIScope

router = APIRouter(prefix="/users")


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "User created successfully"},
        400: {"description": "User already exists or invalid data"},
        401: {"description": "Authentication required"},
        403: {"description": "Insufficient scopes"},
        500: {"description": "Failed to send invitation email"},
    },
    dependencies=[
        Depends(require_any_scope_cached(APIScope.USER_ADMIN)),
    ],
)
async def create_user(
    user_request: UserCreateRequest,
    response: Response,
    current_user: Annotated[UserResponse, Depends(get_current_user_unified_cached)],
) -> BasicResponse | None:
    """
    Create a new user (send invitation).

    Creates a new user account and sends an invitation email.
    Only users with administrative privileges can create other users.

    **Required Scopes:** `user_admin`
    """
    try:
        user_response = await user_handler.create_user(user_request, str(current_user.id))
        if user_response is None:
            response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
            return None

        return BasicResponse(
            status="success",
            data=user_response.model_dump(),
            message="Create new user successfully",
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
        200: {"description": "Users retrieved successfully"},
        401: {"description": "Authentication required"},
        403: {"description": "Insufficient scopes"},
    },
    dependencies=[
        Depends(require_any_scope_cached(APIScope.USER_ADMIN)),
    ],
)
async def list_users(
    page: int = Query(1, ge=1, description="Page number to retrieve"),
    page_size: int = Query(10, ge=1, le=100, description="Number of users per page"),
    role_filter: list[str] = Query(description="Filter by role", default_factory=list),
    status_filter: list[str] = Query(description="Filter by status", default_factory=list),
    q: str = Query(description="Search in name, email, or role", default=""),
) -> BasicResponse:
    """
    List all users in the system.

    Returns a paginated list of users with filtering options.
    Supports searching by name, email, or role.

    **Required Scopes:** `user_admin`
    """
    user_page = await user_handler.get_users(
        page=page,
        page_size=page_size,
        role_filter=role_filter,
        status_filter=status_filter,
        q=q,
    )
    return BasicResponse(
        status="success",
        data=user_page.model_dump(),
        message="Fetch all users successfully",
    )


@router.put(
    "/{user_id}",
    response_model=BasicResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "User updated successfully"},
        400: {"description": "Cannot modify owner or invalid data"},
        401: {"description": "Authentication required"},
        403: {"description": "Insufficient scopes"},
        404: {"description": "User not found"},
    },
    dependencies=[
        Depends(require_any_scope_cached(APIScope.USER_ADMIN)),
    ],
)
async def update_user(
    user_id: str,
    response: Response,
    user_update: UserUpdateRequest,
    current_user: Annotated[UserResponse, Depends(get_current_user_unified_cached)],
) -> BasicResponse:
    """
    Update an existing user's information.

    Allows modification of user details such as name, email, and roles.
    The owner account cannot be modified via this endpoint.

    **Required Scopes:** `user_admin`
    """
    try:
        user_response = await user_handler.update_user(user_id, user_update, str(current_user.id))
        return BasicResponse(
            status="success",
            data=user_response.model_dump(),
            message="Update user successfully",
        )
    except ValueError as e:
        response.status_code = status.HTTP_404_NOT_FOUND
        return BasicResponse(
            status="failed",
            message=str(e),
        )


@router.put(
    "/update/password",
    response_model=BasicResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Password updated successfully"},
        401: {"description": "Authentication required"},
        403: {"description": "Insufficient permissions"},
        404: {"description": "User not found"},
    },
)
async def update_password(
    response: Response,
    password_update: UserPasswordUpdateRequest,
    current_user: Annotated[UserResponse, Depends(get_current_user_unified_cached)],
) -> BasicResponse:
    """
    Update a user's password.

    - An **owner** can update the password for any user (except other owners).
    - A non-owner user can only update their own password.

    **Required Scopes:** None (authentication is required, authorization is handled internally)
    """
    success = await user_handler.update_password(password_update, current_user)
    if not success:
        response.status_code = status.HTTP_404_NOT_FOUND
        return BasicResponse(message="User not found")

    return BasicResponse(
        status="success",
        message="User password updated successfully",
        data=True,
    )


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "User deleted successfully"},
        400: {"description": "Cannot delete owner"},
        401: {"description": "Authentication required"},
        403: {"description": "Insufficient scopes"},
        404: {"description": "User not found"},
    },
    dependencies=[
        Depends(require_any_scope_cached(APIScope.API)),
    ],
)
async def delete_user(
    user_id: str,
    response: Response,
    current_user: Annotated[UserResponse, Depends(get_current_user_unified_cached)],
) -> BasicResponse:
    """
    Delete a user from the system.

    Permanently removes the user account. Owner users cannot be deleted.

    **Required Scopes:** `user_admin`
    """
    is_delete = await user_handler.delete_user(user_id, str(current_user.id))
    if not is_delete:
        response.status_code = status.HTTP_404_NOT_FOUND
        return BasicResponse(message="User not found")

    return BasicResponse(
        status="success",
        data=True,
        message="Delete user successfully",
    )


@router.get(
    "/statistics/dashboard",
    responses={
        200: {"description": "User statistics retrieved successfully"},
        401: {"description": "Authentication required"},
        403: {"description": "Insufficient scopes"},
    },
    dependencies=[
        Depends(require_any_scope_cached(APIScope.USER_ADMIN)),
    ],
)
async def get_user_statistics() -> BasicResponse:
    """
    Get user statistics for the dashboard.

    Returns statistics about users including counts by role and status.

    **Required Scopes:** `user_admin`
    """
    stats = await user_handler.get_user_statistics()
    return BasicResponse(
        data=stats.model_dump(),
        status="success",
        message="Get user statistics successfully",
    )


@router.put(
    "/{user_id}/reset-password",
    response_model=BasicResponse,
    responses={
        200: {"description": "Password reset successfully"},
        401: {"description": "Authentication required"},
        403: {"description": "Insufficient scopes"},
        404: {"description": "User not found"},
        500: {"description": "Failed to reset password"},
    },
    dependencies=[
        Depends(require_any_scope_cached(APIScope.USER_ADMIN)),
    ],
)
async def reset_user_password(
    user_id: str,
    response: Response,
    current_user: UserResponse = Depends(get_current_user_unified_cached),
) -> BasicResponse:
    """
    Reset user password and send a new password via email.

    **Required Scopes:** `api` (Only Owner)
    """
    try:
        reset_response = await user_handler.reset_password(user_id, str(current_user.id))
        return BasicResponse(
            status="success",
            data=reset_response.model_dump(),
            message="Password reset successfully and new password sent to user email",
        )
    except ValueError as e:
        response.status_code = status.HTTP_404_NOT_FOUND
        return BasicResponse(
            status="failed",
            message=str(e),
        )
