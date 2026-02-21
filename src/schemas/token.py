from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, Field

from utils.constants import TIMEZONE


class TokenCreateRequest(BaseModel):
    """Request schema for creating a new access token."""

    name: str = Field(..., description="Descriptive name for the token", max_length=50)
    description: str | None = Field(None, description="Optional description of the token's purpose", max_length=200)
    scopes: list[str] = Field(..., description="List of scopes to grant to this token")
    expires_in: int | None = Field(None, description="Token expiration in days (null for never expires)")


class TokenResponse(BaseModel):
    """Response schema for token operations."""

    id: str = Field(..., description="Unique token identifier")
    name: str = Field(..., description="Token name")
    description: str | None = Field(None, description="Token description")
    scopes: list[str] = Field(..., description="Granted scopes")
    created_at: datetime = Field(..., description="Token creation timestamp")
    expires_at: datetime | None = Field(None, description="Token expiration timestamp")
    last_used_at: datetime | None = Field(None, description="Last usage timestamp")
    is_active: bool = Field(..., description="Whether token is active")

    class Config:
        from_attributes = True


class TokenWithValue(TokenResponse):
    """Token response including the actual token value (only returned on creation)."""

    token: str = Field(..., description="The actual access token value")


class TokenUsageEntry(BaseModel):
    """Schema for token usage log entry."""

    endpoint: str = Field(..., description="API endpoint accessed")
    method: str = Field(..., description="HTTP method used")
    timestamp: datetime = Field(..., description="Access timestamp")
    status_code: int = Field(..., description="HTTP response status")
    ip_address: str | None = Field(None, description="Client IP address")


class TokenDetailsResponse(TokenResponse):
    """Detailed token response including usage history."""

    recent_usage: list[TokenUsageEntry] = Field(default=[], description="Recent usage history")


class TokenListResponse(BaseModel):
    """Response schema for listing tokens."""

    tokens: list[TokenResponse] = Field(..., description="List of user tokens")
    total: int = Field(..., description="Total number of tokens")


class TokenInDB(BaseModel):
    """Database schema for access tokens."""

    id: str = Field(
        default_factory=lambda: f"token-{uuid4()!s}",
        alias="_id",
        alias_priority=2,
    )
    token_hash: str = Field(..., description="SHA256 hash of the token")
    user_id: str = Field(..., description="ID of the token owner")
    name: str = Field(..., description="Token name")
    description: str | None = Field(None, description="Token description")
    scopes: list[str] = Field(..., description="Granted scopes")
    created_at: datetime = Field(default_factory=lambda: datetime.now(TIMEZONE), description="Creation timestamp")
    expires_at: datetime | None = Field(None, description="Expiration timestamp")
    last_used_at: datetime | None = Field(None, description="Last usage timestamp")
    is_active: bool = Field(default=True, description="Whether token is active")

    class Config:
        populate_by_name = True
