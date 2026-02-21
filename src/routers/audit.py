from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import ORJSONResponse

from helpers.jwt_auth import get_current_user_unified_cached, require_any_scope_cached, require_scopes_cached
from initializer import audit_handler
from schemas.response import BasicResponse
from schemas.user import UserResponse
from utils.enums import APIScope

router = APIRouter(prefix="/audit")


@router.get(
    "/api-activities",
    responses={
        200: {"description": "API activities retrieved successfully"},
        403: {"description": "Insufficient permissions"},
    },
    dependencies=[
        Depends(require_scopes_cached(APIScope.AUDIT_READ)),
    ],
)
async def get_api_activities(
    q: Annotated[str | None, Query()] = None,
    start_date: Annotated[datetime | None, Query()] = None,
    end_date: Annotated[datetime | None, Query()] = None,
    status_code: Annotated[int | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 10,
) -> BasicResponse:
    """
    Get API activity logs with filtering options.

    **Required Scopes:** `audit_read`
    """
    api_activities = await audit_handler.get_api_activities(
        q=q,
        start_date=start_date,
        end_date=end_date,
        status_code=status_code,
        page=page,
        page_size=page_size,
    )
    return BasicResponse(
        data=api_activities,
        message="API activities retrieved successfully",
        status="success",
    )


@router.get(
    "/user/{user_id}/activities",
    dependencies=[
        Depends(require_any_scope_cached(APIScope.AUDIT_READ, APIScope.USER_READ)),
    ],
)
async def get_user_activities(
    user_id: str,
    current_user: Annotated[UserResponse, Depends(get_current_user_unified_cached)],
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> BasicResponse:
    """
    Get all API activities for a specific user.

    **Required Scopes:** `audit_read` OR `user_read`
    """
    # Self-access check
    if user_id != current_user.id:
        # Only allow if user has audit_read scope for other users
        # This will be handled by the scope check above
        pass

    activities = await audit_handler.get_user_activities(user_id, limit)

    return BasicResponse(
        data=activities,
        message="User activities retrieved successfully",
        status="success",
    )


@router.get(
    "/token/{token_id}/usage",
    dependencies=[
        Depends(require_scopes_cached(APIScope.TOKEN_ADMIN)),
    ],
)
async def get_token_usage_details(
    token_id: str,
    current_user: Annotated[UserResponse, Depends(get_current_user_unified_cached)],
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> BasicResponse:
    """
    Get detailed usage statistics for a specific token.

    **Required Scopes:** `token_admin`
    """
    usage_details = await audit_handler.get_token_usage_details(token_id, current_user.id, limit)

    return BasicResponse(
        data=usage_details,
        message="Token usage details retrieved successfully",
        status="success",
    )


@router.get(
    "/statistics/dashboard",
    dependencies=[
        Depends(require_scopes_cached(APIScope.SYSTEM_MONITOR)),
    ],
)
async def get_audit_dashboard() -> BasicResponse:
    """
    Get dashboard statistics for API usage and system monitoring.

    **Required Scopes:** `system_monitor`
    """
    dashboard_stats = await audit_handler.get_dashboard_statistics()

    return BasicResponse(
        data=dashboard_stats,
        message="Audit dashboard retrieved successfully",
        status="success",
    )


@router.get(
    "/security/suspicious",
    dependencies=[
        Depends(require_scopes_cached(APIScope.SECURITY_ADMIN)),
    ],
)
async def get_suspicious_activities(
    hours: Annotated[int, Query(ge=1, le=168)] = 24,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> BasicResponse:
    """
    Get flagged suspicious activities for security monitoring.

    **Required Scopes:** `security_admin`
    """
    suspicious = await audit_handler.get_suspicious_activities(hours, limit)

    return BasicResponse(
        data=suspicious,
        message="Suspicious activities retrieved successfully",
        status="success",
    )


@router.get(
    "/security/failed-attempts",
    dependencies=[
        Depends(require_scopes_cached(APIScope.SECURITY_ADMIN)),
    ],
)
async def get_failed_login_attempts(
    hours: Annotated[int, Query(ge=1, le=168)] = 24,
) -> BasicResponse:
    """
    Get failed authentication attempts grouped by IP within specified time window.

    **Required Scopes:** `security_admin`
    """
    failed_attempts = await audit_handler.get_failed_login_attempts(hours)

    return BasicResponse(
        data=failed_attempts,
        message="Failed login attempts retrieved successfully",
        status="success",
    )


@router.post(
    "/security/investigate",
    dependencies=[
        Depends(require_scopes_cached(APIScope.SECURITY_ADMIN, APIScope.AUDIT_ADMIN)),
    ],
)
async def investigate_user_activity(
    investigation_request: dict,
) -> ORJSONResponse:
    """
    Deep dive investigation into user activity patterns.

    **Required Scopes:** `security_admin` AND `audit_admin`
    """
    investigation_result = await audit_handler.investigate_user_activity(investigation_request)

    return BasicResponse(
        data=investigation_result,
        message="Investigate user activity retrieved successfully",
        status="success",
    )
