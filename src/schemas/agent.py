from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, Field, SecretStr

from utils.constants import TIMEZONE
from utils.enums import AgentArchitecture, AgentReasoning, AgentType, LLMProvider, UserRole


class AgentLLMModel(BaseModel):
    provider: LLMProvider
    name: str = ""
    api_key: SecretStr = Field(default=SecretStr(""))
    deployment_name: str = ""
    base_url: str = ""
    api_version: str = "2025-04-01-preview"


class AgentLLMModelResponse(BaseModel):
    provider: LLMProvider
    name: str = ""
    api_key: str = ""
    deployment_name: str = ""
    base_url: str = ""
    api_version: str = "2025-04-01-preview"


class AgentRunbook(BaseModel):
    name: str
    version: str = "1"


class AgentRunbookInput(BaseModel):
    prompt: str
    version: str = "1"
    created_at: datetime


class AgentActionPackage(BaseModel):
    id: str
    version: str = "0.0.1"
    action_selected: list[str] = Field(default_factory=list)


class AdvancedOptions(BaseModel):
    reasoning: AgentReasoning = AgentReasoning.DISABLED
    architecture: AgentArchitecture = AgentArchitecture.REACT
    kb_names: list[str] = Field(default_factory=list)


class AgentInput(BaseModel):
    name: str = Field(max_length=100)
    description: str = Field(max_length=500, default="")
    dt_id: str | None = None
    type: AgentType = AgentType.WORKER
    run_book: AgentRunbookInput = Field(default_factory=AgentRunbookInput)
    action_packages: list[AgentActionPackage] = Field(default_factory=list)
    model: AgentLLMModel
    advanced_options: AdvancedOptions = Field(default_factory=AdvancedOptions)


class AgentUpdate(BaseModel):
    name: str = Field(max_length=100)
    description: str = Field(max_length=500, default="")
    dt_id: str | None = None
    type: AgentType = AgentType.WORKER
    action_packages: list[AgentActionPackage] = Field(default_factory=list)
    model: AgentLLMModel
    advanced_options: AdvancedOptions = Field(default_factory=AdvancedOptions)


class AgentInDB(BaseModel):
    id: str = Field(
        default_factory=lambda: f"agt-{uuid4()!s}",
        alias="_id",
        alias_priority=2,
    )
    name: str = Field(max_length=100)
    description: str = Field(max_length=500, default="")
    dt_id: str = ""
    version: str = "0.0.1"
    type: AgentType = AgentType.WORKER
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(TIMEZONE),
        description="Timestamp at the time of object creation",
    )
    created_by: str
    is_template: bool = False
    run_book: AgentRunbook = Field(default_factory=AgentRunbook)
    action_packages: list[AgentActionPackage] = Field(default_factory=list)
    model: AgentLLMModel = Field(default_factory=AgentLLMModel)
    permissions: list[UserRole] = Field(default_factory=list)
    advanced_options: AdvancedOptions = Field(default_factory=AdvancedOptions)


class AgentResponse(BaseModel):
    id: str
    name: str = Field(max_length=100)
    description: str = Field(max_length=500, default="")
    dt_id: str = ""
    version: str = "0.0.1"
    type: AgentType = AgentType.WORKER
    created_at: datetime
    created_by: str
    is_template: bool = False
    run_book: AgentRunbook = Field(default_factory=AgentRunbook)
    action_packages: list[AgentActionPackage] = Field(default_factory=list)
    model: AgentLLMModelResponse = Field(default_factory=AgentLLMModelResponse)
    permissions: list[UserRole] = Field(default_factory=list)
    advanced_options: AdvancedOptions = Field(default_factory=AdvancedOptions)

    @classmethod
    def from_db_model(cls, agent_db: AgentInDB) -> "AgentResponse":
        model_response = AgentLLMModelResponse(
            **{
                **agent_db.model.model_dump(),
                "api_key": agent_db.model.api_key.get_secret_value(),
            },
        )
        return cls(
            **{
                **agent_db.model_dump(),
                "model": model_response,
            },
        )


class AgentDashBoardItemResponse(BaseModel):
    id: str
    name: str
    description: str
    version: str
    type: AgentType
    is_template: bool
    created_at: datetime
    n_action_packages: int


class AgentDefaultRunBook(BaseModel):
    name: str
    version: str


class AgentStreamRequest(BaseModel):
    """Request model for agent stream endpoint."""

    question: str
    assets: list[str] = Field(default_factory=list)
