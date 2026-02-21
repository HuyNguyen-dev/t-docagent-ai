from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class BasicResponse(BaseModel):
    status: Literal["success", "failed"] = "failed"
    message: str
    data: Any | None = None


class PaginatedMetadata(BaseModel):
    page: int = 1
    page_size: int = 10
    total_items: int = 0
    total_pages: int = 1


class Page(BaseModel):
    items: list = Field(default_factory=list)
    metadata: PaginatedMetadata = Field(default_factory=PaginatedMetadata)

    model_config = ConfigDict(extra="allow")
