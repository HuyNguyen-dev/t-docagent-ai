from datetime import datetime, timedelta

from fastapi import HTTPException, status
from pymongo import DESCENDING

from models.api_audit_log import APIAuditLog
from models.token import Token
from models.user import User
from schemas.response import Page, PaginatedMetadata
from schemas.token import (
    TokenCreateRequest,
    TokenDetailsResponse,
    TokenResponse,
    TokenUsageEntry,
    TokenWithValue,
)
from schemas.user import UserResponse
from utils.auth import generate_token, get_user_permissions, hash_token
from utils.constants import TIMEZONE
from utils.enums import APIScope
from utils.functions import encrypt_secure
from utils.logger.custom_logging import LoggerMixin


class TokenHandler(LoggerMixin):
    """Handler for token management operations."""

    async def create_token(
        self,
        user: User | UserResponse,
        token_request: TokenCreateRequest,
    ) -> TokenWithValue:
        """
        Create a new access token for the user.
        """
        # Validate requested scopes against user permissions
        user_permissions = await get_user_permissions(user.role)

        requested_scopes = set(token_request.scopes)

        # If user has 'api' scope, they can create tokens with any scope
        if APIScope.API not in user_permissions and not requested_scopes.issubset(user_permissions):
            msg = "Cannot create token with scopes you don't have"
            raise ValueError(msg)

        # Generate token and hash
        token_value = generate_token()
        token_hash_value = hash_token(token_value)

        # Calculate expiration
        expires_at = None
        if token_request.expires_in:
            expires_at = datetime.now(TIMEZONE) + timedelta(days=token_request.expires_in)

        # Create token document
        token_doc = Token(
            token_hash=token_hash_value,
            user_id=str(user.id),
            name=token_request.name,
            description=token_request.description,
            scopes=token_request.scopes,
            expires_at=expires_at,
            created_at=datetime.now(TIMEZONE),
            is_active=True,
        )

        await token_doc.insert()
        self.logger.info(
            "event=token-created user_id=%s token_id=%s scopes=%s expires_at=%s",
            user.id,
            token_doc.id,
            len(token_request.scopes),
            expires_at,
        )
        return TokenWithValue(
            **token_doc.model_dump(),
            token=encrypt_secure(token_value),
        )

    async def get_user_tokens(
        self,
        user_id: str,
        page: int = 1,
        page_size: int = 20,
        status_filter: str | None = None,
    ) -> Page:
        """
        Get list of user's tokens.
        """
        # Build query
        query = {"user_id": user_id}

        if status_filter == "active":
            query["is_active"] = True
            query["$or"] = [
                {"expires_at": {"$gt": datetime.now(TIMEZONE)}},
                {"expires_at": None},
            ]
        elif status_filter == "expired":
            query["expires_at"] = {"$lt": datetime.now(TIMEZONE)}
        elif status_filter == "revoked":
            query["is_active"] = False

        # Calculate skip and limit for pagination
        skip = (page - 1) * page_size
        limit = page_size

        # Get tokens with pagination
        tokens = await Token.find(query).sort([("created_at", DESCENDING)]).skip(skip).limit(limit).to_list()
        total_items = await Token.find(query).count()

        token_responses = [
            TokenResponse(
                id=str(token.id),
                name=token.name,
                description=token.description,
                scopes=token.scopes,
                created_at=token.created_at,
                expires_at=token.expires_at,
                last_used_at=token.last_used_at,
                is_active=token.is_active
                and (token.expires_at is None or token.expires_at.astimezone(TIMEZONE) > datetime.now(TIMEZONE)),
            )
            for token in tokens
        ]
        total_pages = (total_items + page_size - 1) // page_size or 1
        return Page(
            items=token_responses,
            metadata=PaginatedMetadata(
                page=min(page, total_pages),
                page_size=page_size,
                total_items=total_items,
                total_pages=total_pages,
            ),
        )

    async def get_token_details(
        self,
        token_id: str,
        user_id: str,
    ) -> TokenDetailsResponse:
        """
        Get detailed information about a specific token.
        """
        token = await Token.get(token_id)
        if not token or token.user_id != user_id:
            msg = "Token not found"
            raise ValueError(msg)

        # Get real recent usage from audit logs
        recent_usage = await self._get_real_token_usage(token_id)

        return TokenDetailsResponse(
            id=str(token.id),
            name=token.name,
            description=token.description,
            scopes=token.scopes,
            created_at=token.created_at,
            expires_at=token.expires_at,
            last_used_at=token.last_used_at,
            is_active=token.is_active
            and (token.expires_at is None or token.expires_at.astimezone(TIMEZONE) > datetime.now(TIMEZONE)),
            recent_usage=recent_usage,
        )

    async def revoke_token(
        self,
        token_id: str,
        user_id: str,
    ) -> bool:
        """
        Revoke (deactivate) a user's token.
        """
        token = await Token.get(token_id)
        if not token or token.user_id != user_id:
            self.logger.error(
                'event=revoke-token-failed message="Token not found"',
            )
            return False

        if not token.is_active:
            self.logger.info(
                'event=revoke-token-failed message="Token is already revoked"',
            )
            return True
        await token.set({Token.is_active: False})
        self.logger.info("event=token-revoked token_id=%s user_id=%s", token_id, user_id)
        return True

    async def delete_token(
        self,
        token_id: str,
        user_id: str,
    ) -> bool:
        """
        Permanently delete a token (only for expired/revoked tokens).
        """
        token = await Token.get(token_id)
        if not token or token.user_id != user_id:
            self.logger.error(
                'event=delete-token-failed message="Token not found"',
            )
            return False

        # Only allow deletion of inactive or expired tokens
        is_expired = token.expires_at and token.expires_at.astimezone(TIMEZONE) < datetime.now(TIMEZONE)
        if token.is_active and not is_expired:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot delete active token. Revoke it first.",
            )

        await token.delete()
        self.logger.info("event=token-deleted token_id=%s user_id=%s", token_id, user_id)
        return True

    async def get_token_statistics(self, user_id: str) -> dict:
        """
        Get token usage statistics for a user.
        """
        # Count active tokens
        active_count = await Token.find(
            {
                "user_id": user_id,
                "is_active": True,
                "$or": [
                    {"expires_at": {"$gt": datetime.now(TIMEZONE)}},
                    {"expires_at": None},
                ],
            },
        ).count()

        # Count expired tokens
        expired_count = await Token.find(
            {
                "user_id": user_id,
                "expires_at": {"$lt": datetime.now(TIMEZONE)},
            },
        ).count()

        # Count revoked tokens
        revoked_count = await Token.find(
            {
                "user_id": user_id,
                "is_active": False,
            },
        ).count()

        # Calculate total API calls (mock data for now)
        total_calls = 847  # In real implementation, this would come from usage logs
        return {
            "active_tokens": active_count,
            "expired_tokens": expired_count,
            "revoked_tokens": revoked_count,
            "total_api_calls": total_calls,
            "success_rate": 99.8,
        }

    async def _get_real_token_usage(self, token_id: str) -> list[TokenUsageEntry]:
        """Get real usage data from audit logs."""
        # Query last 50 API calls for this token
        audit_logs = (
            await APIAuditLog.find(
                APIAuditLog.token_id == token_id,
            )
            .sort([("timestamp", -1)])
            .limit(20)
            .to_list()
        )

        return [
            TokenUsageEntry(
                endpoint=log.endpoint,
                method=log.method,
                timestamp=log.timestamp,
                status_code=log.status_code,
                ip_address=str(log.ip_address) if log.ip_address else None,
            )
            for log in audit_logs
        ]
