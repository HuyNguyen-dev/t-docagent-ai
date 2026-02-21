from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import AnyHttpUrl, BaseModel, Field

from utils.constants import TIMEZONE
from utils.enums import MCPTransport


class StreamableHTTPAdvancedConfigs(BaseModel):
    url: AnyHttpUrl
    headers: dict[str, str] = Field(default_factory=dict)
    timeout: float = 10.0
    sse_read_timeout: float = 30.0


class StdioAdvanceConfigs(BaseModel):
    command: Literal["python", "docker"]
    file_uri: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    encoding: str = "utf-8"


class ActionPackageInDB(BaseModel):
    id: str = Field(
        default_factory=lambda: f"ap-{uuid4()!s}",
        alias="_id",
        alias_priority=2,
    )
    name: str
    description: str = ""
    version: str = "0.0.1"
    transport: MCPTransport = MCPTransport.STREAMABLE_HTTP
    advanced_configs: StreamableHTTPAdvancedConfigs | StdioAdvanceConfigs | dict = Field(default_factory=dict)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(TIMEZONE),
        description="Timestamp at the time of object creation",
    )
    last_updated: datetime = Field(
        default_factory=lambda: datetime.now(TIMEZONE),
        description="Timestamp at the time of object last updated",
    )


class ActionPackageInput(BaseModel):
    name: str = Field(max_length=100)
    description: str = Field(max_length=500, default="")
    transport: MCPTransport = MCPTransport.STREAMABLE_HTTP
    version: str = "0.0.1"
    advanced_configs: StreamableHTTPAdvancedConfigs | StdioAdvanceConfigs | dict = Field(default_factory=dict)


class ActionPackageUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    transport: MCPTransport = MCPTransport.STREAMABLE_HTTP
    version: str | None = None
    advanced_configs: StreamableHTTPAdvancedConfigs | StdioAdvanceConfigs | dict = Field(default_factory=dict)


class ActionPackageSummary(BaseModel):
    id: str
    name: str
    description: str
    version: str


class ActionPackageDetail(BaseModel):
    id: str
    name: str
    description: str
    version: str
    transport: MCPTransport = MCPTransport.STREAMABLE_HTTP
    status: bool = False
    tools: list[Any] = []
    total_tools: int = 0


class ActionPackageIDs(BaseModel):
    ap_ids: list[str]
