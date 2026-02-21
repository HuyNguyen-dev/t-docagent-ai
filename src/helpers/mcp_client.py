from datetime import timedelta

import httpx
from langchain.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from handlers.action_package import ActionPackageHandler
from models.action_package import ActionPackage
from schemas.agent import AgentActionPackage
from utils.enums import MCPTransport
from utils.logger.custom_logging import LoggerMixin


class MCPClient(LoggerMixin):
    async def get_tools_from_agent_config(
        self,
        action_packages: list[AgentActionPackage],
    ) -> list[BaseTool]:
        list_tools: list[BaseTool] = []
        for ap in action_packages:
            action_package_db = await ActionPackage.get(ap.id)
            if action_package_db is None:
                continue
            ap_tools = await self.get_tools(ap=action_package_db, action_selected=ap.action_selected)
            list_tools.extend(ap_tools)
        return list_tools

    async def get_tools(
        self,
        ap: ActionPackage,
        action_selected: list[str] | None = None,
    ) -> list[BaseTool]:
        try:
            server_configs = None
            if not isinstance(ap.advanced_configs, dict):
                ap.advanced_configs = ap.advanced_configs.model_dump()

            if ap.transport == MCPTransport.STREAMABLE_HTTP:
                async with httpx.AsyncClient() as http_client:
                    response = await http_client.head(ap.advanced_configs["url"], timeout=5.0)
                    content_type = response.headers.get("content-type", None)
                    if content_type not in ["application/json", "application/x-ndjson", None]:
                        error_message = f"Unexpected content type: {content_type}"
                        raise TypeError(error_message)

                server_configs = {
                    ap.id: {
                        "url": ap.advanced_configs["url"],
                        "transport": ap.transport,
                        "headers": ap.advanced_configs.get("headers", {}),
                        "timeout": timedelta(seconds=ap.advanced_configs.get("timeout", 20)),
                        "sse_read_timeout": timedelta(seconds=ap.advanced_configs.get("sse_read_timeout", 30)),
                    },
                }
            elif ap.transport == MCPTransport.STDIO:
                script_path = await ActionPackageHandler.check_file_script(ap=ap, mode="download")
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
                        "command": ap.advanced_configs["command"],
                        "transport": ap.transport,
                        "args": args,
                        "env": ap.advanced_configs.get("env"),
                        "encoding": ap.advanced_configs.get("encoding", "utf-8"),
                    },
                }

            mcp_client = MultiServerMCPClient(server_configs)
            tools = await mcp_client.get_tools()
            if action_selected is None:
                return tools
            uniqe_tool = set()
            filtered_tools = []

            for tool in tools:
                name = tool.name
                if name in action_selected and name not in uniqe_tool:
                    filtered_tools.append(tool)
                    uniqe_tool.add(name)
        except httpx.ConnectError:
            self.logger.exception(
                "event=mcp-client-connect-error message=Failed to connect to MCP server ap_id=%s",
                getattr(ap, "id", None),
            )
            return []
        except Exception:
            self.logger.exception(
                "event=mcp-client-error message=Error while fetching tools from MCP",
            )
            return []
        return filtered_tools
