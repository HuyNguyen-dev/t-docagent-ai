import asyncio
import mimetypes
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import orjson
from fastapi import Request
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command, StateSnapshot

from ag_ui.core.events import (
    CustomEvent,
    EventType,
    RunErrorEvent,
    RunFinishedEvent,
    RunStartedEvent,
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
from agents.react.base import BaseChatAgent
from handlers.document import DocumentHandler
from handlers.user import UserHandler
from initializer import redis_pubsub_manager
from models.agent import Agent
from models.conversation import Conversation
from models.message import Message
from schemas.conversation import ConversationFile
from schemas.message import (
    ActionPayload,
    BaseAttachment,
    MessageMetadata,
    MessagePayload,
)
from schemas.user import UserResponse
from settings.prompts.conversational_agent import FRIENDLY_CONVERSATIONAL_AGENT_MESSAGE_SYSTEM
from utils.checkpointer import get_mongodb_checkpointer
from utils.constants import (
    DATA_CHART_DIR,
    DEFAULT_CONVERSATION_FILE_FOLDER,
    DEFAULT_FUNCTION_CHART_GENERATION,
    DEFAULT_FUNCTION_INTERRUPT,
)
from utils.enums import AgentType, LLMEventType, MessageRole
from utils.functions import list_files_pathlib
from utils.logger.custom_logging import LoggerMixin


class BaseAgentHandler(LoggerMixin, ABC):
    def __init__(self) -> None:
        self.document_handler = DocumentHandler()
        self.user_hanlder = UserHandler()
        super().__init__()

    async def _load_history_and_update_state_snapshot(self) -> list[Any]:
        """Load messages history and reformat into object Message."""

    def _get_agent(self, conv_id: str) -> dict[str, Any] | None:
        return redis_pubsub_manager.conv_session_manager.get(conv_id, [None])[0]

    @abstractmethod
    async def _create_agent_instance(self, conv_id: str, agent_config: Agent) -> any:
        """Create and return an agent instance for the given conversation ID and config."""

    async def _check_conv_and_load_agent_config(
        self,
        conv_id: str,
    ) -> tuple[Conversation | None, Agent | None]:
        """
        Load Conversation by ID and then load Agent by agent_id from Conversation.
        Returns a tuple (conversation, agent) or (None, None) if not found.
        """
        conv = await Conversation.get(conv_id)
        if conv is None:
            self.logger.error(
                'event=load-conversation-failed message="Conversation with id %s not found."',
                conv_id,
            )
            return None, None
        agent_id = getattr(conv, "agent_id", None)
        if agent_id is None:
            self.logger.error(
                'event=load-agent-failed message="agent_id missing in conversation %s".',
                conv_id,
            )
            return conv, None
        agent_db = await Agent.get(agent_id)
        if agent_db is None:
            self.logger.error(
                'event=load-agent-failed message="Agent with id %s not found."',
                agent_id,
            )
        return conv, agent_db

    async def _render_assets_part(self, question: str, assets: list[str]) -> list[dict]:
        """Render a list of asset URIs into LLM-compatible content parts with base64 data.

        Each part uses type "image" for image/* mime types, otherwise "file".
        """
        content_parts: list[dict] = []
        if not assets:
            return [{"type": "text", "text": question}]

        results: list[tuple[str, str | None]] = [(uri, None) for uri in assets]
        async with asyncio.TaskGroup() as tg:
            for idx, uri in enumerate(assets):

                async def fetch(i: int, u: str) -> None:
                    try:
                        data_b64 = await self.document_handler.get_data_document(object_path=u)
                    except Exception:
                        self.logger.exception(
                            "event=render-asset-exception uri=%s",
                            u,
                        )
                        data_b64 = None
                    results[i] = (u, data_b64)

                tg.create_task(fetch(idx, uri))
        for uri, data_b64 in results:
            if not data_b64:
                continue
            mime_type = mimetypes.guess_type(uri)[0] or "application/octet-stream"
            part_type = "image" if mime_type.startswith("image/") else "file"
            content_parts.append(
                {
                    "type": part_type,
                    "source_type": "base64",
                    "data": data_b64,
                    "mime_type": mime_type,
                },
            )
        content_parts.append({"type": "text", "text": question})

        return content_parts

    async def _push_and_public_chart(
        self,
        conv_id: str,
        state: StateSnapshot,
        message: Message,
    ) -> dict[str, Any]:
        chart_files = list_files_pathlib(DATA_CHART_DIR)
        chart_attachments = []
        object_return = {
            "message": message,
            "state": state,
            "chart_attachments": chart_attachments,
        }
        if chart_files:
            chart_path = DATA_CHART_DIR.joinpath(chart_files[0])
            object_path = await self.document_handler.upload_document(
                file_path=chart_path,
                document_type_name=DEFAULT_CONVERSATION_FILE_FOLDER,
                document_format_name=conv_id,
            )
            if object_path is not None:
                chart_path.unlink()
                mime_type = mimetypes.guess_type(chart_path)[0] or "application/octet-stream"
                message.metadata = MessageMetadata(
                    attachments=[
                        BaseAttachment(
                            name=chart_path.name,
                            uri=object_path,
                            mime_type=mime_type,
                        ),
                    ],
                )
                presigned_map = await self.document_handler.create_presigned_urls(
                    object_names=[object_path],
                    inline=True,
                )
                object_return["chart_attachments"] = [
                    BaseAttachment(
                        name=chart_path.name,
                        uri=presigned_map[object_path],
                        mime_type=mime_type,
                    ),
                ]
                conv_db = await Conversation.get(conv_id)
                conv_db.files.append(ConversationFile(uri=object_path))
                await conv_db.save()
                last_message = state.values["messages"][-1]
                if isinstance(last_message, ToolMessage):
                    data_b64 = await self.document_handler.get_data_document(object_path=object_path)
                    msg_txt = last_message.content
                    last_message.content = [
                        {
                            "type": "text",
                            "text": msg_txt,
                        },
                        {
                            "type": "image",
                            "source_type": "base64",
                            "data": data_b64,
                            "mime_type": mime_type,
                        },
                    ]
                    state.values["messages"][-1] = last_message

        return object_return

    async def refresh_agent_by_conv_id(self, conv_id: str, agent_config: Agent) -> bool:
        """Refresh the agent in the session manager."""
        # only refresh agent when conversation exists
        if conv_id in redis_pubsub_manager.conv_session_manager:
            async with get_mongodb_checkpointer() as checkpointer:
                obj_agent: BaseChatAgent = await self._create_agent_instance(conv_id, agent_config)
                is_init = await obj_agent.initialize_properties()
                if not is_init:
                    return False
                agent_graph = obj_agent.build_workflow().compile(checkpointer=checkpointer)
                agent_dict = {"obj_agent": obj_agent, "agent_graph": agent_graph}
                # Update the agent in the session manager
                redis_pubsub_manager.conv_session_manager[conv_id][0] = agent_dict
                return True
        return False

    async def initialize_agent(self, conv_id: str, request: Request, agent_config: Agent) -> dict[str, Any]:
        """Initialize the agent and add it to the session manager."""
        if conv_id in redis_pubsub_manager.conv_session_manager:
            if request not in redis_pubsub_manager.conv_session_manager[conv_id][1]:
                redis_pubsub_manager.conv_session_manager[conv_id][1].append(request)
            self.logger.info(
                'event=agent-reinitialized message="Agent for conversation %s reinitialized with new request."',
                conv_id,
            )
            return self._get_agent(conv_id)
        async with get_mongodb_checkpointer() as checkpointer:
            obj_agent: BaseChatAgent = await self._create_agent_instance(conv_id, agent_config)
            is_init = await obj_agent.initialize_properties()
            if not is_init:
                return {"obj_agent": None, "agent_graph": None}
            agent_graph = obj_agent.build_workflow().compile(checkpointer=checkpointer)
            agent_dict = {"obj_agent": obj_agent, "agent_graph": agent_graph}
            redis_pubsub_manager.conv_session_manager[conv_id] = [agent_dict, [request]]
            return agent_dict

    async def initialize(self, conv_id: str, request: Request) -> dict[str, Any] | None:
        conv_db, agent_db = await self._check_conv_and_load_agent_config(conv_id=conv_id)
        if conv_db is None or agent_db is None:
            self.logger.error(
                "event=check-conversation-and-initialize-agent-failed "
                'message="Not found Conversation or Agent Config. Please check conv_id: %s"',
                conv_id,
            )
            return None
        return await self.initialize_agent(
            conv_id=conv_id,
            request=request,
            agent_config=agent_db,
        )

    async def achat(
        self,
        conv_id: str,
        question: str,
        assets: list[str],
        current_user: UserResponse,
    ) -> None:
        agent = self._get_agent(conv_id)
        obj_agent: BaseChatAgent = agent["obj_agent"]
        agent_graph: CompiledStateGraph = agent["agent_graph"]

        conv_db = await Conversation.get(conv_id)
        # The following logic may need to be customized in subclasses
        if conv_db.user_collaboration.hitl:
            state = Command(resume={"data": question})
        else:
            # Classify the message to determine if we should use the runbook
            system_message = obj_agent.system_message  # Default system message
            content_parts = await self._render_assets_part(question, assets)
            conv_db.files.extend([ConversationFile(uri=asset) for asset in assets])
            if obj_agent.agent_db.type == AgentType.CONVERSATION:
                is_friendly_question = await obj_agent.classify_message(question)
                if is_friendly_question:
                    system_message = FRIENDLY_CONVERSATIONAL_AGENT_MESSAGE_SYSTEM.format_messages()[0]

            is_first_message = await Message.find_one(Message.conv_id == conv_id)
            if is_first_message is None:
                state = obj_agent.agent_state(
                    messages=[
                        system_message,
                        HumanMessage(content=content_parts),
                    ],
                )
            else:
                state = obj_agent.agent_state(
                    messages=[HumanMessage(content=content_parts)],
                )
            await conv_db.save()

        presigned_map = {}
        attachments = []
        if assets:
            presigned_map = await self.document_handler.create_presigned_urls(
                object_names=assets,
                inline=True,
            )
            attachments = [
                BaseAttachment(
                    name=Path(asset).name,
                    uri=presigned_map[asset],
                    mime_type=mimetypes.guess_type(Path(asset).name)[0] or "application/octet-stream",
                    download_uri=asset,
                ).model_dump()
                for asset in assets
            ]

        run_id = str(uuid.uuid4())
        # Push User Message
        user_msg = Message(
            conv_id=conv_id,
            role=MessageRole.USER,
            payload=MessagePayload(text=question),
            metadata=MessageMetadata(
                attachments=[
                    BaseAttachment(
                        name=Path(asset).name,
                        uri=asset,
                        mime_type=mimetypes.guess_type(Path(asset).name)[0] or "application/octet-stream",
                    )
                    for asset in assets
                ],
            ),
        )
        await obj_agent.sse_event.publish(
            event_cls=UserMessageEvent,
            event_type=EventType.USER_MESSAGE,
            message_id=user_msg.id,
            text=question,
            metadata={"attachments": attachments},
        )
        await user_msg.insert()
        try:
            await obj_agent.sse_event.publish(
                event_cls=RunStartedEvent,
                event_type=EventType.RUN_STARTED,
                run_id=run_id,
                thread_id=conv_id,
            )
            config = RunnableConfig(run_id=run_id, configurable={"thread_id": conv_id})
            before_event = LLMEventType.ON_CHAIN_END
            is_message_start = False
            message: Message | None = None
            text = ""
            is_thinking_active = False
            is_hitl = False
            async with get_mongodb_checkpointer() as checkpointer:
                agent_graph.checkpointer = checkpointer
                async for event in agent_graph.astream_events(
                    state,
                    config=config,
                    stream_mode="messages",
                ):
                    try:
                        event_type = event["event"]
                        if event_type == LLMEventType.ON_TOOL_START:
                            # In case no thinking mode, so need to create a new Message object
                            if not is_message_start:
                                message = Message(
                                    conv_id=conv_id,
                                    role=MessageRole.TOOL,
                                    payload=MessagePayload(
                                        action=ActionPayload(
                                            name=event["name"],
                                            status="success",
                                        ),
                                    ),
                                )
                                await obj_agent.sse_event.publish(
                                    event_cls=TextMessageStartEvent,
                                    event_type=EventType.TEXT_MESSAGE_START,
                                    message_id=message.id,
                                )
                                is_message_start = True
                            # Ensure the message is a tool message
                            message.payload.action = ActionPayload(
                                name=event["name"],
                                status="success",
                            )
                            message.role = MessageRole.TOOL
                            if is_thinking_active:
                                await obj_agent.sse_event.publish(
                                    event_cls=ThinkingTextMessageEndEvent,
                                    event_type=EventType.THINKING_TEXT_MESSAGE_END,
                                    message_id=message.id,
                                )
                                await obj_agent.sse_event.publish(
                                    event_cls=ThinkingEndEvent,
                                    event_type=EventType.THINKING_END,
                                )
                                is_thinking_active = False
                            await obj_agent.sse_event.publish(
                                event_cls=ToolCallStartEvent,
                                event_type=EventType.TOOL_CALL_START,
                                tool_call_name=event["name"],
                                tool_call_id=message.id,
                            )
                        elif event_type == LLMEventType.ON_TOOL_END and type(event["data"]["output"]) in [dict, str]:
                            observation: dict = event["data"]["output"]
                            try:
                                if isinstance(observation, str):
                                    observation = orjson.loads(observation)
                                content = observation.get("success", "") if "error" not in observation else observation["error"]
                            except (KeyError, TypeError, orjson.JSONDecodeError):
                                content = observation
                            text = f"Inputs: {event['data']['input']} \n Output: {content!s}"
                            chart_attachments = []
                            message.payload.action = message.payload.action.model_dump()
                            if message.payload.action["name"] == DEFAULT_FUNCTION_CHART_GENERATION:
                                current_state: StateSnapshot = await agent_graph.aget_state(config)
                                resp = await self._push_and_public_chart(conv_id, current_state, message)
                                message = resp["message"]
                                chart_attachments = resp["chart_attachments"]
                                current_state = resp["state"]
                                await agent_graph.aupdate_state(
                                    config=current_state.config,
                                    values={"messages": current_state.values["messages"]},
                                    as_node="tools",
                                )

                            message.payload.text = text
                            await message.insert()
                            await obj_agent.sse_event.publish(
                                event_cls=ToolCallEndEvent,
                                event_type=EventType.TOOL_CALL_END,
                                text=text,
                                status="error" if "error" in observation else "success",
                                tool_call_id=message.id,
                                metadata={"attachments": chart_attachments},
                            )
                            await obj_agent.sse_event.publish(
                                event_cls=TextMessageEndEvent,
                                event_type=EventType.TEXT_MESSAGE_END,
                                message_id=message.id,
                                text=text,
                            )
                            is_message_start = False
                        elif (
                            event_type == LLMEventType.ON_CHAIN_START
                            and event["name"] == "ask_human"
                            and isinstance(event["data"]["input"]["messages"][-1], AIMessage)
                        ):
                            last_message: AIMessage = event["data"]["input"]["messages"][-1]
                            if (
                                last_message.tool_calls[0]["name"] == DEFAULT_FUNCTION_INTERRUPT
                                and not conv_db.user_collaboration.hitl
                            ):
                                func_call = last_message.tool_calls[0]
                                reason = func_call["args"]["collaboration_msg"]
                                await obj_agent.sse_event.publish(
                                    event_cls=CustomEvent,
                                    event_type=EventType.CUSTOM,
                                    name="user-collaboration-needs",
                                    value=reason,
                                )
                                is_hitl = True
                                if obj_agent.agent_db.type == AgentType.WORKER:
                                    try:
                                        agent_name = obj_agent.agent_db.name if obj_agent and obj_agent.agent_db else "Agent"
                                        await self.user_hanlder.send_hitl_reason_email(
                                            email_to=current_user.email,
                                            reason=reason,
                                            conv_id=conv_id,
                                            agent_name=agent_name,
                                        )
                                    except Exception:
                                        self.logger.exception("event=send-hitl-email-exception conv_id=%s", conv_id)
                        elif (
                            # Sent Thinking chunk event
                            event_type == LLMEventType.ON_CHAT_MODEL_STREAM
                            and before_event
                            in [
                                LLMEventType.ON_CHAT_MODEL_START,
                                LLMEventType.ON_CHAIN_STREAM,
                                LLMEventType.ON_CHAT_MODEL_STREAM,
                            ]
                            and isinstance(event["data"]["chunk"], AIMessageChunk)
                            and (
                                "reasoning" in event["data"]["chunk"].additional_kwargs  # OpenAI
                                or (
                                    isinstance(event["data"]["chunk"].content, list)
                                    and len(event["data"]["chunk"].content) > 0
                                    and "thinking" in event["data"]["chunk"].content[-1]
                                )  # Google
                            )
                        ):
                            # --- Handle thinking/reasoning events ---
                            msg_chunk: AIMessageChunk = event["data"]["chunk"]
                            # Extract thinking content
                            if (
                                "reasoning" in msg_chunk.additional_kwargs
                                and len(msg_chunk.additional_kwargs["reasoning"]["summary"]) > 0
                            ):
                                thinking_text = msg_chunk.additional_kwargs["reasoning"]["summary"][-1].get("text", "")
                            elif (
                                isinstance(msg_chunk.content, list)
                                and len(msg_chunk.content) > 0
                                and "thinking" in msg_chunk.content[-1]
                            ):
                                thinking_text = msg_chunk.content[-1]["thinking"]
                            else:
                                thinking_text = ""
                            if thinking_text:
                                if not is_message_start:
                                    # Start assistant message and thinking event
                                    message = Message(
                                        conv_id=conv_id,
                                        role=MessageRole.ASSISTANT,
                                        payload=MessagePayload(
                                            text="",
                                            thinking="",
                                        ),
                                    )
                                    await obj_agent.sse_event.publish(
                                        event_cls=TextMessageStartEvent,
                                        event_type=EventType.TEXT_MESSAGE_START,
                                        message_id=message.id,
                                    )
                                    is_message_start = True
                                if not is_thinking_active:
                                    await obj_agent.sse_event.publish(
                                        event_cls=ThinkingStartEvent,
                                        event_type=EventType.THINKING_START,
                                        title="Starting Reasoning Process",
                                    )
                                    is_thinking_active = True
                                    # Start thinking event with same message_id as message
                                    await obj_agent.sse_event.publish(
                                        event_cls=ThinkingTextMessageStartEvent,
                                        event_type=EventType.THINKING_TEXT_MESSAGE_START,
                                        message_id=message.id,
                                    )
                                # Content event (delta)
                                message.payload.thinking += thinking_text
                                await obj_agent.sse_event.publish(
                                    event_cls=ThinkingTextMessageContentEvent,
                                    event_type=EventType.THINKING_TEXT_MESSAGE_CONTENT,
                                    message_id=message.id,
                                    message=thinking_text,
                                )
                            # else: do not emit empty
                        elif (
                            # Sent Message chunk event
                            event_type == LLMEventType.ON_CHAT_MODEL_STREAM
                            and before_event
                            in [
                                LLMEventType.ON_CHAT_MODEL_START,
                                LLMEventType.ON_CHAIN_STREAM,
                                LLMEventType.ON_CHAT_MODEL_STREAM,
                            ]
                            and isinstance(event["data"]["chunk"], AIMessageChunk)
                            and event["data"]["chunk"].content
                        ):
                            if not is_message_start:
                                message = Message(
                                    conv_id=conv_id,
                                    role=MessageRole.ASSISTANT,
                                    payload=MessagePayload(
                                        text="",
                                    ),
                                )
                                await obj_agent.sse_event.publish(
                                    event_cls=TextMessageStartEvent,
                                    event_type=EventType.TEXT_MESSAGE_START,
                                    message_id=message.id,
                                    role="assistant",
                                )
                                is_message_start = True
                            else:
                                # If thinking was active, close it before starting text
                                if is_thinking_active:
                                    await obj_agent.sse_event.publish(
                                        event_cls=ThinkingTextMessageEndEvent,
                                        event_type=EventType.THINKING_TEXT_MESSAGE_END,
                                        message_id=message.id,
                                    )
                                    await obj_agent.sse_event.publish(
                                        event_cls=ThinkingEndEvent,
                                        event_type=EventType.THINKING_END,
                                    )
                                    is_thinking_active = False
                            msg_chunk: AIMessageChunk = event["data"]["chunk"]
                            if isinstance(msg_chunk.content, list):
                                if len(msg_chunk.content) > 0 and "text" in msg_chunk.content[-1]:
                                    text = msg_chunk.content[-1]["text"]
                                else:
                                    text = ""
                            else:
                                text = msg_chunk.content
                            message.payload.text += text
                            await obj_agent.sse_event.publish(
                                event_cls=TextMessageContentEvent,
                                event_type=EventType.TEXT_MESSAGE_CONTENT,
                                message_id=message.id,
                                message=text,
                            )
                        elif (
                            event_type == LLMEventType.ON_CHAT_MODEL_END
                            and isinstance(event["data"]["output"], AIMessage)
                            and event["data"]["output"].content
                        ):
                            # Publish final message
                            if is_message_start and not is_thinking_active:
                                content = event["data"]["output"].content
                                if isinstance(content, list):
                                    if len(content) > 0 and "text" in content[-1]:
                                        text = content[-1] if isinstance(content[-1], str) else content[-1]["text"]
                                    elif len(content) > 0:
                                        text = content[-1]
                                    else:
                                        text = ""
                                else:
                                    text = content
                                message.payload.text = text
                                await message.insert()
                                await obj_agent.sse_event.publish(
                                    event_cls=TextMessageEndEvent,
                                    event_type=EventType.TEXT_MESSAGE_END,
                                    message_id=message.id,
                                    text=text,
                                )
                                is_message_start = False
                        before_event = event_type
                    except ConnectionResetError:
                        self.logger.warning(
                            'event=client_disconnected message="Client disconnected during streaming for conversation %s"',
                            conv_id,
                        )
                        break

            # Ensure sent TEXT_MESSAGE_END event
            if is_thinking_active:
                await obj_agent.sse_event.publish(
                    event_cls=ThinkingTextMessageEndEvent,
                    event_type=EventType.THINKING_TEXT_MESSAGE_END,
                    message_id=message.id,
                )
                await obj_agent.sse_event.publish(
                    event_cls=ThinkingEndEvent,
                    event_type=EventType.THINKING_END,
                )
                is_thinking_active = False

            if is_message_start:
                await message.insert()
                await obj_agent.sse_event.publish(
                    event_cls=TextMessageEndEvent,
                    event_type=EventType.TEXT_MESSAGE_END,
                    message_id=message.id,
                    text=text,
                )
                is_message_start = False
            await obj_agent.sse_event.publish(
                event_cls=RunFinishedEvent,
                event_type=EventType.RUN_FINISHED,
                run_id=run_id,
                thread_id=conv_id,
            )

            if not is_hitl and obj_agent.agent_db.type == AgentType.WORKER:
                try:
                    agent_name = obj_agent.agent_db.name if obj_agent and obj_agent.agent_db else "Agent"
                    await self.user_hanlder.send_success_email(
                        email_to=current_user.email,
                        conv_id=conv_id,
                        agent_name=agent_name,
                    )
                except Exception:
                    self.logger.exception("event=send-success-email-exception conv_id=%s", conv_id)

        except Exception as e:
            self.logger.exception('event=stream_error message="Error in stream"')
            await obj_agent.sse_event.publish(
                event_cls=RunErrorEvent,
                event_type=EventType.RUN_ERROR,
                message=str(e),
            )
            raise
