"""
Authentication schemas and models.

This module contains Pydantic models for authentication-related data structures.
"""

from pydantic import BaseModel, Field

from .user import UserResponse


class LoginResponse(BaseModel):
    """Response schema for login operations."""

    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="JWT refresh token")
    token_type: str = Field(default="Bearer", description="Token type")
    user: UserResponse = Field(..., description="Authenticated user information")

    class Config:
        from_attributes = True


class TokenRefreshResponse(BaseModel):
    """Response schema for token refresh operations."""

    access_token: str = Field(..., description="New JWT access token")
    refresh_token: str = Field(..., description="New JWT refresh token")
    token_type: str = Field(default="Bearer", description="Token type")
    user: UserResponse = Field(..., description="User information")

    class Config:
        from_attributes = True


class LogoutResponse(BaseModel):
    """Response schema for logout operations."""

    success: bool = Field(..., description="Whether logout was successful")

    class Config:
        from_attributes = True
