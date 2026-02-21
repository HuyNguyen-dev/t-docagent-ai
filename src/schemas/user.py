from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, EmailStr, Field

from utils.constants import TIMEZONE
from utils.enums import UserStatus


class UserCreateRequest(BaseModel):
    """Request schema for creating/inviting a new user."""

    email: EmailStr = Field(..., description="User email address", max_length=100)
    name: str = Field(..., description="User full name", max_length=50)
    role: str = Field(..., description="User role")
    message: str | None = Field(None, description="Welcome message for invitation email", max_length=500)


class UserUpdateRequest(BaseModel):
    """Request schema for updating user information."""

    name: str | None = Field(None, description="User full name", max_length=50)
    role: str | None = Field(None, description="User role")
    status: UserStatus | None = Field(None, description="User status")


class UserPasswordUpdateRequest(BaseModel):
    old_password: str
    new_password: str


class UserResponse(BaseModel):
    """Response schema for user information."""

    id: str = Field(..., description="Unique user identifier")
    email: EmailStr = Field(..., description="User email address")
    name: str = Field(..., description="User full name")
    role: str = Field(..., description="User role")
    status: UserStatus = Field(..., description="User status")
    scopes: list[str] = Field(default=[], description="Additional scopes beyond role")
    created_at: datetime = Field(..., description="User creation timestamp")
    last_seen_at: datetime | None = Field(None, description="Last activity timestamp")
    is_active: bool = Field(..., description="Whether user account is active")

    class Config:
        from_attributes = True


class Role(BaseModel):
    """Schema for roles."""

    id: str = Field(..., description="Role identifier")
    name: str = Field(..., description="Display name")
    description: str = Field(..., description="Role description")
    icon: str = Field(default="🔧", description="Role icon")
    scopes: list[str] = Field(..., description="Scopes included in this role")
    created_at: datetime = Field(default_factory=lambda: datetime.now(TIMEZONE), description="Creation timestamp")
    is_system_role: bool = Field(default=False, description="Whether this is a system role")


class RoleCreateRequest(BaseModel):
    """Request schema for creating roles."""

    name: str = Field(..., description="Role name", max_length=20)
    description: str = Field(..., description="Role description")
    icon: str = Field(default="🔧", description="Role icon")
    scopes: list[str] = Field(..., description="Scopes to include")


class UserInDB(BaseModel):
    """Database schema for users."""

    id: str = Field(
        default_factory=lambda: f"usr-{uuid4()!s}",
        alias="_id",
        alias_priority=2,
    )
    email: EmailStr = Field(..., description="User email address", unique=True)
    name: str = Field(..., description="User full name")
    role: str = Field(..., description="User role")
    status: UserStatus = Field(default=UserStatus.PENDING, description="User status")
    password_hash: str | None = Field(None, description="Hashed password (if local auth)")
    created_at: datetime = Field(default_factory=lambda: datetime.now(TIMEZONE), description="Creation timestamp")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(TIMEZONE), description="Last update timestamp")
    last_seen_at: datetime | None = Field(None, description="Last activity timestamp")
    is_active: bool = Field(default=True, description="Whether user account is active")

    class Config:
        populate_by_name = True


class RoleInDB(BaseModel):
    """Database schema for roles."""

    id: str = Field(
        default_factory=lambda: f"rol-{uuid4()!s}",
        alias="_id",
        alias_priority=2,
    )
    name: str = Field(..., description="Role name")
    description: str = Field(..., description="Role description")
    icon: str = Field(default="🔧", description="Role icon")
    scopes: list[str] = Field(..., description="Scopes included in this role")
    created_at: datetime = Field(default_factory=lambda: datetime.now(TIMEZONE), description="Creation timestamp")
    created_by: str = Field(..., description="ID of user who created this role")
    is_system_role: bool = Field(default=False, description="Whether this is a system role")

    class Config:
        populate_by_name = True


# Onboarding and Authentication Schemas
class OwnerOnboardingRequest(BaseModel):
    """Schema for owner onboarding request."""

    email: EmailStr = Field(..., description="Owner email address")
    name: str = Field(..., description="Owner full name")
    password: str = Field(..., min_length=8, description="Owner password (minimum 8 characters)")


class OwnerOnboardingResponse(BaseModel):
    """Schema for owner onboarding response."""

    user: "UserResponse" = Field(..., description="Created owner user")
    message: str = Field(..., description="Success message")


class LoginRequest(BaseModel):
    """Schema for user login request."""

    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., description="User password")


class SystemStatusResponse(BaseModel):
    """Schema for system status response."""

    is_initialized: bool = Field(..., description="Whether system has been initialized")
    has_owner: bool = Field(..., description="Whether an owner account exists")
    requires_onboarding: bool = Field(..., description="Whether onboarding is required")
    version: str = Field(default="1.0.0", description="System version")
    status: str = Field(default="ready", description="System status")


class UserCreateResponse(BaseModel):
    """Schema for user creation response."""

    id: str = Field(..., description="Unique user identifier")
    email: EmailStr = Field(..., description="User email address")
    name: str = Field(..., description="User full name")
    role: str = Field(..., description="User role")
    status: UserStatus = Field(..., description="User status")
    created_at: datetime = Field(..., description="User creation timestamp")
    is_active: bool = Field(..., description="Whether user account is active")
    password: str = Field(..., description="Encrypted temporary password")

    class Config:
        from_attributes = True


class UserStatisticsResponse(BaseModel):
    """Schema for user statistics response."""

    total_users: int = Field(..., description="Total number of users")
    active_users: int = Field(..., description="Number of active users")
    pending_users: int = Field(..., description="Number of pending users")
    suspended_users: int = Field(..., description="Number of suspended users")

    class Config:
        from_attributes = True


class PasswordResetResponse(BaseModel):
    """Schema for password reset response."""

    success: bool = Field(..., description="Whether password reset was successful")

    class Config:
        from_attributes = True


class RoleCreateResponse(BaseModel):
    """Schema for role creation response."""

    id: str = Field(..., description="Role identifier")
    name: str = Field(..., description="Display name")
    description: str = Field(..., description="Role description")
    icon: str = Field(default="🔧", description="Role icon")
    scopes: list[str] = Field(..., description="Scopes included in this role")
    created_at: datetime = Field(..., description="Creation timestamp")
    is_system_role: bool = Field(default=False, description="Whether this is a system role")

    class Config:
        from_attributes = True


class RoleListResponse(BaseModel):
    """Schema for role list response."""

    roles: list[Role] = Field(..., description="List of roles")

    class Config:
        from_attributes = True
