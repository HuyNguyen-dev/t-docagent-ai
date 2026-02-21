from datetime import datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, IPvAnyAddress, field_validator, model_validator

from utils.constants import TIMEZONE


class APIAuditLogBase(BaseModel):
    """Base schema for API audit log with Pydantic v2 features."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        use_enum_values=True,
        populate_by_name=True,
    )


class APIAuditLogCreate(APIAuditLogBase):
    """Schema for creating new audit log entries."""

    # Core identification
    request_id: str = Field(..., min_length=1, description="Unique request identifier")

    # Authentication context
    user_id: str = Field(..., description="User ID for session/token auth")
    token_id: str | None = Field(None, description="Token ID for token auth")
    auth_type: Literal["SESSION", "TOKEN", "NONE", "INVALID", "ERROR"] = Field(
        ...,
        description="Type of authentication used",
    )

    # Request details
    endpoint: str = Field(..., min_length=1, description="API endpoint accessed")
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"] = Field(
        ...,
        description="HTTP method used",
    )
    path_params: dict[str, str] | None = Field(None, description="URL path parameters")
    query_params: dict[str, str] | None = Field(None, description="Query string parameters")

    # Response details
    status_code: int = Field(..., ge=100, le=599, description="HTTP response status")
    response_size: int | None = Field(None, ge=0, description="Response size in bytes")
    processing_time_ms: int | None = Field(None, ge=0, description="Processing time in ms")

    # Client context - Using Pydantic v2 IPvAnyAddress
    ip_address: str | None = Field(None, description="Client IP address (IPv4/IPv6)")
    user_agent: str | None = Field(None, max_length=2048, description="Client user agent")
    referer: str | None = Field(None, max_length=2048, description="HTTP referer header")

    # Security context
    scopes_used: list[str] = Field(default=[], description="API scopes accessed")
    risk_level: Literal["low", "medium", "high", "critical"] = Field(
        default="low",
        description="Assessed risk level",
    )
    is_suspicious: bool = Field(default=False, description="Flagged as suspicious")

    # Error details
    error_code: str | None = Field(None, max_length=100, description="Error code if failed")
    error_message: str | None = Field(None, max_length=1000, description="Error message if failed")

    @field_validator("scopes_used")
    @classmethod
    def validate_scopes_unique(cls, v: list[str]) -> list[str]:
        """Ensure scopes are unique and non-empty."""
        if not isinstance(v, list):
            error_msg = "scopes_used must be a list"
            raise TypeError(error_msg)
        # Remove duplicates while preserving order
        unique_scopes = list(dict.fromkeys(v))
        # Filter out empty strings
        return [scope for scope in unique_scopes if scope.strip()]

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint_format(cls, v: str) -> str:
        """Validate endpoint format."""
        if not v.startswith("/"):
            error_msg = "Endpoint must start with '/'"
            raise ValueError(error_msg)
        if len(v) > 500:
            error_msg = "Endpoint path too long"
            raise ValueError(error_msg)
        return v

    @field_validator("request_id")
    @classmethod
    def validate_request_id_format(cls, v: str) -> str:
        """Validate request ID format."""
        import re

        # Should be UUID-like or alphanumeric
        if not re.match(r"^[a-fA-F0-9\-]{8,}$", v):
            error_msg = "Invalid request_id format"
            raise ValueError(error_msg)
        return v

    @model_validator(mode="after")
    def validate_auth_context(self):  # noqa: ANN201
        """Validate authentication context consistency."""
        if self.auth_type == "SESSION" and not self.user_id:
            error_msg = "SESSION auth requires user_id"
            raise ValueError(error_msg)
        if self.auth_type == "TOKEN" and not self.token_id:
            error_msg = "TOKEN auth requires token_id"
            raise ValueError(error_msg)
        if self.auth_type == "TOKEN" and not self.user_id:
            error_msg = "TOKEN auth requires user_id (token owner)"
            raise ValueError(error_msg)
        return self

    @model_validator(mode="after")
    def validate_error_context(self):  # noqa: ANN201
        """Validate error fields consistency."""
        if self.status_code >= 400:
            # For error responses, we might want error details
            pass
        else:
            # For successful responses, clear any error fields
            if self.error_code or self.error_message:
                error_msg = "Success responses should not have error details"
                raise ValueError(error_msg)
        return self


class APIAuditLogInDB(APIAuditLogCreate):
    """Database schema for API audit log."""

    # Auto-generated fields
    id: str = Field(
        default_factory=lambda: str(uuid4()),
        alias="_id",
        description="Unique audit log identifier",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(TIMEZONE),
        description="When the API call was made",
    )


class APIAuditLogResponse(APIAuditLogBase):
    """Response schema for API audit log queries."""

    id: str = Field(..., description="Unique audit log identifier")
    timestamp: datetime = Field(..., description="When the API call was made")
    request_id: str = Field(..., description="Unique request identifier")

    # Authentication context
    user_id: str | None = Field(None, description="User ID for session auth")
    token_id: str | None = Field(None, description="Token ID for token auth")
    auth_type: str = Field(..., description="Type of authentication used")

    # Request details
    endpoint: str = Field(..., description="API endpoint accessed")
    method: str = Field(..., description="HTTP method used")

    # Response details
    status_code: int = Field(..., description="HTTP response status")
    processing_time_ms: int | None = Field(None, description="Processing time in ms")

    # Client context (IP as string in response)
    ip_address: str | None = Field(None, description="Client IP address")

    # Security context
    risk_level: str = Field(..., description="Assessed risk level")
    is_suspicious: bool = Field(..., description="Flagged as suspicious")


class AuditStatistics(APIAuditLogBase):
    """Schema for audit statistics and dashboard data."""

    total_requests: int = Field(..., ge=0, description="Total API requests")
    unique_users: int = Field(..., ge=0, description="Number of unique users")
    unique_tokens: int = Field(..., ge=0, description="Number of unique tokens used")
    error_rate: float = Field(..., ge=0, le=1, description="Error rate (0-1)")
    avg_response_time: float | None = Field(None, ge=0, description="Average response time in ms")
    suspicious_count: int = Field(..., ge=0, description="Number of suspicious requests")

    # Top endpoints
    top_endpoints: list[dict[str, int | str]] = Field(
        default=[],
        description="Most frequently accessed endpoints",
    )

    # Status code distribution
    status_distribution: dict[str, int] = Field(
        default={},
        description="Distribution of HTTP status codes",
    )

    # Time-based metrics
    requests_by_hour: dict[str, int] = Field(
        default={},
        description="Request count by hour",
    )


# Type aliases for convenience
AuditLogDict = dict[str, any]
IPAddress = IPvAnyAddress
