"""
This module contains the event types for the Agent User Interaction Protocol Python SDK.
"""

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import Field

from .model_types import ConfiguredBaseModel, Message, State


class EventType(StrEnum):
    """
    The type of event.
    """

    USER_MESSAGE = "USER_MESSAGE"
    TEXT_MESSAGE_START = "TEXT_MESSAGE_START"
    TEXT_MESSAGE_CONTENT = "TEXT_MESSAGE_CONTENT"
    TEXT_MESSAGE_END = "TEXT_MESSAGE_END"
    THINKING_TEXT_MESSAGE_START = "THINKING_TEXT_MESSAGE_START"
    THINKING_TEXT_MESSAGE_CONTENT = "THINKING_TEXT_MESSAGE_CONTENT"
    THINKING_TEXT_MESSAGE_END = "THINKING_TEXT_MESSAGE_END"
    THINKING_START = "THINKING_START"
    THINKING_END = "THINKING_END"
    TOOL_CALL_START = "TOOL_CALL_START"
    TOOL_CALL_ARGS = "TOOL_CALL_ARGS"
    TOOL_CALL_END = "TOOL_CALL_END"
    STATE_SNAPSHOT = "STATE_SNAPSHOT"
    STATE_DELTA = "STATE_DELTA"
    MESSAGES_SNAPSHOT = "MESSAGES_SNAPSHOT"
    RAW = "RAW"
    CUSTOM = "CUSTOM"
    RUN_STARTED = "RUN_STARTED"
    RUN_FINISHED = "RUN_FINISHED"
    RUN_ERROR = "RUN_ERROR"
    STEP_STARTED = "STEP_STARTED"
    STEP_FINISHED = "STEP_FINISHED"


class BaseEvent(ConfiguredBaseModel):
    """
    Base event for all events in the Agent User Interaction Protocol.
    """

    type: EventType
    timestamp: int | None = None
    raw_event: Any | None = None


class TextMessageStartEvent(BaseEvent):
    """
    Event indicating the start of a text message.
    """

    type: Literal[EventType.TEXT_MESSAGE_START]
    message_id: str
    role: Literal["assistant"]


class TextMessageContentEvent(BaseEvent):
    """
    Event containing a piece of text message content.
    """

    type: Literal[EventType.TEXT_MESSAGE_CONTENT]
    message_id: str
    delta: str  # This should not be an empty string


class TextMessageEndEvent(BaseEvent):
    """
    Event indicating the end of a text message.
    """

    type: Literal[EventType.TEXT_MESSAGE_END]
    message_id: str
    text: str


class ToolCallStartEvent(BaseEvent):
    """
    Event indicating the start of a tool call.
    """

    type: Literal[EventType.TOOL_CALL_START]
    tool_call_id: str
    tool_call_name: str
    parent_message_id: str | None = None


class ToolCallArgsEvent(BaseEvent):
    """
    Event containing tool call arguments.
    """

    type: Literal[EventType.TOOL_CALL_ARGS]
    tool_call_id: str
    delta: str


class ToolCallEndEvent(BaseEvent):
    """
    Event indicating the end of a tool call.
    """

    type: Literal[EventType.TOOL_CALL_END]
    text: str = ""
    status: Literal["success", "error"] = "success"
    tool_call_id: str
    metadata: dict = None


class StateSnapshotEvent(BaseEvent):
    """
    Event containing a snapshot of the state.
    """

    type: Literal[EventType.STATE_SNAPSHOT]
    snapshot: State


class StateDeltaEvent(BaseEvent):
    """
    Event containing a delta of the state.
    """

    type: Literal[EventType.STATE_DELTA]
    delta: list[Any]  # JSON Patch (RFC 6902)


class MessagesSnapshotEvent(BaseEvent):
    """
    Event containing a snapshot of the messages.
    """

    type: Literal[EventType.MESSAGES_SNAPSHOT]
    messages: list[Message]


class RawEvent(BaseEvent):
    """
    Event containing a raw event.
    """

    type: Literal[EventType.RAW]
    event: Any
    source: str | None = None


class CustomEvent(BaseEvent):
    """
    Event containing a custom event.
    """

    type: Literal[EventType.CUSTOM]
    name: str
    value: Any


class RunStartedEvent(BaseEvent):
    """
    Event indicating that a run has started.
    """

    type: Literal[EventType.RUN_STARTED]
    thread_id: str
    run_id: str


class RunFinishedEvent(BaseEvent):
    """
    Event indicating that a run has finished.
    """

    type: Literal[EventType.RUN_FINISHED]
    thread_id: str
    run_id: str


class RunErrorEvent(BaseEvent):
    """
    Event indicating that a run has encountered an error.
    """

    type: Literal[EventType.RUN_ERROR]
    message: str
    code: str | None = None


class StepStartedEvent(BaseEvent):
    """
    Event indicating that a step has started.
    """

    type: Literal[EventType.STEP_STARTED]
    step_name: str


class StepFinishedEvent(BaseEvent):
    """
    Event indicating that a step has finished.
    """

    type: Literal[EventType.STEP_FINISHED]
    step_name: str


class UserMessageEvent(BaseEvent):
    """
    Event containing the user's message.
    """

    type: Literal[EventType.USER_MESSAGE]
    message_id: str
    text: str
    metadata: dict = None


class ThinkingTextMessageStartEvent(BaseEvent):
    """
    Event indicating the start of a thinking text message.
    """

    message_id: str
    type: Literal[EventType.THINKING_TEXT_MESSAGE_START] = EventType.THINKING_TEXT_MESSAGE_START  # pyright: ignore[reportIncompatibleVariableOverride]


class ThinkingTextMessageContentEvent(BaseEvent):
    """
    Event indicating a piece of a thinking text message.
    """

    message_id: str
    type: Literal[EventType.THINKING_TEXT_MESSAGE_CONTENT] = EventType.THINKING_TEXT_MESSAGE_CONTENT  # pyright: ignore[reportIncompatibleVariableOverride]
    delta: str = Field(min_length=1)


class ThinkingTextMessageEndEvent(BaseEvent):
    """
    Event indicating the end of a thinking text message.
    """

    message_id: str
    type: Literal[EventType.THINKING_TEXT_MESSAGE_END] = EventType.THINKING_TEXT_MESSAGE_END  # pyright: ignore[reportIncompatibleVariableOverride]


class ThinkingStartEvent(BaseEvent):
    """
    Event indicating the start of a thinking step event.
    """

    type: Literal[EventType.THINKING_START] = EventType.THINKING_START  # pyright: ignore[reportIncompatibleVariableOverride]
    title: str | None = None


class ThinkingEndEvent(BaseEvent):
    """
    Event indicating the end of a thinking step event.
    """

    type: Literal[EventType.THINKING_END] = EventType.THINKING_END  # pyright: ignore[reportIncompatibleVariableOverride]


Event = Annotated[
    UserMessageEvent
    | TextMessageStartEvent
    | TextMessageContentEvent
    | TextMessageEndEvent
    | ThinkingTextMessageStartEvent
    | ThinkingTextMessageContentEvent
    | ThinkingTextMessageEndEvent
    | ThinkingStartEvent
    | ThinkingEndEvent
    | ToolCallStartEvent
    | ToolCallArgsEvent
    | ToolCallEndEvent
    | StateSnapshotEvent
    | StateDeltaEvent
    | MessagesSnapshotEvent
    | RawEvent
    | CustomEvent
    | RunStartedEvent
    | RunFinishedEvent
    | RunErrorEvent
    | StepStartedEvent
    | StepFinishedEvent,
    Field(discriminator="type"),
]
