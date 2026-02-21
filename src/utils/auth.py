import hashlib
import secrets
from datetime import datetime

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from models import Role, Token, User
from utils.constants import ROLE_SCOPES, SCOPE_INHERITANCE, TIMEZONE
from utils.enums import APIScope, UserRole

# Security instance for token extraction
security = HTTPBearer()


def expand_scopes(scopes: set[APIScope]) -> set[APIScope]:
    """
    Expand scopes to include inherited scopes.
    """
    expanded = set(scopes)

    for scope in scopes:
        if scope in SCOPE_INHERITANCE:
            if SCOPE_INHERITANCE[scope] == "all":
                # Return all available scopes
                return set(ROLE_SCOPES[UserRole.OWNER])
            expanded.update(SCOPE_INHERITANCE[scope])

    return expanded


def generate_token() -> str:
    """
    Generate a secure random token.
    """
    return f"sk_{secrets.token_urlsafe(32)}"


def hash_token(token: str) -> str:
    """
    Create SHA256 hash of token for secure storage.
    """
    return hashlib.sha256(token.encode()).hexdigest()


async def get_user_permissions(user_role: str) -> set[APIScope]:
    """
    Calculate final user permissions by get role scopes and expand scopes.
    """
    role_db = await Role.find_one(Role.name == user_role)
    role_scopes = {APIScope(scope) for scope in role_db.scopes}
    if not role_db:
        role_scopes = set()
    return expand_scopes(role_scopes)


def has_required_scopes(user_scopes: set[APIScope], required_scopes: list[APIScope]) -> bool:
    """
    Check if user has all required scopes.
    """
    # If user has 'api' scope, they have access to everything
    if APIScope.API in user_scopes:
        return True

    # Check if user has all required scopes
    return all(scope in user_scopes for scope in required_scopes)


async def validate_access_token(token: str) -> dict | None:
    """
    Validate access token and return token data if valid.
    """
    try:
        token_hash = hash_token(token)
        token_doc = await Token.find_one(
            Token.token_hash == token_hash,
            Token.is_active == True,  # noqa: E712
        )

        if not token_doc:
            return None

        # Check if token is expired
        if token_doc.expires_at and token_doc.expires_at.astimezone(TIMEZONE) < datetime.now(TIMEZONE):
            # Mark token as inactive
            await token_doc.set({Token.is_active: False})
            return None

        # Update last used timestamp
        await token_doc.set({Token.last_used_at: datetime.now(TIMEZONE)})

        return {
            "token_id": str(token_doc.id),
            "user_id": token_doc.user_id,
            "scopes": token_doc.scopes,
        }
    except Exception:
        return None


async def get_user_by_id(user_id: str) -> User | None:
    """
    Get user by ID.
    """
    try:
        return await User.get(user_id)
    except Exception:
        return None


async def get_current_user_scopes(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> set[APIScope]:
    """
    Extract and validate user scopes from access token.
    """
    token = credentials.credentials

    # Validate token and get user info
    token_data = await validate_access_token(token)
    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    # Get user from database
    user = await get_user_by_id(token_data["user_id"])
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    # Calculate user permissions
    token_scopes = [APIScope(s) for s in (token_data.get("scopes", []) or [])]  # Token-specific scopes

    # Get user's full permissions (including role-based and additional scopes, expanded)
    user_permissions = await get_user_permissions(user.role)

    # If token has 'api' scope, use user's full permissions
    if APIScope.API in token_scopes:
        return user_permissions

    # Otherwise, token scopes are limited to what's specified in the token itself
    # and must be a subset of the user's overall permissions.
    # We expand the token scopes to include any inherited scopes from the token itself.
    expanded_token_scopes = expand_scopes(set(token_scopes))

    # The final scopes are the intersection of the user's expanded permissions and the expanded token scopes.
    return user_permissions.intersection(expanded_token_scopes)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> User:
    """
    Get current authenticated user.
    """
    token = credentials.credentials

    # Validate token and get user info
    token_data = await validate_access_token(token)
    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    # Get user from database
    user = await get_user_by_id(token_data["user_id"])
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    return user


async def cleanup_expired_tokens() -> int:
    """
    Clean up expired tokens by marking them as inactive.
    Returns the number of tokens cleaned up.
    """
    try:
        current_time = datetime.now(TIMEZONE)
        expired_tokens = await Token.find(
            Token.expires_at < current_time,
            Token.is_active == True,  # noqa: E712
        ).to_list()

        count = 0
        for token in expired_tokens:
            await token.set({Token.is_active: False})
            count += 1
    except Exception:
        return 0
    return count


# Password utilities
def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt.

    Args:
        password: Plain text password to hash

    Returns:
        Hashed password string
    """
    salt = bcrypt.gensalt()
    password_bytes = password.encode("utf-8")
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """
    Verify a password against its hash.

    Args:
        password: Plain text password to verify
        hashed: Hashed password to verify against

    Returns:
        True if password matches, False otherwise
    """
    try:
        password_bytes = password.encode("utf-8")
        hashed_bytes = hashed.encode("utf-8")
        return bcrypt.checkpw(password_bytes, hashed_bytes)
    except Exception:
        return False


async def authenticate_user(email: str, password: str) -> User | None:
    """
    Authenticate a user with email and password.

    Args:
        email: User email address
        password: Plain text password

    Returns:
        User object if authentication successful, None otherwise
    """
    try:
        user = await User.find_one({"email": email, "is_active": True})
        if not user or not user.password_hash:
            return None

        if verify_password(password, user.password_hash):
            # Update last seen timestamp
            user.last_seen_at = datetime.now(TIMEZONE)
            await user.save()
            return user
    except Exception:
        return None
    return None
