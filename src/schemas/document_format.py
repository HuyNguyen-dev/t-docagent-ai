from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from schemas.document_type import BaseProperty
from utils.common import convert_name_to_id
from utils.constants import TIMEZONE
from utils.enums import DocumentFormatState


# Mapping Format
class BaseMappingProperty(BaseProperty):
    mapped_to: str

    @model_validator(mode="after")
    def generate_id_from_display_name(self) -> "BaseMappingProperty":
        self.id = convert_name_to_id(self.display_name)
        return self


class BaseMappingPropertyDisplay(BaseModel):
    mapped_to: str
    display_name: str


class BaseDocumentFormatField(BaseModel):
    static_value: str = ""
    additional_prompt: str = ""


class DocumentFormatField(BaseMappingProperty, BaseDocumentFormatField):
    pass


class DocumentFormatFieldDisplay(BaseMappingPropertyDisplay, BaseDocumentFormatField):
    pass


class BaseDocumentFormatTable(BaseModel):
    id: str


class DocumentFormatTable(BaseDocumentFormatTable):
    columns: list[BaseMappingProperty] = Field(default_factory=list)


class DocumentFormatTableDisplay(BaseDocumentFormatTable):
    columns: list[BaseMappingPropertyDisplay] = Field(default_factory=list)


class DocumentFormatInDB(BaseModel):
    id: str = Field(
        default_factory=lambda: f"df-{uuid4()!s}",
        alias="_id",
        alias_priority=2,
    )
    name: str = Field(max_length=100)
    dt_id: str
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
    state: DocumentFormatState = DocumentFormatState.IN_TRAINING
    fields: list[DocumentFormatField] = Field(default_factory=list)
    tables: list[DocumentFormatTable] = Field(default_factory=list)
    extraction_prompt: str = ""
    sample_table_rows: str = ""


class BaseDocumentFormatUpdate(BaseModel):
    extraction_prompt: str
    sample_table_rows: str


class DocumentFormatUpdate(BaseDocumentFormatUpdate):
    fields: list[DocumentFormatField] = Field(default_factory=list)
    tables: list[DocumentFormatTable] = Field(default_factory=list)


class DocumentFormatUpdateDisplay(BaseDocumentFormatUpdate):
    fields: list[DocumentFormatFieldDisplay] = Field(default_factory=list)
    tables: list[DocumentFormatTableDisplay] = Field(default_factory=list)


class DocumentFormatQuery(BaseModel):
    id: str = Field(
        alias="_id",
        alias_priority=2,
    )
    name: str
    created_at: datetime
    last_updated: datetime
    state: DocumentFormatState


class DocumentFormatDeleteQuery(BaseModel):
    id: str = Field(
        alias="_id",
        alias_priority=2,
    )
    doc_uri: str


class DocumentFormatDasboardQuery(BaseModel):
    id: str = Field(
        alias="_id",
        alias_priority=2,
    )
    name: str


class DocumentFormatResponse(BaseModel):
    id: str
    name: str = ""
    dt_id: str = ""
    doc_uri: str = ""
    fields: list[DocumentFormatField] = Field(default_factory=list)
    tables: list[DocumentFormatTable] = Field(default_factory=list)
    extraction_prompt: str = ""
    sample_table_rows: str = ""


class DocumentFormatUpdateState(BaseModel):
    state: DocumentFormatState
    df_ids: list[str]
