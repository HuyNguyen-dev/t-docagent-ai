from fastapi import Depends, Response, status
from fastapi.routing import APIRouter

from helpers.jwt_auth import require_scopes_cached
from initializer import scope_handler
from schemas.response import BasicResponse
from utils.enums import APIScope

router = APIRouter(prefix="/scopes", dependencies=[])


@router.get(
    "",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_scopes_cached(APIScope.USER_ADMIN)),
    ],
)
def get_all_scopes(
    response: Response,
) -> BasicResponse:
    """
    Retrieve all available API scopes.

    This endpoint returns a list of all defined API scopes within the system.

    **Required Scopes:** `user_admin`
    """
    scopes = scope_handler.get_all_scopes()
    if scopes is None:
        resp = BasicResponse(
            status="failed",
            message="Failed to retrieve scopes",
            data=None,
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
    else:
        resp = BasicResponse(
            status="success",
            message="Successfully retrieved all scopes",
            data=scopes,
        )
        response.status_code = status.HTTP_200_OK
    return resp
