import asyncio
import os
from datetime import datetime
from pathlib import Path
from typing import Literal

import httpx
from beanie.odm.enums import SortDirection
from fastapi import UploadFile
from langchain_mcp_adapters.client import MultiServerMCPClient

from config import settings
from handlers.document import DocumentHandler
from models.action_package import ActionPackage
from models.agent import Agent
from schemas.action_package import (
    ActionPackageDetail,
    ActionPackageInput,
    ActionPackageUpdate,
)
from schemas.response import Page, PaginatedMetadata
from utils.constants import DEFAULT_MCP_SCRIPT_FILE_FOLDER, DEFAULT_STANDARDIO_MCP_FOLDER, TIMEZONE
from utils.enums import MCPTransport
from utils.logger.custom_logging import LoggerMixin

document_handler = DocumentHandler()


class ActionPackageHandler(LoggerMixin):
    @staticmethod
    async def check_file_script(
        ap: ActionPackage,
        mode: Literal["download", "delete"],
    ) -> str | None:
        if not isinstance(ap.advanced_configs, dict):
            ap.advanced_configs = ap.advanced_configs.model_dump()

        package_folder = ap.name.replace(" ", "_")
        file_uri = ap.advanced_configs["file_uri"]
        if file_uri is None:
            return None
        file_name = Path(file_uri).name
        dest_folder = Path(os.environ["SRC_DIR"]) / DEFAULT_STANDARDIO_MCP_FOLDER / package_folder
        dest_path = Path(dest_folder) / file_name
        if mode == "download":
            dest_folder.mkdir(parents=True, exist_ok=True)
            if not dest_path.exists():
                bytes_file = await document_handler.download_document(object_path=file_uri)
                if bytes_file is None:
                    return None
                dest_path.write_bytes(bytes_file.getvalue())
        else:
            if dest_path.exists():
                dest_path.unlink()
                if not dest_folder.is_dir():
                    dest_folder.rmdir()
            is_deleted = await document_handler.delete_document(
                object_path=ap.advanced_configs["file_uri"],
            )
            if not is_deleted:
                return None
        return str(dest_path)

    async def get_connection_details(self, ap: ActionPackage) -> ActionPackageDetail:
        """
        Connects to a single action package and fetches its details.
        Returns an ActionPackageDetail object with status and tool info.
        """
        try:
            if not isinstance(ap.advanced_configs, dict):
                ap.advanced_configs = ap.advanced_configs.model_dump()

            if ap.transport == MCPTransport.STREAMABLE_HTTP:
                async with httpx.AsyncClient() as http_client:
                    response = await http_client.head(
                        url=str(ap.advanced_configs["url"]),
                        headers=ap.advanced_configs["headers"],
                        timeout=5.0,
                    )
                    content_type = response.headers.get("content-type", None)
                    if content_type not in ["application/json", "application/x-ndjson", None]:
                        error_message = f"Unexpected content type: {content_type}"
                        raise TypeError(error_message)

                server_configs = {
                    ap.id: {
                        "url": str(ap.advanced_configs["url"]),
                        "transport": ap.transport.value,
                        "headers": ap.advanced_configs["headers"],
                    },
                }
            else:
                script_path = await self.check_file_script(
                    ap=ap,
                    mode="download",
                )
                args: list[str] = ap.advanced_configs.get("args", [])
                if script_path is not None:
                    args.append(script_path)

                if ap.advanced_configs["command"] == "docker" and ap.advanced_configs.get("env"):
                    env_vars = ap.advanced_configs["env"]
                    if isinstance(env_vars, dict):
                        env_args = []
                        for key, value in env_vars.items():
                            env_args.extend(["-e", f"{key}={value}"])
                        # Insert env args before the last item (image name)
                        if len(args) > 0:
                            args[-1:-1] = env_args
                        else:
                            args.extend(env_args)

                server_configs = {
                    ap.id: {
                        "command": str(ap.advanced_configs["command"]),
                        "transport": ap.transport.value,
                        "args": args,
                        "env": ap.advanced_configs["env"],
                        "encoding": ap.advanced_configs["encoding"],
                    },
                }
            mcp_client = MultiServerMCPClient(server_configs)
            raw_tools = await mcp_client.get_tools()
            is_in_set = set()
            tools = []
            for tool in raw_tools:
                if tool.name not in is_in_set:
                    tools.append({"name": tool.name, "description": tool.description})
                    is_in_set.add(tool.name)
            return ActionPackageDetail(
                id=ap.id,
                name=ap.name,
                description=ap.description,
                version=ap.version,
                transport=ap.transport,
                status=True,
                tools=tools,
                total_tools=len(tools),
            )
        except httpx.ConnectError:
            self.logger.exception(
                "event=mcp-client-connect-error message=Failed to connect to MCP server ap_id=%s",
                getattr(ap, "id", None),
            )
        except Exception:
            self.logger.exception(
                "event=mcp-client-error message=Error occurred while connecting to MCP server ap_id=%s",
                getattr(ap, "id", None),
            )
        return ActionPackageDetail(
            id=ap.id,
            name=ap.name,
            description=ap.description,
            version=ap.version,
            transport=ap.transport,
        )

    async def create_action_package(
        self,
        action_package_input: ActionPackageInput,
        file_script: UploadFile | None = None,
    ) -> ActionPackageDetail | None:
        self.logger.info("event=starting-creating-new-action-package")
        if not isinstance(action_package_input.advanced_configs, dict):
            action_package_input.advanced_configs = action_package_input.advanced_configs.model_dump()

        if (
            action_package_input.transport == MCPTransport.STDIO
            and file_script is None
            and action_package_input.advanced_configs["command"] == "python"
        ):
            self.logger.error(
                'event=create-new-action-package-failed message="Missing script file with type transport Stdio"',
            )
            return None
        if action_package_input.transport == MCPTransport.STDIO and file_script is not None:
            if action_package_input.advanced_configs["command"] == "docker":
                self.logger.error(
                    "event=create-new-action-package-failed "
                    'message="Script file with Stdio transport is not needed when using Docker commands"',
                )
                return None
            object_path = await document_handler.upload_document(
                file=file_script,
                document_type_name=DEFAULT_MCP_SCRIPT_FILE_FOLDER,
                document_format_name=action_package_input.name,
            )
            if object_path is None:
                return None
            action_package_input.advanced_configs["file_uri"] = object_path
        action_package = ActionPackage(**action_package_input.model_dump())
        await action_package.create()
        return await self.get_connection_details(action_package)

    async def update_action_package(
        self,
        ap_id: str,
        action_package_update: ActionPackageUpdate,
        file_script: UploadFile | None = None,
    ) -> ActionPackageDetail | None:
        self.logger.info("event=starting-updating-action-package ap_id=%s", ap_id)
        action_package = await ActionPackage.get(ap_id)
        if not action_package:
            self.logger.warning("event=action-package-not-found ap_id=%s", ap_id)
            return None
        if not isinstance(action_package.advanced_configs, dict):
            action_package.advanced_configs = action_package.advanced_configs.model_dump()

        if not isinstance(action_package_update.advanced_configs, dict):
            action_package_update.advanced_configs = action_package_update.advanced_configs.model_dump()

        if (
            action_package_update.transport == MCPTransport.STDIO
            and file_script is None
            and action_package_update.advanced_configs["command"] == "python"
        ):
            self.logger.error(
                'event=update-action-package-failed message="Missing script file with type transport Stdio"',
            )
            return None

        if action_package_update.transport == MCPTransport.STDIO and file_script is not None:
            if action_package_update.advanced_configs["command"] == "docker":
                self.logger.error(
                    "event=update-action-package-failed "
                    'message="Script file with Stdio transport is not needed when using Docker commands"',
                )
                return None
            await self.check_file_script(ap=action_package, mode="delete")
            object_path = await document_handler.upload_document(
                file=file_script,
                document_type_name=DEFAULT_MCP_SCRIPT_FILE_FOLDER,
                document_format_name=action_package_update.name,
            )
            if not isinstance(action_package_update.advanced_configs, dict):
                action_package_update.advanced_configs = action_package_update.advanced_configs.model_dump()

            action_package_update.advanced_configs["file_uri"] = object_path
        update_data = action_package_update.model_dump(exclude_unset=True)
        if update_data:
            update_data["last_updated"] = datetime.now(TIMEZONE)
            if "advanced_configs" in update_data and isinstance(update_data["advanced_configs"], dict):
                updated_configs = {**action_package.advanced_configs, **update_data["advanced_configs"]}
                update_data["advanced_configs"] = updated_configs
            await action_package.set(update_data)
        return await self.get_connection_details(action_package)

    async def delete_action_package_by_id(
        self,
        ap_id: str,
    ) -> bool:
        self.logger.info("event=starting-deleting-action-package ap_id=%s", ap_id)
        action_package = await ActionPackage.get(ap_id)
        if action_package:
            filter_query = {"action_packages.id": ap_id}
            update_operation = {"$pull": {"action_packages": {"id": ap_id}}}
            result = await Agent.find_many(filter_query).update(update_operation)
            self.logger.debug(
                'event=delete-action-package-by-id message="Matched %s agents, modified %s agents"',
                result.matched_count,
                result.modified_count,
            )
            if not isinstance(action_package.advanced_configs, dict):
                action_package.advanced_configs = action_package.advanced_configs.model_dump()

            if action_package.transport == MCPTransport.STDIO and action_package.advanced_configs["command"] == "python":
                await self.check_file_script(ap=action_package, mode="delete")
            await action_package.delete()
            return True
        self.logger.warning("event=action-package-not-found ap_id=%s", ap_id)
        return False

    async def get_all_action_packages(
        self,
        q: str,
        page: int,
        page_size: int,
        filter_no_tools: bool = False,
    ) -> Page | None:
        self.logger.info("event=starting-retrieving-all-action-packages-with-details")
        search_criteria = {}
        if q:
            search_criteria = {"name": {"$regex": q, "$options": "i"}}
        if not filter_no_tools:
            total_records = await ActionPackage.find(search_criteria).count()
            action_packages = (
                await ActionPackage.find(search_criteria)
                .sort((ActionPackage.last_updated, SortDirection.DESCENDING))
                .skip((page - 1) * page_size)
                .limit(page_size)
                .to_list()
            )
            detailed_results = []
            async with asyncio.TaskGroup() as tg:
                tasks = [tg.create_task(self.get_connection_details(ap)) for ap in action_packages]

            detailed_results = [task.result() for task in tasks]

            self.logger.info(
                "event=get-connection-details-success count=%d",
                len(detailed_results),
            )
            total_pages = (total_records + page_size - 1) // page_size or 1
        else:
            action_packages = (
                await ActionPackage.find(search_criteria).sort((ActionPackage.last_updated, SortDirection.DESCENDING)).to_list()
            )
            async with asyncio.TaskGroup() as tg:
                tasks = [tg.create_task(self.get_connection_details(ap)) for ap in action_packages]

            detailed_results = [task.result() for task in tasks]

            self.logger.info(
                "event=get-connection-details-success count=%d",
                len(detailed_results),
            )
            filtered_aps = [action for action in detailed_results if action.total_tools != 0]
            total_records = len(filtered_aps)
            start_index = (page - 1) * page_size
            end_index = (page - 1) * page_size + page_size
            total_pages = (total_records + page_size - 1) // page_size or 1
            detailed_results = filtered_aps[start_index:end_index]

        return Page(
            items=detailed_results,
            metadata=PaginatedMetadata(
                page=min(page, total_pages),
                page_size=page_size,
                total_items=total_records,
                total_pages=total_pages,
            ),
        )

    async def refresh_list_action_package(
        self,
        ap_ids: list[str],
    ) -> list[ActionPackageDetail]:
        self.logger.info("event=starting-refresh-list-action-package ap_ids=%s", ap_ids)
        results = []
        async with asyncio.TaskGroup() as tg:
            tasks = [tg.create_task(self.refresh_connection(ap_id)) for ap_id in ap_ids]
        for task in tasks:
            result = task.result()
            if result:
                results.append(result)
        self.logger.info("event=refresh-list-action-package-successful count=%s", len(results))
        return results

    async def refresh_connection(self, ap_id: str) -> ActionPackageDetail | None:
        self.logger.info("event=starting-refresh-connection ap_id=%s", ap_id)
        action_package = await ActionPackage.get(ap_id)
        if not action_package:
            self.logger.warning("event=action-package-not-found ap_id=%s", ap_id)
            return None

        details = await self.get_connection_details(action_package)

        if details.status:
            self.logger.info("event=refresh-connection-successful ap_id=%s", ap_id)

        return details

    async def get_action_package_by_id(
        self,
        ap_id: str,
    ) -> ActionPackage | None:
        self.logger.info("event=starting-retrieving-action-package ap_id=%s", ap_id)
        action_package = await ActionPackage.get(ap_id)
        if not action_package:
            self.logger.warning("event=action-package-not-found ap_id=%s", ap_id)
            return None

        if not isinstance(action_package.advanced_configs, dict):
            action_package.advanced_configs = action_package.advanced_configs.model_dump()

        if action_package.transport == MCPTransport.STDIO and action_package.advanced_configs["command"] == "python":
            presigned_url = await document_handler.create_presigned_urls(
                object_names=[action_package.advanced_configs["file_uri"]],
                expiration=settings.PRESIGN_URL_EXPIRATION,
                inline=True,
            )
            action_package.advanced_configs["file_uri"] = next(iter(presigned_url.values()))

        return action_package
