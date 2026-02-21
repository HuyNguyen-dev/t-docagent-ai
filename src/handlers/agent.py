import asyncio
import re
from datetime import datetime
from uuid import uuid4

import orjson
from beanie.operators import In
from fastapi import UploadFile

from handlers.action_package import ActionPackageHandler
from handlers.agents.conversation import ConversationalAgentHandler
from handlers.agents.worker import WorkerAgentHandler
from handlers.runbook import RunbookHandler
from initializer import redis_pubsub_manager
from models.action_package import ActionPackage
from models.agent import Agent
from models.conversation import Conversation
from models.document_type import DocumentType
from models.message import Message
from models.runbook import RunBook
from schemas.agent import (
    AgentDashBoardItemResponse,
    AgentDefaultRunBook,
    AgentInput,
    AgentResponse,
    AgentRunbook,
    AgentRunbookInput,
    AgentUpdate,
)
from schemas.conversation import ConversationItemResponse
from schemas.export import AgentExport, MetadataExport
from schemas.response import Page, PaginatedMetadata
from schemas.runbook import RunbookInput
from utils.checkpointer import delete_thread_from_checkpoint
from utils.constants import TIMEZONE
from utils.enums import AgentType
from utils.logger.custom_logging import LoggerMixin


class AgentHandler(LoggerMixin):
    def __init__(self) -> None:
        self.action_package_handler = ActionPackageHandler()
        self.runbook_handler = RunbookHandler()
        super().__init__()

    async def create_new_agent(
        self,
        agent_input: AgentInput,
    ) -> str | None:
        self.logger.info(
            "event=starting-creating-new-agent",
        )
        if not agent_input.dt_id and agent_input.type == AgentType.WORKER:
            self.logger.error(
                'event=creating-new-agent-failed message="Work Agent must have dt_id. Please check again"',
            )
            return None
        if agent_input.dt_id and agent_input.type == AgentType.CONVERSATION:
            self.logger.error(
                "event=creating-new-agent-failed "
                'message="The Conversation Agent does not need to provide dt_id. Please check again"',
            )
            return None
        if agent_input.type == AgentType.WORKER:
            dt_db = await DocumentType.find_one(DocumentType.id == agent_input.dt_id)
            if dt_db is None:
                self.logger.error(
                    'event=creating-new-agent-failed message="Not found document type with id: dt_id=%s"',
                    agent_input.dt_id,
                )
                return None
        agent_id = f"agt-{uuid4()!s}"
        rb_name, rb_version = await self.runbook_handler.create_runbook(
            runbook_input=RunbookInput(
                **agent_input.run_book.model_dump(),
                name=agent_id,
            ),
        )
        # Handler update created by is user_id
        agent_update_data = agent_input.model_dump(exclude_unset=True)
        agent_update_data.pop("run_book")
        new_agent = Agent(
            _id=agent_id,
            **agent_update_data,
            run_book=AgentRunbook(
                name=rb_name,
                version=rb_version,
            ),
            created_by="admin",
            created_at=agent_input.run_book.created_at,
        )
        await new_agent.insert()
        return new_agent.id

    async def get_all_agents(
        self,
        q: str = "",
        page: int = 1,
        page_size: int = 10,
        agent_type: AgentType | None = None,
    ) -> Page | None:
        query_filter = {}
        if q:
            safe_search_term = re.escape(q)
            query_filter["name"] = {"$regex": safe_search_term, "$options": "i"}
        if agent_type is not None:
            query_filter["type"] = agent_type

        n_skip = (page - 1) * page_size
        cursor_query = Agent.find(query_filter)
        total_items = await cursor_query.count()
        agents_db = (
            await cursor_query.sort(
                ("created_at", -1),
            )
            .skip(n_skip)
            .limit(page_size)
            .to_list()
        )
        agent_responses = [
            AgentDashBoardItemResponse(
                **agent.model_dump(),
                n_action_packages=len(agent.action_packages),
            )
            for agent in agents_db
        ]
        total_pages = (total_items + page_size - 1) // page_size or 1
        return Page(
            items=[agent.model_dump() for agent in agent_responses],
            metadata=PaginatedMetadata(
                page=min(page, total_pages),
                page_size=page_size,
                total_items=total_items,
                total_pages=total_pages,
            ),
        )

    async def get_all_agent_templates(
        self,
        q: str = "",
        page: int = 1,
        page_size: int = 10,
    ) -> Page | None:
        """
        Get all agent templates (agents with is_template=True).
        """
        query_filter = {"is_template": True}
        if q:
            safe_search_term = re.escape(q)
            query_filter["name"] = {"$regex": safe_search_term, "$options": "i"}

        n_skip = (page - 1) * page_size
        cursor_query = Agent.find(query_filter)
        total_items = await cursor_query.count()
        agents_db = (
            await cursor_query.sort(
                ("created_at", -1),
            )
            .skip(n_skip)
            .limit(page_size)
            .to_list()
        )
        agent_responses = [
            AgentDashBoardItemResponse(
                **agent.model_dump(),
                n_action_packages=len(agent.action_packages),
            )
            for agent in agents_db
        ]
        total_pages = (total_items + page_size - 1) // page_size or 1
        return Page(
            items=[agent.model_dump() for agent in agent_responses],
            metadata=PaginatedMetadata(
                page=min(page, total_pages),
                page_size=page_size,
                total_items=total_items,
                total_pages=total_pages,
            ),
        )

    async def get_agents_by_type(
        self,
        agent_type: AgentType,
        page: int = 1,
        page_size: int = 5,
    ) -> Page | None:
        """
        Get all agents filtered by type (Conversation/Worker).
        """
        query_filter = {"type": agent_type}
        n_skip = (page - 1) * page_size
        cursor_query = Agent.find(query_filter)
        total_items = await cursor_query.count()
        agents_db = await cursor_query.skip(n_skip).limit(page_size).to_list()
        total_pages = (total_items + page_size - 1) // page_size or 1
        return Page(
            items=[{"id": agent.id, "name": agent.name} for agent in agents_db],
            metadata=PaginatedMetadata(
                page=min(page, total_pages),
                page_size=page_size,
                total_items=total_items,
                total_pages=total_pages,
            ),
        )

    async def get_agent_by_id(
        self,
        agent_id: str,
    ) -> dict | None:
        agent_db = await Agent.find_one(Agent.id == agent_id)
        if agent_db is None:
            self.logger.debug(
                'event=retrieving-agent-by-id-failed message="Not found agent with id: agent_id=%s"',
                agent_id,
            )
            return None

        selected_dict = {action.id: action.action_selected for action in agent_db.action_packages}
        action_packages = await ActionPackage.find(
            In(ActionPackage.id, list(selected_dict.keys())),
        ).to_list()
        async with asyncio.TaskGroup() as tg:
            tasks = [
                tg.create_task(
                    self.action_package_handler.get_connection_details(ap),
                )
                for ap in action_packages
            ]
        action_detailed_results = [task.result() for task in tasks]

        agent_response = AgentResponse.from_db_model(agent_db).model_dump()
        agent_response["action_packages"] = [
            {
                **action.model_dump(),
                "action_selected": selected_dict.get(action.id),
            }
            for action in action_detailed_results
        ]
        return agent_response

    async def get_all_conversations_by_agent_id(
        self,
        agent_id: str,
        agent_type: AgentType = AgentType.WORKER,
        q: str = "",
        page: int = 1,
        page_size: int = 10,
    ) -> Page | None:
        n_skip = (page - 1) * page_size
        pipeline = [{"$match": {"agent_id": agent_id}}]

        if q:
            safe_search_term = re.escape(q)
            pipeline.append(
                {"$match": {"name": {"$regex": safe_search_term, "$options": "i"}}},
            )
        dwi_condition = (
            {
                "dwi_id": {"$regex": "^dwi-"},
            }
            if agent_type == AgentType.WORKER
            else {
                "dwi_id": "",
            }
        )
        pipeline.extend(
            [
                {"$match": dwi_condition},
                {"$sort": {"last_updated": -1}},
                {
                    "$facet": {
                        "data": [
                            {"$skip": n_skip},
                            {"$limit": page_size},
                            {
                                "$replaceRoot": {
                                    "newRoot": {
                                        "$mergeObjects": [
                                            {
                                                "id": "$_id",
                                                "name": "$name",
                                            },
                                        ],
                                    },
                                },
                            },
                        ],
                        "metadata": [{"$count": "total"}],
                    },
                },
            ],
        )
        aggregation_result = await Conversation.aggregate(pipeline).to_list()
        if not aggregation_result or not aggregation_result[0]["metadata"]:
            return Page()
        result_payload = aggregation_result[0]
        total_items = result_payload["metadata"][0]["total"]
        items = [ConversationItemResponse(**doc).model_dump() for doc in result_payload["data"]]
        return Page(
            items=items,
            metadata={
                "page": page,
                "page_size": page_size,
                "total_items": total_items,
                "total_pages": (total_items + page_size - 1) // page_size or 1,
            },
        )

    async def list_runbook_names_by_agent_id(self, agent_id: str) -> dict[str, str] | None:
        """List all runbook names associated with an agent."""
        agent_db = await Agent.find_one(Agent.id == agent_id)
        if agent_db:
            runbooks = await RunBook.find_many(RunBook.name == agent_db.run_book.name).sort((RunBook.last_updated, -1)).to_list()
            self.logger.info(
                'event=list-runbook-names-success message="Listed runbook names successfully" prms="agent_id=%s"',
                agent_id,
            )
            return [
                {
                    "name": runbook.name,
                    "version": runbook.version,
                    "created_at": runbook.created_at,
                    "agent_default": runbook.version == agent_db.run_book.version,
                }
                for runbook in runbooks
            ]

        self.logger.debug(
            'event=retrieving-runbook-names-failed message="Not found agent with id: agent_id=%s"',
            agent_id,
        )

        return None

    async def set_default_version(self, agent_id: str, default_runbook: AgentDefaultRunBook) -> bool:
        """Set the default version for a runbook."""
        agent_db = await Agent.find_one(Agent.id == agent_id)
        if agent_db:
            agent_db.run_book.name = default_runbook.name
            agent_db.run_book.version = default_runbook.version
            await agent_db.save()

            self.logger.info(
                (
                    "event=set-default-version-success "
                    'message="Set default version successfully" '
                    'prms="agent= %s name=%s, version=%s"'
                ),
                agent_id,
                default_runbook.name,
                default_runbook.version,
            )
            return True

        return False

    async def update_agent_by_id(
        self,
        agent_id: str,
        agent_update: AgentUpdate,
    ) -> Agent | None:
        """
        Update an agent by its ID with the provided AgentUpdate payload.
        """
        agent_db = await Agent.find_one(Agent.id == agent_id)
        if not agent_db:
            self.logger.error(
                'event=update-agent-failed message="Agent not found" agent_id=%s',
                agent_id,
            )
            return None

        if not agent_update.dt_id and agent_update.type == AgentType.WORKER:
            self.logger.error(
                'event=process-update-agent-failed message="Work Agent must have dt_id. Please check again"',
            )
            return None
        if agent_update.dt_id and agent_update.type == AgentType.CONVERSATION:
            self.logger.error(
                "event=process-update-agent-failed "
                'message="The Conversation Agent does not need to provide dt_id. Please check again"',
            )
            return False
        if agent_update.type == AgentType.WORKER:
            dt_db = await DocumentType.find_one(DocumentType.id == agent_update.dt_id)
            if dt_db is None:
                self.logger.error(
                    'event=process-update-agent-failed message="Not found document type with id: dt_id=%s"',
                    agent_update.dt_id,
                )
                return False

        update_data = agent_update.model_dump(exclude_unset=True)
        if update_data:
            await agent_db.set(update_data)

        self.logger.info(
            'event=update-agent-success message="Agent updated successfully" agent_id=%s',
            agent_id,
        )
        return agent_db

    async def delete_agent(
        self,
        agent_id: str,
    ) -> bool:
        self.logger.info(
            "event=starting-deleting-agent agent_id=%s",
            agent_id,
        )

        agent_db = await Agent.get(agent_id)
        if agent_db is None:
            self.logger.error(
                'event=deleting-agent-failed message="Not found agent with id: agent_id=%s"',
                agent_id,
            )
            return False

        convs = await Conversation.find(Conversation.agent_id == agent_id).to_list()
        conv_ids = [conv.id for conv in convs]

        if conv_ids:
            for conv_id in conv_ids:
                await delete_thread_from_checkpoint(conv_id)

            n_deleted_message = await Message.find(In(Message.conv_id, conv_ids)).delete()
            self.logger.info(
                "event=agent-messages-deleted agent_id=%s total_messages=%d",
                agent_id,
                n_deleted_message.deleted_count,
            )

            n_deleted_conv = await Conversation.find(In(Conversation.id, conv_ids)).delete()
            self.logger.info(
                "event=agent-conversations-deleted agent_id=%s n_conv=%d",
                agent_id,
                n_deleted_conv.deleted_count,
            )

        runbook_name = agent_db.run_book.name
        runbooks_deleted = await self.runbook_handler.delete_all_runbooks(runbook_name)
        if runbooks_deleted:
            self.logger.info(
                "event=agent-runbooks-deleted agent_id=%s runbook_name=%s",
                agent_id,
                runbook_name,
            )

        for conv_id in conv_ids:
            if conv_id in redis_pubsub_manager.conv_session_manager:
                del redis_pubsub_manager.conv_session_manager[conv_id]
                self.logger.info(
                    "event=agent-redis-session-cleaned agent_id=%s conv_id=%s",
                    agent_id,
                    conv_id,
                )

        await agent_db.delete()

        self.logger.info(
            'event=agent-deleted-successfully agent_id=%s message="Agent deleted successfully"',
            agent_id,
        )

        return True

    async def refresh_all_conv_by_agent_id(self, agent: Agent) -> bool:
        """Refresh all conversations by agent id."""
        agent_type = agent.type
        conversations = await Conversation.find(Conversation.agent_id == agent.id).to_list()

        if not conversations:
            self.logger.info("event=no-conversations-found agent_id=%s", agent.id)
            return True

        # Map agent types to their handlers
        handler_map = {
            AgentType.WORKER: WorkerAgentHandler(),
            AgentType.CONVERSATION: ConversationalAgentHandler(),
        }
        results = []
        try:
            async with asyncio.TaskGroup() as tg:
                tasks = [
                    tg.create_task(handler_map[agent_type].refresh_agent_by_conv_id(conv.id, agent))
                    for conv in conversations
                ]

            self.logger.info(
                "event=refresh-all-conv-success agent_id=%s count=%d",
                agent.id,
                len(conversations),
            )
            results = [task.result() for task in tasks]
        except* Exception as eg:
            # Handle ExceptionGroup from TaskGroup or other exceptions
            for exc in eg.exceptions if isinstance(eg, BaseExceptionGroup) else [eg]:
                self.logger.exception(
                    'event=refresh-conv-failed agent_id=%s error=%s message="Failed to refresh conversation"',
                    agent.id,
                    str(exc),
                )
            results.append(False)
        return all(results)

    async def refresh_action_connections(self, agent_id: str) -> list | None:
        """
        Refreshes the connection details of all action packages for the given agent.
        Returns the updated agent response with refreshed action package details.
        """
        agent_db = await Agent.find_one(Agent.id == agent_id)
        if agent_db is None:
            self.logger.debug(
                'event=refresh-action-connections-failed message="Not found agent with id: agent_id=%s"',
                agent_id,
            )
            return None

        selected_dict = {action.id: action.action_selected for action in agent_db.action_packages}
        action_packages = await ActionPackage.find(
            In(ActionPackage.id, list(selected_dict.keys())),
        ).to_list()
        async with asyncio.TaskGroup() as tg:
            tasks = [
                tg.create_task(
                    self.action_package_handler.get_connection_details(ap),
                )
                for ap in action_packages
            ]
        action_detailed_results = [task.result() for task in tasks]
        return [
            {
                **action.model_dump(),
                "action_selected": selected_dict.get(action.id),
            }
            for action in action_detailed_results
        ]

    async def export_agent(self, agent_id: str) -> AgentExport | None:
        """Export agents by ID"""
        agent = await Agent.find_one(Agent.id == agent_id)
        if not agent:
            self.logger.warning(
                'event=agent-not-found message="Agent with ID %s not found"',
                agent_id,
            )
            return None

        # Get the current runbook for the agent
        current_runbook = await RunBook.find_one(
            RunBook.name == agent.run_book.name,
            RunBook.version == agent.run_book.version,
        )

        if not current_runbook:
            self.logger.error(
                'event=export-agent-failed message="Current runbook not found for agent" '
                "agent_id=%s runbook_name=%s runbook_version=%s",
                agent_id,
                agent.run_book.name,
                agent.run_book.version,
            )
            return None

        all_runbooks = await RunBook.find_many(RunBook.name == agent.run_book.name).sort((RunBook.last_updated, -1)).to_list()

        agent_dict = agent.model_dump()
        agent_dict["run_book"] = {
            "name": current_runbook.name,
            "version": current_runbook.version,
            "prompt": current_runbook.prompt,
            "created_at": current_runbook.created_at,
        }

        self.logger.info(
            'event=export-agent-success message="Exported agent with %d runbooks" agent_id=%s runbook_name=%s',
            len(all_runbooks),
            agent_id,
            agent.run_book.name,
        )

        return AgentExport(
            metadata=MetadataExport(),
            agent=agent_dict,
            runbooks=[runbook.model_dump() for runbook in all_runbooks],
        )

    async def import_agent(
        self,
        agent_name: str,
        file: UploadFile,
    ) -> dict | None:
        content = await file.read()
        data = orjson.loads(content.decode("utf-8"))

        agent_data = data["agent"]
        if agent_data is None:
            return None
        exported_runbooks = data.get("runbooks", [])

        # Generate new agent ID
        new_agent_id = f"agt-{uuid4()!s}"

        # Import all runbooks first with the new agent ID as the runbook name
        if exported_runbooks:
            for runbook_data in exported_runbooks:
                existing_runbook = await RunBook.find_one(
                    RunBook.name == new_agent_id,
                    RunBook.version == runbook_data["version"],
                )

                if not existing_runbook:
                    runbook = RunBook(
                        name=new_agent_id,
                        prompt=runbook_data["prompt"],
                        version=runbook_data["version"],
                        type=runbook_data.get("type", "text"),
                        labels=runbook_data.get("labels", []),
                        tags=runbook_data.get("tags", []),
                        created_at=runbook_data.get("created_at", datetime.now(TIMEZONE)),
                        last_updated=runbook_data.get("last_updated", datetime.now(TIMEZONE)),
                    )
                    await runbook.insert()

                    self.logger.info(
                        'event=import-runbook-success message="Imported runbook" name=%s version=%s',
                        new_agent_id,
                        runbook_data["version"],
                    )
                else:
                    self.logger.info(
                        'event=import-runbook-skip message="Runbook already exists" name=%s version=%s',
                        new_agent_id,
                        runbook_data["version"],
                    )

        # Get the original runbook version from the agent data
        original_runbook = agent_data.get("run_book", {})
        runbook_version = original_runbook.get("version", "1")

        agent_input = AgentInput(
            name=agent_name,
            description=agent_data.get("description", ""),
            dt_id=agent_data.get("dt_id"),
            type=agent_data.get("type", AgentType.WORKER),
            run_book=AgentRunbookInput(
                prompt=original_runbook.get("prompt", ""),
                version=runbook_version,  # Use the original runbook version as default
                created_at=datetime.now(TIMEZONE),
            ),
            action_packages=agent_data.get("action_packages", []),
            model=agent_data.get("model", {}),
        )

        agent_update_data = agent_input.model_dump(exclude_unset=True)
        agent_update_data.pop("run_book")
        new_agent = Agent(
            _id=new_agent_id,
            **agent_update_data,
            run_book=AgentRunbook(
                name=new_agent_id,
                version=runbook_version,
            ),
            created_by=agent_data.get("created_by", "admin"),
            created_at=agent_input.run_book.created_at,
        )
        await new_agent.insert()

        self.logger.info(
            'event=import-agent-success message="Imported agent with %d runbooks" '
            "agent_name=%s agent_id=%s agent_type=%s runbook_version=%s",
            len(exported_runbooks),
            agent_data["name"],
            new_agent_id,
            agent_input.type.value,
            runbook_version,
        )

        return {
            "agent_id": new_agent_id,
            "agent_type": agent_input.type,
        }

    async def set_agent_template(
        self,
        agent_id: str,
        is_template: bool,
    ) -> bool:
        """
        Set the is_template field of an agent.
        """
        agent_db = await Agent.get(agent_id)
        if not agent_db:
            self.logger.error(
                'event=set-agent-template-failed message="Agent not found" agent_id=%s',
                agent_id,
            )
            return False

        agent_db.is_template = is_template
        await agent_db.save()
        self.logger.info(
            'event=set-agent-template-success message="Set agent template status successfully" agent_id=%s is_template=%s',
            agent_id,
            is_template,
        )
        return True
