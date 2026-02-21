import asyncio
from collections.abc import AsyncGenerator
from typing import Any

import orjson
from fastapi import Request
from redis.asyncio import Redis
from redis.asyncio.client import PubSub
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError

from utils.logger.custom_logging import LoggerMixin


class RedisPubSubManager(LoggerMixin):
    def __init__(self, redis: Redis) -> None:
        super().__init__()
        self._redis: Redis = redis
        self._subscribers: dict[str, dict[str, PubSub]] = {}
        self.conv_session_manager: dict[str, tuple[any, list[Request]]] = {}

    async def connect(self) -> bool:
        """Initialize Redis connection pool and connection"""
        try:
            await self._redis.ping()
        except RedisError:
            self.logger.exception(
                "event=redis-connection-error message=Failed to connect to Redis",
            )
            return False
        return True

    def _encode_message(self, message: str | bytes | dict | list) -> str | None:
        """Encode message to string format suitable for Redis"""
        if isinstance(message, str | bytes):
            return message if isinstance(message, str) else message.decode("utf-8")
        try:
            return orjson.dumps(message).decode("utf-8")
        except (TypeError, ValueError):
            self.logger.exception(
                "event=redis-message-encode-error message=Failed to encode message for Redis",
            )
            return None

    async def publish(self, channel: str, message: str | bytes | dict | list) -> None:
        """Publish a message to a channel with retry mechanism"""
        if not self._redis:
            await self.connect()

        encoded_message = self._encode_message(message)
        if encoded_message is None:
            self.logger.error(
                "event=redis-publish-error message=Failed to encode message for publishing",
            )
            return
        await self._redis.publish(channel, encoded_message)

    async def subscribe(self, channel: str, connection_id: str) -> PubSub:
        """Subscribe to a channel with a specific connection ID"""
        if not self._redis:
            await self.connect()

        if channel not in self._subscribers:
            self._subscribers[channel] = {}

        if connection_id not in self._subscribers[channel]:
            pubsub = self._redis.pubsub()
            await pubsub.subscribe(channel)
            self._subscribers[channel][connection_id] = pubsub

        return self._subscribers[channel][connection_id]

    async def unsubscribe(self, channel: str, connection_id: str) -> None:
        """Unsubscribe from a channel for a specific connection"""
        if channel in self._subscribers and connection_id in self._subscribers[channel]:
            subscriber = self._subscribers[channel][connection_id]
            try:
                await subscriber.unsubscribe()
                await subscriber.close()
            finally:
                del self._subscribers[channel][connection_id]
                if not self._subscribers[channel]:
                    del self._subscribers[channel]

    async def prune_disconnected_session(
        self,
        conv_id: str,
    ) -> None:
        """Unsubscribe a request if it is disconnected."""
        if conv_id in self.conv_session_manager:
            _, requests = self.conv_session_manager[conv_id]
            for request in requests:
                if await request.is_disconnected():
                    self.logger.info(
                        'event=worker_agent_request_disconnected conv_id=%s message="Request for conversation is disconnected"',
                        conv_id,
                    )
                    self.unsubscribe_request(conv_id, request)
        else:
            self.logger.warning(
                'event=worker_agent_session_not_found conv_id=%s message="Conversation session not found for unsubscription"',
                conv_id,
            )

    def unsubscribe_request(self, conv_id: str, request: Request) -> None:
        """Unsubscribe a request from the conversation session."""
        if conv_id not in self.conv_session_manager:
            return

        _, requests = self.conv_session_manager[conv_id]
        if request in requests:
            requests.remove(request)
            if not requests:
                del self.conv_session_manager[conv_id]
                self.logger.info(
                    "event=worker_agent_unsubscribed conv_id=%s "
                    'message="Request unsubscribed and no requests left for conversation"',
                    conv_id,
                )
        else:
            self.logger.warning(
                'event=worker_agent_unsubscribe_failed conv_id=%s message="Request not found in the session for conversation"',
                conv_id,
            )

    async def cleanup_empty_conv_session(
        self,
        conv_id: str,
    ) -> None:
        """Delete the conversation session if no requests are connected."""
        if conv_id in self.conv_session_manager:
            _, requests = self.conv_session_manager[conv_id]
            if not requests:
                await asyncio.sleep(delay=2)
                del self.conv_session_manager[conv_id]
                self.logger.info(
                    "event=worker_agent_session_deleted conv_id=%s "
                    'message="Conversation session deleted due to no connected requests"',
                    conv_id,
                )
            else:
                self.logger.debug(
                    "event=worker_agent_session_not_deleted conv_id=%s "
                    'message="Conversation session still has connected requests"',
                    conv_id,
                )
        else:
            self.logger.warning(
                'event=worker_agent_session_not_found conv_id=%s message="Conversation session not found for deletion"',
                conv_id,
            )

    async def get_messages(
        self,
        channel: str,
        ignore_subscribe_messages: bool = True,
    ) -> AsyncGenerator[Any, None]:
        """Get messages from a channel as an async generator with automatic reconnection"""
        if not self._redis:
            await self.connect()

        connection_id = f"{channel}_{id(asyncio.current_task())}"

        while True:
            try:
                pubsub = await self.subscribe(channel, connection_id)
                while True:
                    try:
                        message = await pubsub.get_message(
                            ignore_subscribe_messages=ignore_subscribe_messages,
                            timeout=15.0,
                        )
                        if message is not None:
                            try:
                                data = orjson.loads(message["data"])
                            except (orjson.JSONDecodeError, TypeError):
                                data = message["data"]
                            yield data
                        else:
                            yield {"type": "heartbeat"}
                    except (RedisError, RedisConnectionError) as e:
                        self.logger.warning(
                            'event=redis-connection-error error=%s message="Redis connection error. Attempting to reconnect!"',
                            e,
                        )
                        await self.connect()
                        pubsub = await self.subscribe(channel, connection_id)
            except Exception as e:
                self.logger.warning(
                    'event=redis-error error=%s message="Unhandled error in get_messages"',
                    e,
                )
            finally:
                if "conv" in str(channel.split(":")[1]):
                    conv_id = channel.split(":")[1]
                    await self.prune_disconnected_session(conv_id)
                    await self.cleanup_empty_conv_session(conv_id)
                await self.unsubscribe(channel, connection_id)
