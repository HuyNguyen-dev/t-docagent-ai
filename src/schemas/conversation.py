from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, Field

from utils.constants import TIMEZONE


class ConversationInput(BaseModel):
    agent_id: str
    dwi_ids: list[str] = Field(default_factory=list)


class ConversationUpdateName(BaseModel):
    name: str = Field(max_length=100)


class UserCollaboration(BaseModel):
    hitl: bool = False
    reason: str = ""


class ConversationFile(BaseModel):
    uri: str
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(TIMEZONE),
        description="Timestamp at the time of object creation",
    )


class ConversationFileResponse(BaseModel):
    name: str
    uri: str
    mime_type: str
    created_at: datetime


class ConversationInDB(BaseModel):
    id: str = Field(
        default_factory=lambda: f"conv-{uuid4()!s}",
        alias="_id",
        alias_priority=2,
    )
    name: str = Field(max_length=100)
    agent_id: str
    dwi_id: str = ""
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(TIMEZONE),
        description="Timestamp at the time of object creation",
    )
    last_updated: datetime = Field(
        default_factory=lambda: datetime.now(TIMEZONE),
        description="Timestamp at the time of object last updated",
    )
    user_collaboration: UserCollaboration = Field(default_factory=UserCollaboration)
    files: list[ConversationFile] = Field(default_factory=list)


class ConversationItemResponse(BaseModel):
    id: str
    name: str


class ConversationDownloadRequest(BaseModel):
    asset_uris: list[str]
