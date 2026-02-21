from typing import Annotated

import orjson
from fastapi import Depends, File, Form, HTTPException, Response, UploadFile, status
from fastapi.routing import APIRouter
from pydantic import ValidationError

from helpers.jwt_auth import require_scopes_cached
from initializer import ap_handler
from schemas.action_package import ActionPackageIDs, ActionPackageInput, ActionPackageUpdate
from schemas.response import BasicResponse
from utils.enums import APIScope

router = APIRouter(prefix="/action-package", dependencies=[])


@router.post(
    "/create/streamable-http",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_scopes_cached(APIScope.ACTION_PACKAGE_ADMIN)),
    ],
)
async def create_http_action_package(
    response: Response,
    action_package_input: ActionPackageInput,
) -> BasicResponse:
    """
    Create a new HTTP streamable action package.

    This endpoint allows for the creation of action packages that communicate over HTTP.

    **Required Scopes:** `action_package_admin`
    """
    action_package = await ap_handler.create_action_package(action_package_input=action_package_input)
    if action_package is None:
        resp = BasicResponse(
            status="failed",
            message="Create new action package failed",
            data=None,
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
    else:
        resp = BasicResponse(
            status="success",
            message="New action package created successfully",
            data=action_package.model_dump(),
        )
        response.status_code = status.HTTP_201_CREATED
    return resp


@router.post(
    "/create/stdio",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_scopes_cached(APIScope.ACTION_PACKAGE_ADMIN)),
    ],
)
async def create_stdio_action_package(
    response: Response,
    action_package_input: Annotated[str, Form(..., description="JSON string config MCP")],
    file_script: Annotated[UploadFile | None, File(description="File Script run MCP")] = None,
) -> BasicResponse:
    """
    Create a new stdio action package with an optional script file.

    This endpoint allows for the creation of action packages that communicate over standard I/O,
    and can include an associated script file.

    **Required Scopes:** `action_package_admin`
    """
    try:
        input_dict = orjson.loads(action_package_input)
        action_package_input = ActionPackageInput(**input_dict)
        action_package = await ap_handler.create_action_package(
            action_package_input=action_package_input,
            file_script=file_script,
        )
        if action_package is None:
            resp = BasicResponse(
                status="failed",
                message="Create new action package failed",
                data=None,
            )
            response.status_code = status.HTTP_400_BAD_REQUEST
        else:
            resp = BasicResponse(
                status="success",
                message="New action package created successfully",
                data=action_package.model_dump(),
            )
            response.status_code = status.HTTP_201_CREATED
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


@router.get(
    "/{ap_id}",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_scopes_cached(APIScope.ACTION_PACKAGE_READ)),
    ],
)
async def get_action_package_by_id(
    response: Response,
    ap_id: str,
) -> BasicResponse:
    """
    Retrieve an action package by its ID.

    Returns the details of a specific action package.

    **Required Scopes:** `action_package_read`
    """
    action_package = await ap_handler.get_action_package_by_id(ap_id=ap_id)
    if action_package is None:
        resp = BasicResponse(
            status="failed",
            message=f"Get action package failed with ap_id: {ap_id}",
            data=None,
        )
        response.status_code = status.HTTP_404_NOT_FOUND
    else:
        resp = BasicResponse(
            status="success",
            message="Get action package successfully",
            data=action_package.model_dump(),
        )
        response.status_code = status.HTTP_200_OK
    return resp


@router.put(
    "/{ap_id}/streamable-http",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_scopes_cached(APIScope.ACTION_PACKAGE_ADMIN)),
    ],
)
async def update_http_action_package(
    response: Response,
    ap_id: str,
    action_package_update: ActionPackageUpdate,
) -> BasicResponse:
    """
    Update an existing HTTP streamable action package.

    This endpoint allows for updating the configuration of an HTTP action package.

    **Required Scopes:** `action_package_admin`
    """
    updated_action_package = await ap_handler.update_action_package(
        ap_id=ap_id,
        action_package_update=action_package_update,
    )
    if updated_action_package is None:
        resp = BasicResponse(
            status="failed",
            message=f"Update action package failed with ap_id: {ap_id}",
            data=None,
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
    else:
        resp = BasicResponse(
            status="success",
            message="Action package updated successfully",
            data=updated_action_package.model_dump(),
        )
        response.status_code = status.HTTP_200_OK
    return resp


@router.put(
    "/{ap_id}/stdio",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_scopes_cached(APIScope.ACTION_PACKAGE_ADMIN)),
    ],
)
async def update_stdio_action_package(
    response: Response,
    ap_id: str,
    action_package_update: Annotated[str, Form(..., description="JSON string config MCP")],
    file_script: Annotated[UploadFile | None, File(description="File Script run MCP")] = None,
) -> BasicResponse:
    """
    Update an existing stdio action package with an optional script file.

    This endpoint allows for updating the configuration and optionally the script file
    of a stdio action package.

    **Required Scopes:** `action_package_admin`
    """
    try:
        input_dict = orjson.loads(action_package_update)
        action_package_update = ActionPackageUpdate(**input_dict)
        updated_action_package = await ap_handler.update_action_package(
            ap_id=ap_id,
            action_package_update=action_package_update,
            file_script=file_script,
        )
        if updated_action_package is None:
            resp = BasicResponse(
                status="failed",
                message=f"Update action package failed with ap_id: {ap_id}",
                data=None,
            )
            response.status_code = status.HTTP_400_BAD_REQUEST
        else:
            resp = BasicResponse(
                status="success",
                message="Action package updated successfully",
                data=updated_action_package.model_dump(),
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


@router.delete(
    "/{ap_id}",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_scopes_cached(APIScope.ACTION_PACKAGE_ADMIN)),
    ],
)
async def delete_action_package_by_id(
    response: Response,
    ap_id: str,
) -> BasicResponse:
    """
    Delete an action package by its ID.

    This endpoint allows for the permanent deletion of an action package.

    **Required Scopes:** `action_package_admin`
    """
    is_deleted = await ap_handler.delete_action_package_by_id(ap_id=ap_id)
    if not is_deleted:
        resp = BasicResponse(
            status="failed",
            message=f"Delete action package failed with ap_id: {ap_id}",
            data=None,
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
    else:
        resp = BasicResponse(
            status="success",
            message="Delete action package successfully",
            data=ap_id,
        )
        response.status_code = status.HTTP_200_OK
    return resp


@router.post(
    "/{ap_id}/refresh",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_scopes_cached(APIScope.ACTION_PACKAGE_ADMIN)),
    ],
)
async def refresh_action_package_connection(
    response: Response,
    ap_id: str,
) -> BasicResponse:
    """
    Refresh the connection for an action package.

    This endpoint attempts to refresh the underlying connection for a specified action package.

    **Required Scopes:** `action_package_admin`
    """
    details = await ap_handler.refresh_connection(ap_id=ap_id)
    if details is None:
        resp = BasicResponse(
            status="failed",
            message="Connection refresh failed",
            data=None,
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
    else:
        resp = BasicResponse(
            status="success",
            message="Connection refresh completed successfully",
            data=details.model_dump(),
        )
        response.status_code = status.HTTP_200_OK
    return resp


@router.post(
    "/refresh",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_scopes_cached(APIScope.ACTION_PACKAGE_ADMIN)),
    ],
)
async def refresh_list_action_packages(
    response: Response,
    action_package_ids: ActionPackageIDs,
) -> BasicResponse:
    """
    Refresh connections for a list of action packages.

    This endpoint attempts to refresh the underlying connections for multiple specified action packages.

    **Required Scopes:** `action_package_admin`
    """
    details = await ap_handler.refresh_list_action_package(ap_ids=action_package_ids.ap_ids)
    if not details:
        resp = BasicResponse(
            status="failed",
            message="Connection refresh failed for all packages",
            data=None,
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
    else:
        resp = BasicResponse(
            status="success",
            message="Connection refresh completed successfully",
            data=[d.model_dump() for d in details],
        )
        response.status_code = status.HTTP_200_OK
    return resp


@router.get(
    "",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_scopes_cached(APIScope.ACTION_PACKAGE_READ)),
    ],
)
async def get_all_action_packages(
    response: Response,
    q: str = "",
    page: int = 1,
    page_size: int = 10,
    filter_no_tools: bool = False,
) -> BasicResponse:
    """
    Retrieve a paginated list of all action packages.

    Supports searching by query, pagination, and filtering for packages with no tools.

    **Required Scopes:** `action_package_read`
    """
    page_data = await ap_handler.get_all_action_packages(
        q=q,
        page=page,
        page_size=page_size,
        filter_no_tools=filter_no_tools,
    )
    if page_data is None:
        resp = BasicResponse(
            status="failed",
            message="Get all action packages failed",
            data=None,
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
    else:
        resp = BasicResponse(
            status="success",
            message="Get all action packages successfully",
            data=page_data.model_dump(),
        )
        response.status_code = status.HTTP_200_OK
    return resp
