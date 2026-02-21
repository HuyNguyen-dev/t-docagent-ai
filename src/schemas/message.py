from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from utils.constants import TIMEZONE
from utils.enums import MessageRole


class ActionPayload(BaseModel):
    name: str
    status: str
    metadata: dict = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class MessagePayload(BaseModel):
    text: str = ""
    thinking: str = ""
    action: ActionPayload | dict = Field(default_factory=dict)


class BaseAttachment(BaseModel):
    name: str
    uri: str
    mime_type: str

    model_config = ConfigDict(extra="allow")


class MessageMetadata(BaseModel):
    attachments: list[BaseAttachment] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


class BaseMessage(BaseModel):
    role: MessageRole = MessageRole.ASSISTANT
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(TIMEZONE),
        description="Timestamp at the time of object creation",
    )
    payload: MessagePayload = Field(default_factory=MessagePayload)
    metadata: MessageMetadata = Field(default_factory=MessageMetadata)


class MessageInDB(BaseMessage):
    id: str = Field(
        default_factory=lambda: f"msg-{uuid4()!s}",
        alias="_id",
        alias_priority=2,
    )
    conv_id: str
    user_id: str = ""


class HistoricalMessages(BaseModel):
    conv_id: str
    user_id: str = ""
    total: int = 0
    historical_messages: list[BaseMessage] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")
