from datetime import datetime

from ag_ui.core.events import (
    CustomEvent,
    EventType,
    RunErrorEvent,
    RunFinishedEvent,
    RunStartedEvent,
    StepFinishedEvent,
    StepStartedEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
    ThinkingEndEvent,
    ThinkingStartEvent,
    ThinkingTextMessageContentEvent,
    ThinkingTextMessageEndEvent,
    ThinkingTextMessageStartEvent,
    ToolCallEndEvent,
    ToolCallStartEvent,
    UserMessageEvent,
)
from ag_ui.encoder import EventEncoder
from initializer import redis_pubsub_manager
from utils.constants import TIMEZONE


class AGUI:
    def __init__(self, chanel: str) -> None:
        """Initialize the mixin with conversation and run IDs."""
        self.chanel = chanel
        self.event_encoder = EventEncoder()

    async def publish(
        self,
        event_cls: any,
        event_type: EventType,
        title: str | None = None,
        step_name: str | None = None,
        message_id: str | None = None,
        message: str | None = None,
        role: str | None = None,
        run_id: str | None = None,
        thread_id: str | None = None,
        tool_call_name: str | None = None,
        text: str | None = None,
        tool_call_id: str | None = None,
        status: str | None = None,
        name: str | None = None,
        value: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        """Helper method to create, encode, and publish step events."""
        event_kwargs = {
            "type": event_type,
            "timestamp": int(datetime.now(TIMEZONE).timestamp()),
        }

        run_params = {"thread_id": thread_id, "run_id": run_id}
        step_params = {"step_name": step_name}

        event_param_map = {
            RunStartedEvent: run_params,
            RunFinishedEvent: run_params,
            StepStartedEvent: step_params,
            StepFinishedEvent: step_params,
            RunErrorEvent: {"message": message},
            ToolCallStartEvent: {
                "tool_call_id": tool_call_id,
                "tool_call_name": tool_call_name,
            },
            ToolCallEndEvent: {
                "text": text,
                "status": status,
                "tool_call_id": tool_call_id,
                "metadata": metadata,
            },
            TextMessageContentEvent: {
                "message_id": message_id,
                "delta": message or "",
            },
            TextMessageStartEvent: {
                "message_id": message_id,
                "role": role or "assistant",
            },
            TextMessageEndEvent: {
                "message_id": message_id,
                "text": text or "",
            },
            UserMessageEvent: {"message_id": message_id, "text": text, "metadata": metadata},
            CustomEvent: {"name": name, "value": value},
            ThinkingStartEvent: {"title": title},
            ThinkingEndEvent: {},
            ThinkingTextMessageStartEvent: {"message_id": message_id},
            ThinkingTextMessageContentEvent: {"message_id": message_id, "delta": message or ""},
            ThinkingTextMessageEndEvent: {"message_id": message_id},
        }

        if event_specific_params := event_param_map.get(event_cls):
            event_kwargs.update(event_specific_params)

        event = event_cls(**event_kwargs)
        event_data = self.event_encoder.encode(event)
        await self._publish_event(event_data)

    async def _publish_event(self, event: dict) -> None:
        """Publish event to Redis channel."""
        await redis_pubsub_manager.publish(
            self.chanel,
            event,
        )
