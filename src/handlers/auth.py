from fastapi import HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from helpers.jwt_auth import authenticate_user, create_session_tokens, refresh_jwt_token, validate_jwt_token
from models.user import User
from schemas.auth import LoginResponse, LogoutResponse, TokenRefreshResponse
from schemas.user import UserResponse
from utils.auth import get_user_permissions
from utils.enums import UserStatus
from utils.logger.custom_logging import LoggerMixin


class AuthHandler(LoggerMixin):
    """Authentication handler for JWT session tokens and access token support."""

    async def login(
        self,
        form_data: OAuth2PasswordRequestForm,
    ) -> LoginResponse:
        """
        Login with username/password and receive JWT session tokens.
        Returns login data including tokens and user information.
        """
        # Authenticate user
        user = await authenticate_user(form_data.username, form_data.password)
        if not user:
            self.logger.warning(
                'event=login-failed message="Login attempt failed for email: %s"',
                form_data.username,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
            )

        # Create JWT session tokens
        await user.set({"status": UserStatus.ACTIVE})
        tokens = await create_session_tokens(user)
        user_scopes = await get_user_permissions(user_role=user.role)
        user_response = UserResponse(**user.model_dump())
        user_response.scopes = list(user_scopes)

        self.logger.info(
            'event=user-login-success message="User logged in successfully: %s"',
            user.email,
        )

        return LoginResponse(
            access_token=tokens["access_token"],
            refresh_token=tokens["refresh_token"],
            token_type="Bearer",  # noqa: S106
            user=user_response,
        )

    async def login_unified(
        self,
        email: str,
        password: str,
    ) -> LoginResponse:
        """
        Unified login method that accepts email and password directly.
        Used by the unified login endpoint that supports both OAuth2 form and JSON body.
        """
        # Authenticate user
        user = await authenticate_user(email, password)
        if not user:
            self.logger.warning(
                'event=login-failed message="Login attempt failed for email: %s"',
                email,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
            )

        # Create JWT session tokens
        await user.set({"status": UserStatus.ACTIVE})
        tokens = await create_session_tokens(user)
        user_scopes = await get_user_permissions(user_role=user.role)
        user_response = UserResponse(**user.model_dump())
        user_response.scopes = list(user_scopes)

        self.logger.info(
            'event=user-login-success message="User logged in successfully: %s"',
            user.email,
        )

        return LoginResponse(
            access_token=tokens["access_token"],
            refresh_token=tokens["refresh_token"],
            token_type="Bearer",  # noqa: S106
            user=user_response,
        )

    async def refresh_access_token(
        self,
        refresh_token: str | None = None,
    ) -> TokenRefreshResponse:
        """
        Refresh access token using refresh token.
        """
        if not refresh_token:
            self.logger.warning('event=refresh-token-missing message="Refresh token not provided"')
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token not found",
            )

        # Refresh tokens
        tokens = await refresh_jwt_token(refresh_token)

        # Get user info for response
        jwt_payload = await validate_jwt_token(tokens["access_token"])
        user = await User.get(jwt_payload["user_id"])
        user_response = UserResponse(**user.model_dump())

        self.logger.info(
            'event=token-refresh-success message="Token refreshed for user: %s"',
            user.email,
        )
        return TokenRefreshResponse(
            access_token=tokens["access_token"],
            refresh_token=tokens["refresh_token"],
            token_type="Bearer",  # noqa: S106
            user=user_response,
        )

    async def logout(self) -> LogoutResponse:
        """
        Logout user.
        Note: JWT tokens cannot be invalidated server-side, they will expire naturally.
        """
        self.logger.info('event=user-logout message="User logged out"')
        return LogoutResponse(success=True)

    async def get_current_user_info(self, current_user: UserResponse) -> UserResponse:
        """Get current user information from JWT session token or access token."""
        return current_user
