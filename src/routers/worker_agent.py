import asyncio
from collections.abc import AsyncGenerator
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from fastapi.routing import APIRouter

from helpers.jwt_auth import get_current_user_unified_cached, require_scopes_cached
from initializer import redis_pubsub_manager, worker_agent_handler
from schemas.agent import AgentStreamRequest
from schemas.response import BasicResponse
from schemas.user import UserResponse
from utils.enums import APIScope, RedisChannelName

router = APIRouter(
    prefix="/worker-agent",
    dependencies=[
        Depends(require_scopes_cached(APIScope.AGENT_WORKFLOW)),
    ],
)


async def stream_event(conv_id: str) -> AsyncGenerator[Any, None]:
    """Stream events from Redis channel."""
    try:
        async for message in redis_pubsub_manager.get_messages(f"{RedisChannelName.CONVERSATION}:{conv_id}"):
            if isinstance(message, dict) and message.get("type") == "heartbeat":
                # Yield an SSE comment as a keep-alive signal
                yield ":heartbeat\n\n"
            else:
                yield message
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error streaming events: {e!s}",
        ) from e


@router.post(
    "/{conv_id}/chat",
)
async def chat(
    conv_id: str,
    stream_request: AgentStreamRequest,
    current_user: Annotated[UserResponse, Depends(get_current_user_unified_cached)],
) -> BasicResponse:
    """
    Handle chat requests with the worker agent.

    Args:
        request: The FastAPI request object
        conv_id: The unique conversation identifier
        stream_request: The chat request containing the question

    Returns:
        BasicResponse: A response containing the agent's response

    **Required Scopes:** `agent_workflow`
    """
    try:
        await asyncio.sleep(0.05)
        # store a reference to the created task so it can be awaited/cancelled or inspected
        task = asyncio.create_task(
            worker_agent_handler.achat(
                conv_id=conv_id,
                question=stream_request.question,
                assets=stream_request.assets,
                current_user=current_user,
            ),
        )
        # optional: ensure exceptions from the background task are at least surfaced to the event loop
        task.add_done_callback(lambda t: t.exception() if t.cancelled() is False else None)
        return BasicResponse(
            status="success",
            message="Completed send question to agent.",
            data={"conv_id": conv_id},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing chat request: {e!s}",
        ) from e


@router.get(
    "/{conv_id}/stream",
    response_class=StreamingResponse,
)
async def stream_events(
    request: Request,
    conv_id: str,
) -> StreamingResponse:
    """
    Stream events for a specific conversation using Server-Sent Events.

    Args:
        request: The FastAPI request object
        conv_id: The unique conversation identifier

    Returns:
        StreamingResponse: A streaming response containing SSE events

    **Required Scopes:** `agent_workflow`
    """
    await worker_agent_handler.initialize(conv_id, request)
    return StreamingResponse(
        stream_event(conv_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
        },
    )
