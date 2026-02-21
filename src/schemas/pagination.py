from typing import TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Page[T](BaseModel):
    total: int = Field(..., description="Total number of records")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Number of records per page")
    items: list[T] = Field(..., description="List of records")
