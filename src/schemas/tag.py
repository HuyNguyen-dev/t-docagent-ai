from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, Field

from utils.constants import TIMEZONE


class TagInDB(BaseModel):
    """Tag model for database operations."""

    id: str = Field(
        default_factory=lambda: f"tag-{uuid4()!s}",
        alias="_id",
        alias_priority=2,
        description="Unique identifier for the tag",
    )
    name: str = Field(..., max_length=50, description="Tag name (unique)")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(TIMEZONE),
        description="Timestamp when the tag was created",
    )
    created_by: str = Field(default="Admin", description="User who created the tag")
    is_active: bool = Field(default=True, description="Whether the tag is active")
    usage_count: int = Field(default=0, description="Number of knowledge bases using this tag")


class TagCreateRequest(BaseModel):
    """Request model for creating a new tag."""

    name: str = Field(..., max_length=50, description="Tag name")


class TagUpdate(BaseModel):
    """Model for updating an existing tag."""

    name: str | None = Field(None, max_length=50, description="Tag name")
    is_active: bool | None = Field(None, description="Whether the tag is active")


class TagResponse(BaseModel):
    """Response model for tag information."""

    id: str = Field(..., description="Unique identifier for the tag")
    name: str = Field(..., description="Tag name")
    created_at: datetime = Field(..., description="Creation timestamp")
    created_by: str = Field(..., description="User who created the tag")
    is_active: bool = Field(..., description="Whether the tag is active")
    usage_count: int = Field(..., description="Number of knowledge bases using this tag")


class TagListResponse(BaseModel):
    """Response model for tag list with pagination."""

    tags: list[TagResponse] = Field(..., description="List of tags")
    total_items: int = Field(..., description="Total number of tags")
    total_pages: int = Field(..., description="Total number of pages")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Number of items per page")
    has_next: bool = Field(..., description="Whether there is a next page")
    has_prev: bool = Field(..., description="Whether there is a previous page")
