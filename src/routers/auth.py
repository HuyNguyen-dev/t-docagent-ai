from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm

from handlers.auth import AuthHandler
from helpers.jwt_auth import get_current_user_scopes_unified, get_current_user_unified_cached
from schemas.response import BasicResponse
from schemas.user import LoginRequest, UserResponse

router = APIRouter(prefix="/auth")
auth_handler = AuthHandler()


@router.post("/login", status_code=status.HTTP_200_OK)
async def unified_login(
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    response: Response,
) -> BasicResponse:
    """
    Unified login endpoint supporting both OAuth2 form and JSON body formats.

    Supports two input formats:
    1. OAuth2 form: Content-Type: application/x-www-form-urlencoded
       username=user@example.com&password=password123

    2. JSON body: Content-Type: application/json
       {"email": "user@example.com", "password": "password123"}

    Returns JWT session tokens with user information.
    """
    content_type = request.headers.get("content-type", "").lower()

    try:
        if "application/json" in content_type:
            # Handle JSON body format
            body = await request.json()
            login_request = LoginRequest(**body)
            login_response = await auth_handler.login_unified(login_request.email, login_request.password)
        elif "application/x-www-form-urlencoded" in content_type:
            # Handle OAuth2 form format
            form = await request.form()
            username = form.get("username")
            password = form.get("password")

            if not username or not password:
                msg = "Missing username or password in form data"
                raise ValueError(msg)

            login_response = await auth_handler.login(form_data)
        else:
            msg = "Unsupported content type. Use 'application/json' or 'application/x-www-form-urlencoded'"
            raise ValueError(msg)

        # Set refresh token cookie
        response.set_cookie(
            key="refresh_token",
            value=login_response.refresh_token,
            httponly=True,
            secure=True,  # Use HTTPS in production
            samesite="strict",
            max_age=60 * 60 * 24 * 7,  # 7 days
        )

        # Return response without refresh_token in body
        return BasicResponse(
            status="success",
            message="Login successful.",
            data={
                "access_token": login_response.access_token,
                "token_type": login_response.token_type,
                "user": login_response.user.model_dump(),
            },
        )

    except ValueError as e:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return BasicResponse(
            status="failed",
            message=str(e),
        )
    except Exception:
        response.status_code = status.HTTP_401_UNAUTHORIZED
        return BasicResponse(
            status="failed",
            message="Login failed",
        )


@router.post(
    "/refresh",
    status_code=status.HTTP_200_OK,
    dependencies=[
        Depends(get_current_user_unified_cached),
    ],
)
async def refresh_access_token(
    response: Response,
    refresh_token: Annotated[str | None, Cookie()] = None,
) -> BasicResponse:
    """
    Refresh access token using refresh token from HttpOnly cookie.
    """
    try:
        refresh_response = await auth_handler.refresh_access_token(refresh_token)

        # Set new refresh token cookie
        response.set_cookie(
            key="refresh_token",
            value=refresh_response.refresh_token,
            httponly=True,
            secure=True,
            samesite="strict",
            max_age=60 * 60 * 24 * 7,  # 7 days
        )

        # Return response without refresh_token in body
        return BasicResponse(
            status="success",
            message="Token refreshed successfully.",
            data={
                "access_token": refresh_response.access_token,
                "token_type": refresh_response.token_type,
                "user": refresh_response.user.model_dump(),
            },
        )
    except Exception:
        response.status_code = status.HTTP_401_UNAUTHORIZED
        return BasicResponse(
            status="failed",
            message="Token refresh failed",
        )


@router.post(
    "/logout",
    dependencies=[
        Depends(get_current_user_unified_cached),
    ],
)
async def logout(response: Response) -> BasicResponse:
    """
    Logout user by clearing refresh token cookie.
    Note: JWT tokens cannot be invalidated server-side, they will expire naturally.
    """
    try:
        logout_response = await auth_handler.logout()

        # Clear refresh token cookie
        response.delete_cookie(
            key="refresh_token",
            httponly=True,
            secure=True,
            samesite="strict",
        )

        return BasicResponse(
            status="success",
            message="Logged out successfully.",
            data=logout_response.success,
        )
    except Exception:
        return BasicResponse(
            status="failed",
            message="Logout failed",
            data=False,
        )


@router.get("/me")
async def get_current_user_info(
    current_user: Annotated[UserResponse, Depends(get_current_user_unified_cached)],
) -> BasicResponse:
    """Get current user information from JWT session token or access token."""
    user_data = await auth_handler.get_current_user_info(current_user)
    return BasicResponse(
        status="success",
        data=user_data.model_dump(),
        message="User information retrieved successfully.",
    )


@router.get("/scopes")
async def get_access_token_scopes(
    user_scopes: Annotated[set[str], Depends(get_current_user_scopes_unified)],
) -> BasicResponse:
    """
    Get the scopes associated with the current access token.

    This endpoint returns a list of all API scopes that the current
    authenticated user's access token is authorized for, including
    inherited scopes based on their role.

    Returns:
        list[str]: A list of scope strings.
    """
    return BasicResponse(
        status="success",
        data=user_scopes,
        message="User information retrieved successfully.",
    )
