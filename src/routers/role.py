from typing import Annotated

from fastapi import APIRouter, Body, Depends, Response, status

from helpers.jwt_auth import get_current_user_unified_cached, require_any_scope_cached, require_scopes_cached
from initializer import role_handler
from schemas.response import BasicResponse
from schemas.user import RoleCreateRequest, UserResponse
from utils.enums import APIScope

router = APIRouter(prefix="/roles")


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "Role created successfully"},
        400: {"description": "Role already exists or invalid data"},
        401: {"description": "Authentication required"},
        403: {"description": "Insufficient scopes"},
    },
    dependencies=[
        Depends(require_scopes_cached(APIScope.API)),
    ],
)
async def create_role(
    role_request: RoleCreateRequest,
    current_user: Annotated[UserResponse, Depends(get_current_user_unified_cached)],
) -> BasicResponse:
    """
    Create a new custom role.

    **Required Scopes:** `api` (Owner only)
    """
    resp = await role_handler.create_role(role_request, str(current_user.id))
    return BasicResponse(
        data=resp.model_dump(),
        status="success",
        message="Create new a role successfully",
    )


@router.get(
    "",
    responses={
        200: {"description": "Roles retrieved successfully"},
        401: {"description": "Authentication required"},
        403: {"description": "Insufficient scopes"},
    },
    dependencies=[
        Depends(require_any_scope_cached(APIScope.API)),
    ],
)
async def list_roles() -> BasicResponse:
    """
    List all roles.

    **Required Scopes:** `api` (Owner only)
    """
    roles = await role_handler.get_roles()
    return BasicResponse(
        data=roles.model_dump()["roles"],
        status="success",
        message="Fetch all roles successfully",
    )


@router.get(
    "/names",
    responses={
        200: {"description": "Role names retrieved successfully"},
        401: {"description": "Authentication required"},
        403: {"description": "Insufficient scopes"},
    },
    dependencies=[
        Depends(require_any_scope_cached(APIScope.USER_ADMIN)),
    ],
)
async def list_role_names(include_owner: bool = False) -> BasicResponse:
    """
    Get all role names

    **Required Scopes:** `user_admin`
    """
    role_names = await role_handler.get_all_role_names(include_owner)
    return BasicResponse(
        data=role_names,
        status="success",
        message="Fetch all role names successfully",
    )


@router.put(
    "/{role_id}/scopes",
    responses={
        200: {"description": "Role scopes updated successfully"},
        400: {"description": "Role not found or invalid data"},
        401: {"description": "Authentication required"},
        403: {"description": "Insufficient scopes"},
    },
    dependencies=[
        Depends(require_scopes_cached(APIScope.API)),
    ],
)
async def update_role_scopes(
    role_id: str,
    current_user: Annotated[UserResponse, Depends(get_current_user_unified_cached)],
    scopes: Annotated[list[str], Body(..., embed=True, description="List of new scopes for the role")],
) -> BasicResponse:
    """
    Update the scopes of a custom role by its ID.
    Only the scopes field can be updated.

    **Required Scopes:** `api` (Owner only)
    """
    updated_role = await role_handler.update_role_scopes(role_id, scopes, str(current_user.id))
    return BasicResponse(
        data=updated_role.model_dump(),
        status="success",
        message="Update a role successfully",
    )


@router.delete(
    "/{role_id}",
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Role deleted successfully"},
        400: {"description": "Role is in use and cannot be deleted"},
        401: {"description": "Authentication required"},
        403: {"description": "Insufficient scopes"},
        404: {"description": "Role not found"},
    },
    dependencies=[
        Depends(require_scopes_cached(APIScope.API)),
    ],
)
async def delete_role(
    role_id: str,
    response: Response,
    current_user: Annotated[UserResponse, Depends(get_current_user_unified_cached)],
) -> BasicResponse:
    """
    Delete a role.

    **Required Scopes:** `api` (Owner only)
    """
    is_delete = await role_handler.delete_role(role_id, str(current_user.id))
    if not is_delete:
        response.status_code = status.HTTP_404_NOT_FOUND
        return BasicResponse(message="Custom role not found")
    return BasicResponse(
        data=True,
        message="Custom role deleted successfully",
        status="success",
    )
