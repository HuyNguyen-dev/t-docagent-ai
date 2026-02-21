from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, Field

from utils.constants import TIMEZONE
from utils.enums import RunBookType


class RunbookBase(BaseModel):
    name: str = Field(description="Name of the runbook")
    version: str = Field(default="1", description="Version of the runbook")
    prompt: str = Field(description="Content of the runbook")
    type: RunBookType = Field(default=RunBookType.TEXT.value, description="Type of the runbook")
    labels: list[str] = Field(default_factory=list, description="Labels associated with the runbook")
    tags: list[str] = Field(default_factory=list, description="Tags associated with the runbook")


class RunbookInDB(RunbookBase):
    id: str = Field(
        default_factory=lambda: f"rb-{uuid4()!s}",
        alias="_id",
        alias_priority=2,
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(TIMEZONE),
        description="Creation timestamp",
    )
    last_updated: datetime = Field(
        default_factory=lambda: datetime.now(TIMEZONE),
        description="Last update timestamp",
    )


class RunbookInput(BaseModel):
    name: str = Field(description="Name of the runbook")
    prompt: str = Field(description="Content of the runbook")
    created_at: datetime = Field(description="Creation timestamp")
    labels: list[str] = Field(default_factory=list, description="Labels associated with the runbook")
    tags: list[str] = Field(default_factory=list, description="Tags associated with the runbook")


class RunbookUpdate(BaseModel):
    version: str = Field(description="Version of the runbook")
    content: str = Field(description="Content of the runbook")
    labels: list[str] = Field(default_factory=list, description="Labels associated with the runbook")
    tags: list[str] = Field(default_factory=list, description="Tags associated with the runbook")


class RunbookResponse(RunbookBase):
    id: str = Field(description="Unique identifier for the runbook")
    created_at: datetime = Field(description="Creation timestamp")
    last_updated: datetime = Field(description="Last update timestamp")
