from datetime import datetime

from pydantic import BaseModel, Field

from utils.constants import TIMEZONE


class StreamingResponse(BaseModel):
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(TIMEZONE),
        description="Timestamp at the time of object creation",
    )
    data: str | None
    done: bool


class LLMInput(BaseModel):
    prompt: str


class LLMResponse(StreamingResponse):
    model: str
