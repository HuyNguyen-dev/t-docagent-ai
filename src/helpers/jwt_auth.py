import re
from collections.abc import Callable
from datetime import datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext

from config import settings
from initializer import logger_instance
from models.user import User
from schemas.user import UserResponse
from utils.auth import expand_scopes, get_user_permissions, has_required_scopes, validate_access_token
from utils.constants import TIMEZONE
from utils.enums import APIScope

logger = logger_instance.get_logger(__name__)

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()


def create_jwt_token(data: dict, expires_delta: timedelta) -> str:
    """Create JWT token with expiration."""
    to_encode = data.copy()
    expire = datetime.now(TIMEZONE) + expires_delta
    to_encode.update(
        {
            "created_at": datetime.now(TIMEZONE).isoformat(),
            "exp": expire,
            "token_type": "session",  # Mark as session token
        },
    )
    return jwt.encode(to_encode, settings.AUTH_SECRET_KEY, algorithm=settings.AUTH_ALGORITHM)


async def authenticate_user(email: str, password: str) -> User | None:
    """Authenticate user with email and password."""
    try:
        user = await User.find_one(User.email == email)
        if user is None or not user.password_hash:
            logger.warning(
                "event=user-authentication-failed "
                'message="Failed login attempt for email: %s - user not found or no password hash"',
                email,
            )
            return None

        # Verify password against password_hash
        if not pwd_context.verify(password, user.password_hash):
            logger.warning(
                'event=user-authentication-failed message="Failed login attempt for email: %s - invalid password"',
                email,
            )
            return None
        if not user.is_active:
            logger.warning(
                'event=inactive-user-login-attempt message="Inactive user attempted login: %s"',
                email,
            )
            return None
        logger.info(
            'event=user-authentication-success message="User authenticated successfully: %s"',
            email,
        )
    except Exception:
        logger.exception(
            'event=user-authentication-error message="Authentication error for email: %s"',
            email,
        )
        return None
    return user


async def create_session_tokens(user: User) -> dict:
    """Create JWT session tokens (access + refresh) for user login."""

    # Calculate user permissions based on role and additional scopes
    user_permissions = await get_user_permissions(user.role)

    token_data = {
        "user_id": str(user.id),
        "email": user.email,
        "role": user.role,
        "scopes": list(user_permissions),  # Include all user permissions in JWT
    }

    access_token = create_jwt_token(
        data=token_data,
        expires_delta=timedelta(hours=settings.AUTH_ACCESS_TOKEN_EXPIRE_HOURS),
    )

    refresh_token = create_jwt_token(
        data=token_data,
        expires_delta=timedelta(hours=settings.AUTH_REFRESH_TOKEN_EXPIRE_HOURS),
    )

    logger.info(
        'event=session-tokens-created message="Session tokens created for user: %s"',
        user.email,
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
    }


async def validate_jwt_token(token: str) -> dict | None:
    """Validate JWT token and return payload if valid."""
    try:
        # Remove Bearer prefix if present
        origin_token = re.search(r"^Bearer (.*)$", token)
        if origin_token is not None:
            token = origin_token.group(1)

        # Basic format validation - JWT should have 3 parts
        if not _is_jwt_format(token):
            logger.warning(
                'event=jwt-token-invalid message="Invalid JWT format - expected 3 segments separated by dots"',
            )
            return None

        # Decode and validate JWT
        payload = jwt.decode(token, settings.AUTH_SECRET_KEY, algorithms=[settings.AUTH_ALGORITHM])

        # Verify required fields
        required_fields = ["user_id", "email", "role", "scopes", "token_type"]
        missing_fields = [field for field in required_fields if field not in payload]
        if missing_fields:
            logger.warning(
                'event=jwt-token-validation-failed message="JWT token missing required fields: %s"',
                ", ".join(missing_fields),
            )
            return None

        # Verify it's a session token
        if payload.get("token_type") != "session":
            logger.warning(
                'event=jwt-token-validation-failed message="Invalid token type: %s, expected: session"',
                payload.get("token_type"),
            )
            return None

        # Verify user still exists and is active
        user = await User.get(payload["user_id"])
        if not user or not user.is_active:
            logger.warning(
                'event=jwt-token-validation-failed message="User not found or inactive: %s"',
                payload["user_id"],
            )
            return None

        # Verify role hasn't changed
        if payload["role"] != user.role:
            logger.warning(
                'event=jwt-token-validation-failed message="User role changed since token creation: %s (token: %s, current: %s)"',
                payload["user_id"],
                payload["role"],
                user.role,
            )
            return None

        logger.debug(
            'event=jwt-token-validation-success message="JWT token validated successfully for user: %s"',
            payload["user_id"],
        )
    except jwt.ExpiredSignatureError:
        logger.warning('event=jwt-token-expired message="JWT token has expired"')
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(
            'event=jwt-token-invalid message="Invalid JWT token: %s"',
            str(e),
        )
        return None
    except Exception:
        logger.exception(
            'event=jwt-token-validation-error message="JWT token validation error"',
        )
        return None
    return payload


async def refresh_jwt_token(refresh_token: str) -> dict:
    """Refresh JWT access token using refresh token."""
    payload = await validate_jwt_token(refresh_token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Get fresh user data
    user = await User.get(payload["user_id"])
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    # Create new tokens with fresh data
    return await create_session_tokens(user)


def _is_jwt_format(token: str) -> bool:
    """Check if token looks like a JWT (has 3 parts separated by dots)."""
    return len(token.split(".")) == 3


async def get_current_user_from_jwt_or_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> tuple[UserResponse, set[str]]:
    """
    Get current user and scopes from either JWT session token or stored access token.
    Returns tuple of (user, scopes).
    """
    token = credentials.credentials

    # Detect token format and validate accordingly
    if _is_jwt_format(token):
        # Token looks like JWT - validate as JWT session token
        logger.debug('event=token-validation message="Validating as JWT session token"')
        jwt_payload = await validate_jwt_token(token)
        if jwt_payload:
            # JWT session token - get user and return their scopes from token
            user = await User.get(jwt_payload["user_id"])
            if user and user.is_active:
                user_response = UserResponse(**user.model_dump())
                jwt_scopes = set(jwt_payload.get("scopes", []))

                user_permissions = await get_user_permissions(user.role)
                if APIScope.API in user_permissions or APIScope.API in jwt_scopes:
                    scopes = {APIScope.API}
                else:
                    scopes = user_permissions.intersection(set(jwt_scopes))
                return user_response, scopes

        # JWT format but invalid - reject immediately
        logger.warning(
            'event=jwt-token-rejected message="JWT token format detected but validation failed"',
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid JWT token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Token doesn't look like JWT - validate as stored access token
    logger.debug('event=token-validation message="Validating as stored access token"')
    token_data = await validate_access_token(token)
    if token_data:
        user = await User.get(token_data["user_id"])
        if user and user.is_active:
            user_response = UserResponse(**user.model_dump())
            token_scopes = token_data.get("scopes", [])
            token_scopes = [APIScope(s) for s in token_scopes]
            scopes = expand_scopes(token_scopes)

            return user_response, scopes

    # Stored token format but invalid - reject
    logger.warning(
        'event=stored-token-rejected message="Stored access token validation failed"',
    )
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid access token",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user_scopes_unified(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> set[str]:
    """Get current user scopes from either JWT or access token."""
    _, scopes = await get_current_user_from_jwt_or_token(credentials)
    return scopes


async def get_current_user_unified(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> UserResponse:
    """Get current user from either JWT or access token."""
    user, _ = await get_current_user_from_jwt_or_token(credentials)
    return user


# Enhanced functions with caching support
async def get_current_user_unified_cached(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> UserResponse:
    """
    Get current user with caching from middleware.
    No duplicate DB queries!
    """

    # Check if middleware cached user info
    if hasattr(request.state, "cached_user") and hasattr(request.state, "auth_validated") and request.state.auth_validated:
        # Use cached user from middleware
        cached_user = request.state.cached_user
        return UserResponse(**cached_user.model_dump())

    # Fallback: Original logic if no cache
    logger.warning('event=cache-miss-user message="Cache miss in get_current_user_unified_cached"')
    user, _ = await get_current_user_from_jwt_or_token(credentials)
    return UserResponse(**user.model_dump())


async def get_current_user_scopes_unified_cached(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> set[APIScope]:
    """Get user scopes with caching."""

    # Use cached scopes if available
    if hasattr(request.state, "cached_user_scopes") and hasattr(request.state, "auth_validated") and request.state.auth_validated:
        cached_scopes = request.state.cached_user_scopes
        return {APIScope(scope) for scope in cached_scopes if scope in APIScope}

    # Fallback: Original logic
    logger.warning('event=cache-miss-scopes message="Cache miss in get_current_user_scopes_unified_cached"')
    return await get_current_user_scopes_unified(credentials)


def require_scopes_cached(*required_scopes: APIScope) -> Callable:
    """
    Enhanced scope checking with cached data and audit tracking.
    """

    def scope_dependency(
        request: Request,
        user_scopes: set[APIScope] = Depends(get_current_user_scopes_unified_cached),
    ) -> None:
        if not has_required_scopes(user_scopes, list(required_scopes)):
            # Log the scope violation for audit
            if hasattr(request.state, "request_id"):
                request.state.scope_violation = {
                    "required": [scope.value for scope in required_scopes],
                    "available": [scope.value for scope in user_scopes],
                }

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have the necessary permissions to access this feature. "
                "Please contact your administrator to request the following permissions: "
                f"{[scope.value for scope in required_scopes]}",
            )

        # Track successful scope usage for audit
        if hasattr(request.state, "request_id"):
            request.state.scopes_successfully_used = [scope.value for scope in required_scopes]

    return scope_dependency


def require_any_scope_cached(*required_scopes: APIScope) -> Callable:
    """
    Enhanced ANY scope checking with cached data and audit tracking.
    """

    def scope_dependency(
        request: Request,
        user_scopes: set[APIScope] = Depends(get_current_user_scopes_unified_cached),
    ) -> None:
        if APIScope.API not in user_scopes and not any(scope in user_scopes for scope in required_scopes):
            # Log the scope violation for audit
            if hasattr(request.state, "request_id"):
                request.state.scope_violation = {
                    "required": [scope.value for scope in required_scopes],
                    "available": [scope.value for scope in user_scopes],
                }

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have the necessary permissions to access this feature. "
                "Please contact your administrator to have any scope in "
                f"{[scope.value for scope in required_scopes]}",
            )

        # Track successful scope usage for audit
        if hasattr(request.state, "request_id"):
            used_scopes = [scope for scope in required_scopes if scope in user_scopes]
            request.state.scopes_successfully_used = [scope.value for scope in used_scopes]

    return scope_dependency
