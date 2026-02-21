import asyncio
import mimetypes
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from beanie.operators import In
from fastapi import UploadFile

from handlers.agents import ConversationalAgentHandler, WorkerAgentHandler
from handlers.document import DocumentHandler
from initializer import redis_pubsub_manager
from models.agent import Agent
from models.conversation import Conversation
from models.document_work_item import DocumentWorkItem
from models.message import Message
from schemas.conversation import ConversationFileResponse, ConversationInput
from schemas.message import BaseAttachment, HistoricalMessages
from schemas.message import BaseMessage as ResponseBaseMessage
from utils.checkpointer import delete_thread_from_checkpoint
from utils.constants import DEFAULT_CONVERSATION_FILE_FOLDER, TIMEZONE
from utils.logger.custom_logging import LoggerMixin

worker_agent_handler = WorkerAgentHandler()
conversational_agent_handler = ConversationalAgentHandler()


class ConversationHandler(LoggerMixin):
    def __init__(self) -> None:
        super().__init__()
        self.document_handler = DocumentHandler()

    async def upload_asset_to_conversation(
        self,
        conv_id: str,
        files: list[UploadFile],
    ) -> list[BaseAttachment] | None:
        """Upload files/assets to storage and return attachment metadata for the conversation.

        Returns list[BaseAttachment] on success; None on failure or if conversation not found.
        """
        conv_db = await Conversation.get(conv_id)
        if conv_db is None:
            self.logger.error(
                'event=upload-asset-failed message="Not found conversation with id: conv_id=%s"',
                conv_id,
            )
            return None

        if not files:
            return []

        async def upload_one(file: UploadFile) -> BaseAttachment | None:
            try:
                object_path = await self.document_handler.upload_document(
                    file=file,
                    document_type_name=DEFAULT_CONVERSATION_FILE_FOLDER,
                    document_format_name=conv_id,
                    original_filename=file.filename,
                )
                if object_path is None:
                    return None
                presigned_map = await self.document_handler.create_presigned_urls(
                    object_names=[object_path],
                    inline=True,
                )
                return BaseAttachment(
                    name=file.filename,
                    uri=presigned_map.get(object_path, ""),
                    mime_type=file.content_type or "application/octet-stream",
                    download_uri=object_path,
                )
            except Exception:
                self.logger.exception(
                    "event=upload-asset-exception conv_id=%s filename=%s",
                    conv_id,
                    getattr(file, "filename", ""),
                )
                return None

        results: list[BaseAttachment | None] = [None] * len(files)
        async with asyncio.TaskGroup() as tg:
            for idx, f in enumerate(files):

                async def runner(i: int, uf: UploadFile) -> None:
                    results[i] = await upload_one(uf)

                tg.create_task(runner(idx, f))

        if any(r is None for r in results):
            self.logger.error(
                "event=upload-asset-failed message=one-or-more-uploads-failed conv_id=%s",
                conv_id,
            )
            return None
        return [r for r in results if r is not None]

    async def delete_asset_from_conversation(
        self,
        conv_id: str,
        asset_uri: str,
    ) -> bool:
        """Delete an uploaded file/asset from storage by its uri for the given conversation.

        Returns True on success; False on failure or if conversation not found.
        """
        conv_db = await Conversation.get(conv_id)
        if conv_db is None:
            self.logger.error(
                'event=delete-asset-failed message="Not found conversation with id: conv_id=%s"',
                conv_id,
            )
            return False

        if not asset_uri:
            self.logger.error(
                "event=delete-asset-failed message=asset_uri-is-empty conv_id=%s",
                conv_id,
            )
            return False

        deleted = await self.document_handler.delete_document(object_path=asset_uri)
        if not deleted:
            self.logger.error(
                "event=delete-asset-failed message=delete-document-returned-false conv_id=%s asset_uri=%s",
                conv_id,
                asset_uri,
            )
            return False
        return True

    async def get_download_urls_for_assets(
        self,
        conv_id: str,
        asset_uris: list[str],
    ) -> list[str] | None:
        """Generate downloadable URLs for given asset URIs in a conversation.

        Returns list[str] on success; None on failure or if conversation not found.
        """
        conv_db = await Conversation.get(conv_id)
        if conv_db is None:
            self.logger.error(
                'event=get-download-urls-failed message="Not found conversation with id: conv_id=%s"',
                conv_id,
            )
            return None

        if not asset_uris:
            return []

        presigned_map = await self.document_handler.create_presigned_urls(
            object_names=asset_uris,
            inline=False,
        )
        if presigned_map is None:
            self.logger.error(
                "event=get-download-urls-failed message=presign-returned-none conv_id=%s",
                conv_id,
            )
            return None

        # Keep the order as input and filter out missing ones
        return [presigned_map[u] for u in asset_uris if u in presigned_map]

    async def _create_conversation(
        self,
        agent_id: str,
        dwi_id: str | None = None,
    ) -> tuple[str | None, str]:
        self.logger.info(
            "event=starting-creating-new-conversation",
        )
        agent_db = await Agent.find_one(Agent.id == agent_id)
        dwi_db = await DocumentWorkItem.find_one(DocumentWorkItem.id == dwi_id)
        if dwi_id is not None:
            existed_conv = await Conversation.find_one(
                Conversation.agent_id == agent_id,
                Conversation.dwi_id == dwi_id,
            )
            if existed_conv is not None:
                self.logger.error(
                    'event=creating-new-conversation-failed message="Existed conversation with agent_id=%s and dwi_id=%s"',
                    agent_id,
                    dwi_id,
                )
                return None, f"Existed conversation with agent_id={agent_id} and dwi_id={dwi_id}"

        if agent_db is None:
            self.logger.error(
                'event=creating-new-conversation-failed message="Not found agent config with id: agent_id=%s"',
                agent_id,
            )
            return None, f"Not found agent config with id: agent_id={agent_id}"

        if dwi_id and dwi_db is None:
            self.logger.error(
                'event=creating-new-conversation-failed message="Not found document work item with id: dwi_id=%s"',
                dwi_id,
            )
            return None, f"Not found document work item with id: dwi_id={agent_id}"

        conv_name = f"Work Item {dwi_id}" if dwi_id else f"Conversation {uuid4()!s}"
        new_conv = Conversation(
            agent_id=agent_id,
            name=conv_name,
        )
        if dwi_id is not None:
            new_conv.dwi_id = dwi_id
        await new_conv.insert()
        return new_conv.id, "New conversation created successfully"

    async def create_new_conversations(
        self,
        conv_input: ConversationInput,
    ) -> list[str] | None:
        self.logger.info(
            "event=starting-creating-new-conversations",
        )
        new_convs: list[tuple[str | None, str]] = []
        if len(conv_input.dwi_ids) == 0:
            new_conv = await self._create_conversation(agent_id=conv_input.agent_id)
            new_convs.append(new_conv[0])
        else:
            existed_convs = await Conversation.find(
                Conversation.agent_id == conv_input.agent_id,
                In(Conversation.dwi_id, conv_input.dwi_ids),
            ).to_list()
            if existed_convs:
                return None

            async with asyncio.TaskGroup() as task_group:
                tasks = [
                    task_group.create_task(
                        self._create_conversation(
                            agent_id=conv_input.agent_id,
                            dwi_id=dwi_id,
                        ),
                    )
                    for dwi_id in conv_input.dwi_ids
                ]
            new_convs = [task.result()[0] for task in tasks]
        return new_convs

    async def delete_conversation(
        self,
        conv_id: str,
    ) -> bool:
        self.logger.debug(
            "event=starting-deleting-conversation conv_id=%s",
            conv_id,
        )

        conv_db = await Conversation.get(conv_id)

        if conv_db is None:
            self.logger.error(
                'event=deleting-conversation-failed message="Not found conversation with id: conv_id=%s"',
                conv_id,
            )
            return False

        messages_count = 0
        delete_result = await Message.find(Message.conv_id == conv_id).delete()
        messages_count = delete_result.deleted_count

        if messages_count > 0:
            self.logger.info(
                "event=conversation-messages-deleted conv_id=%s messages_count=%d",
                conv_id,
                messages_count,
            )

        if conv_id in redis_pubsub_manager.conv_session_manager:
            del redis_pubsub_manager.conv_session_manager[conv_id]
            self.logger.info(
                "event=conversation-redis-session-cleaned conv_id=%s",
                conv_id,
            )
        await delete_thread_from_checkpoint(thread_id=conv_id)
        await self.document_handler.delete_documents(object_paths=[file.uri for file in conv_db.files])
        await conv_db.delete()
        self.logger.debug(
            "event=conversation-deleted-successfully conv_id=%s messages_deleted=%d",
            conv_id,
            messages_count,
        )
        return True

    async def update_conversation_name(
        self,
        conv_id: str,
        new_name: str,
    ) -> bool:
        self.logger.info(
            "event=starting-updating-conversation-name conv_id=%s",
            conv_id,
        )
        conv_db = await Conversation.get(conv_id)

        if conv_db is None:
            self.logger.error(
                'event=updating-conversation-name-failed message="Not found conversation with id: conv_id=%s"',
                conv_id,
            )
            return False

        conv_db.name = new_name
        conv_db.last_updated = datetime.now(TIMEZONE)
        await conv_db.save()

        self.logger.info(
            "event=conversation-name-updated-successfully conv_id=%s new_name=%s",
            conv_id,
            new_name,
        )
        return True

    async def _get_history_message_from_db(
        self,
        conv_id: str,
        offset: int,
        limit: int,
    ) -> tuple[int, list[ResponseBaseMessage] | None]:
        total_messages = await Message.find(Message.conv_id == conv_id).count()
        messages_list = (
            await Message.find(
                Message.conv_id == conv_id,
                projection_model=ResponseBaseMessage,
            )
            .sort(
                ("created_at", -1),
            )
            .skip(offset)
            .limit(limit)
            .to_list()
        )

        if not messages_list:
            return 0, None
        messages_list.reverse()
        return total_messages, messages_list

    async def get_conversation_history(
        self,
        conv_id: str,
        limit: int,
        offset: int,
    ) -> HistoricalMessages | None:
        """Get conversation history with events from DB using Beanie Message model"""
        conv_db = await Conversation.get(conv_id)
        if conv_db is None:
            return None

        total_messages, base_messages = await self._get_history_message_from_db(
            conv_id=conv_id,
            offset=offset,
            limit=limit,
        )
        if base_messages is None:
            return HistoricalMessages(
                conv_id=conv_id,
                metadata={
                    "dwi_id": conv_db.dwi_id,
                    "user_collaboration": conv_db.user_collaboration,
                },
            )

        # Generate presigned URLs for all attachments found in the messages
        attachment_object_names: set[str] = set()
        for msg in base_messages:
            if getattr(msg, "metadata", None) and getattr(msg.metadata, "attachments", None):
                for att in msg.metadata.attachments:
                    if getattr(att, "uri", None):
                        attachment_object_names.add(att.uri)

        if attachment_object_names:
            presigned_map = await self.document_handler.create_presigned_urls(
                object_names=list(attachment_object_names),
                inline=True,
            )
            if presigned_map:
                for msg in base_messages:
                    if getattr(msg, "metadata", None) and getattr(msg.metadata, "attachments", None):
                        for att in msg.metadata.attachments:
                            if getattr(att, "uri", None) and att.uri in presigned_map:
                                att.download_uri = att.uri
                                att.uri = presigned_map[att.uri]

        return HistoricalMessages(
            conv_id=conv_id,
            total=total_messages,
            historical_messages=base_messages,
            metadata={
                "dwi_id": conv_db.dwi_id,
                "user_collaboration": conv_db.user_collaboration,
            },
        )

    async def get_conversation_files(
        self,
        conv_id: str,
    ) -> list[ConversationFileResponse] | None:
        """Get all files associated with a conversation.

        Returns list[ConversationFileResponse] if conversation exists, None otherwise.
        """
        self.logger.info(
            "event=starting-get-conversation-files conv_id=%s",
            conv_id,
        )

        conv_db = await Conversation.get(conv_id)
        if conv_db is None:
            self.logger.error(
                'event=get-conversation-files-failed message="Not found conversation with id: conv_id=%s"',
                conv_id,
            )
            return None

        # Early return for empty files list
        if not conv_db.files:
            self.logger.info(
                "event=get-conversation-files-success conv_id=%s file_count=0",
                conv_id,
            )
            return []

        # Use list comprehension for better performance and readability
        file_responses = [
            ConversationFileResponse(
                name=Path(conv_file.uri).name,
                uri=conv_file.uri,
                mime_type=mimetypes.guess_type(Path(conv_file.uri).name)[0] or "application/octet-stream",
                created_at=conv_file.created_at,
            )
            for conv_file in conv_db.files
        ]

        self.logger.info(
            "event=get-conversation-files-success conv_id=%s file_count=%d",
            conv_id,
            len(file_responses),
        )
        return file_responses

    async def delete_conversations_by_ids(
        self,
        conv_ids: list[str],
    ) -> dict[str, bool]:
        """
        Delete multiple conversations concurrently.
        Returns a dict mapping conv_id to True (success) or False (fail).
        """
        results: dict[str, bool] = {}

        async def delete_one(conv_id: str) -> None:
            try:
                result = await self.delete_conversation(conv_id)
                results[conv_id] = result
            except Exception:
                self.logger.exception(
                    "event=deleting-multi-conversation-failed conv_id=%s",
                    conv_id,
                )
                results[conv_id] = False

        async with asyncio.TaskGroup() as tg:
            for conv_id in conv_ids:
                tg.create_task(delete_one(conv_id))
        return results
