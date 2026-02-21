from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from utils.common import convert_name_to_id
from utils.constants import INVALID_DISPLAY_NAME_MSG, TIMEZONE
from utils.enums import DocWorkItemStage, DocWorkItemState


class BaseProperty(BaseModel):
    id: str = Field(init=False, default="")
    display_name: str

    @field_validator("display_name")
    @classmethod
    def display_name_must_be_valid(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError(INVALID_DISPLAY_NAME_MSG)
        return v

    @model_validator(mode="after")
    def generate_id_from_display_name(self) -> "BaseProperty":
        self.id = convert_name_to_id(self.display_name)
        return self


class BasePropertyDisplay(BaseModel):
    display_name: str


class DocumentTypeFields(BaseModel):
    properties: list[BaseProperty] = Field(description="All fields", default_factory=list)
    required: list[str] = Field(description="All fields required", default_factory=list)

    @model_validator(mode="after")
    def generate_ids_from_required_properties(self) -> "DocumentTypeFields":
        self.required = [convert_name_to_id(prop) for prop in self.required]
        return self


class DocumentTypeFieldsDisplay(BaseModel):
    properties: list[BasePropertyDisplay] = Field(description="All fields", default_factory=list)
    required: list[str] = Field(description="All fields required", default_factory=list)


class DocumentTypeTable(BaseModel):
    id: str = Field(init=False, default="")
    display_name: str
    description: str
    columns: DocumentTypeFields = Field(default_factory=DocumentTypeFields)

    @field_validator("display_name")
    @classmethod
    def display_name_must_be_valid(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError(INVALID_DISPLAY_NAME_MSG)
        return v

    @model_validator(mode="after")
    def generate_table_id_from_display_name(self) -> "DocumentTypeTable":
        self.id = convert_name_to_id(self.display_name)
        return self


class DocumentTypeTableDisplay(BaseModel):
    display_name: str
    description: str = ""
    columns: DocumentTypeFieldsDisplay = Field(default_factory=DocumentTypeFieldsDisplay)


class BaseDocumentTypeUpdate(BaseModel):
    agent_validation: bool = False
    auto_mapping: bool = False


class DocumentTypeUpdate(BaseDocumentTypeUpdate):
    fields: DocumentTypeFields = Field(default_factory=DocumentTypeFields)
    tables: list[DocumentTypeTable] = Field(default_factory=list)


class DocumentTypeUpdateDisplay(BaseDocumentTypeUpdate):
    fields: DocumentTypeFieldsDisplay = Field(default_factory=DocumentTypeFieldsDisplay)
    tables: list[DocumentTypeTableDisplay] = Field(default_factory=list)


class DocumentTypeInDB(BaseModel):
    id: str = Field(
        default_factory=lambda: f"dt-{uuid4()!s}",
        alias="_id",
        alias_priority=2,
    )
    name: str = Field(max_length=100)
    doc_uri: str
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(TIMEZONE),
        description="Timestamp at the time of object creation",
    )
    created_by: str = "Admin"
    last_updated: datetime = Field(
        default_factory=lambda: datetime.now(TIMEZONE),
        description="Timestamp at the time of object last update",
    )
    agent_validation: bool = False
    auto_mapping: bool = False
    fields: DocumentTypeFields = Field(default_factory=DocumentTypeFields)
    tables: list[DocumentTypeTable] = Field(default_factory=list)


class DocumentTypeName(BaseModel):
    id: str = Field(
        alias="_id",
        alias_priority=2,
    )
    name: str


class DocumentTypeResponse(BaseModel):
    id: str
    name: str = ""
    doc_uri: str = ""
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(TIMEZONE),
        description="Timestamp at the time of object creation",
    )
    agent_validation: bool = False
    auto_mapping: bool = False
    fields: DocumentTypeFields = Field(default_factory=DocumentTypeFields)
    tables: list[DocumentTypeTable] = Field(default_factory=list)
    is_activate: bool = False


class DocumentTypeDashboardItem(BaseModel):
    dt_id: str = Field(..., alias="_id")
    dt_name: str
    total: int
    total_failed: int
    total_need_training: int


class DocumentTypeDashboardWorkItem(BaseModel):
    id: str = Field(
        alias="_id",
        alias_priority=2,
    )
    doc_name: str
    df_name: str
    stage: DocWorkItemStage = DocWorkItemStage.TRAINING
    state: DocWorkItemState = DocWorkItemState.IN_PROCESS
    created_at: datetime
    last_run: datetime

    model_config = ConfigDict(extra="allow")


class DocumentTypeDFTrainingItem(BaseModel):
    id: str = Field(
        alias="_id",
        alias_priority=2,
    )
    doc_name: str
    df_id: str
    df_name: str
    training_status: str
    stage: DocWorkItemStage = DocWorkItemStage.TRAINING
    state: DocWorkItemState = DocWorkItemState.IN_PROCESS
    created_at: datetime
    last_run: datetime
