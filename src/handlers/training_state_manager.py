from datetime import datetime
from typing import Any

from redis.asyncio import Redis

from helpers.pubsub import RedisPubSubManager
from models.document_content import DocumentContent
from models.document_work_item import DocumentWorkItem
from utils.constants import TIMEZONE, TRAINING_POSTFIX, TRAINING_PREFIX
from utils.enums import DocWorkItemState, RedisChannelName
from utils.logger.custom_logging import LoggerMixin


class TrainingStatusManager(LoggerMixin):
    """
    Manages training status in Redis for failover handling when backend crashes.
    """

    def __init__(self, redis: Redis, redis_pubsub_manager: RedisPubSubManager) -> None:
        super().__init__()
        self._redis: Redis = redis
        self._training_prefix = TRAINING_PREFIX
        self._redis_pubsub_manager = redis_pubsub_manager

    async def set_training_status(
        self,
        dwi_id: str,
        dt_id: str,
        status: str = DocWorkItemState.IN_PROCESS,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """
        Set training status for a DWI in Redis.

        Args:
            dwi_id: Document Work Item ID
            status: Training status (pending, in_process, completed, failed)
            metadata: Additional metadata to store

        Returns:
            bool: True if successful, False otherwise
        """
        key = f"{self._training_prefix}{dwi_id}{TRAINING_POSTFIX}"

        data = {
            "status": status,
            "dwi_id": dwi_id,
            "dt_id": dt_id,
        }

        if metadata:
            data.update(metadata)

        await self._redis.hset(key, mapping=data)

        self.logger.info(
            'event=training-status-set dwi_id=%s status=%s message="Training status set in Redis"',
            dwi_id,
            status,
        )
        return True

    async def remove_training_status(self, dwi_id: str) -> bool:
        """
        Remove training status for a DWI from Redis (when training completes successfully).

        Args:
            dwi_id: Document Work Item ID

        Returns:
            bool: True if successful, False otherwise
        """
        key = f"{self._training_prefix}{dwi_id}{TRAINING_POSTFIX}"

        await self._redis.delete(key)

        self.logger.info(
            'event=training-status-removed dwi_id=%s message="Training status removed from Redis"',
            dwi_id,
        )
        return True

    async def cleanup_stale_training_items(self) -> int:
        """
        Clean up stale training items that have exceeded the timeout.
        Updates their status to FAILED in the database and removes from Redis.

        Returns:
            int: Number of items cleaned up
        """
        pattern = f"{self._training_prefix}*"
        keys = await self._redis.keys(pattern)

        cleaned_count = 0

        for key in keys:
            data = await self._redis.hgetall(key)
            if not data:
                continue

            try:
                dwi_id = data.get("dwi_id")
                dt_id = data.get("dt_id")
                if dwi_id and dt_id:
                    success = await self._update_dwi_status_to_failed(dwi_id)
                    if success:
                        await self._redis.delete(key)
                        cleaned_count += 1
                        await self._publish_failed_event(dwi_id, dt_id)

            except (ValueError, TypeError):
                await self._redis.delete(key)
                cleaned_count += 1

        if cleaned_count > 0:
            self.logger.info(
                'event=stale-training-items-cleaned count=%d message="Cleaned up stale training items"',
                cleaned_count,
            )
        return cleaned_count

    async def _update_dwi_status_to_failed(self, dwi_id: str) -> bool:
        """
        Update DWI status to FAILED in the database.

        Args:
            dwi_id: Document Work Item ID

        Returns:
            bool: True if successful, False otherwise
        """
        dwi_db = await DocumentWorkItem.get(dwi_id)
        dc_db = await DocumentContent.find_one(DocumentContent.dwi_id == dwi_id)
        if dwi_db:
            dwi_db.state = DocWorkItemState.FAILED
            dwi_db.last_run = datetime.now(TIMEZONE)
            await dwi_db.save()

            self.logger.info(
                'event=dwi-status-updated-to-failed dwi_id=%s message="DWI status updated to FAILED due to timeout"',
                dwi_id,
            )

        if dc_db:
            existing_metadata = dc_db.metadata or {}
            logs = {
                "logs": {
                    "field": {
                        "error_detail": "Timeout occurred in backend",
                    },
                    "table": {
                        "error_detail": "Timeout occurred in backend",
                    },
                },
            }

            existing_metadata.update(logs)
            dc_db.metadata = existing_metadata
            await dc_db.save()

            self.logger.info(
                'event=dwi-status-failed-timeout dwi_id=%s message="Marked DWI as FAILED due to backend timeout"',
                dwi_id,
            )
        return True

    async def _publish_failed_event(self, dwi_id: str, dt_id: str) -> None:
        """
        Publish a failed event notification.

        Args:
            dwi_id: Document Work Item ID
        """
        dwi_db = await DocumentWorkItem.get(dwi_id)
        if dwi_db:
            message = {
                "dwi": dwi_id,
                "state": DocWorkItemState.FAILED.value,
            }

            channel = f"{RedisChannelName.DOCUMENT_TYPE}:{dt_id}"
            await self._redis_pubsub_manager.publish(channel, message)

            self.logger.info(
                'event=failover-event-published dwi_id=%s dt_id=%s message="Failed event published"',
                dwi_id,
                dt_id,
            )
