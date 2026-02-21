"""
Owner Onboarding and Authentication Router

This module provides API endpoints for system initialization and user authentication.
"""

from fastapi import Response, status
from fastapi.routing import APIRouter

from initializer import onboarding_handler
from schemas.response import BasicResponse
from schemas.user import (
    OwnerOnboardingRequest,
)

# Create router instance
router = APIRouter(prefix="/onboarding")


@router.get(
    "/status",
    response_model=BasicResponse,
    status_code=status.HTTP_200_OK,
    summary="Get System Status",
    tags=["System Onboarding"],
)
async def get_system_status(
    response: Response,
) -> BasicResponse:
    """
    Get the current system initialization status.

    This endpoint checks whether the system has been initialized with an owner account.
    It can be called without authentication to determine if onboarding is required.

    Returns:
        SystemStatusResponse: Current system status including initialization state
    """
    system_status = await onboarding_handler.get_system_status()
    if system_status is None:
        resp = BasicResponse(
            status="failed",
            message="Get system status failed",
            data=None,
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
    else:
        resp = BasicResponse(
            status="success",
            message="Get system status successfully",
            data=system_status.model_dump(),
        )
        response.status_code = status.HTTP_200_OK
    return resp


@router.post(
    "/initialize-owner",
    response_model=BasicResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Initialize Owner Account",
    tags=["System Onboarding"],
)
async def initialize_owner(
    onboarding_request: OwnerOnboardingRequest,
) -> BasicResponse:
    """
    Create the first owner account for system initialization.

    This endpoint is used to set up the initial owner account when the system
    is first deployed. It can only be used when no owner account exists.

    Args:
        onboarding_request: Owner account details including email, name, and password

    Returns:
        BasicResponse: Created owner user details

    Raises:
        HTTPException 409: If system already has an owner account
        HTTPException 422: If validation fails (email format, password strength, etc.)
        HTTPException 500: If account creation fails
    """
    # Validate the request
    await onboarding_handler.validate_onboarding_request(onboarding_request)

    # Create the owner account
    user_data = await onboarding_handler.onboard_owner(onboarding_request)

    return BasicResponse(
        status="success",
        data=user_data.model_dump(),
        message="Owner account created successfully. Please login to access the system.",
    )
