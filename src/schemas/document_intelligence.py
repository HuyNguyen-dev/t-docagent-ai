from typing import Annotated

from pydantic import BaseModel, Field, field_validator
from pydantic.types import StringConstraints

from schemas.document_format import DocumentFormatFieldDisplay, DocumentFormatTableDisplay

HexCodeStr = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^#(?:[0-9a-fA-F]{3}){1,2}$")]
NameStr = Annotated[str, StringConstraints(min_length=1, max_length=100)]


class TableSchema(BaseModel):
    table_name: str
    columns: list[str] = Field(default_factory=list)

    @field_validator("columns")
    @classmethod
    def check_unique_columns(cls, v: list[str]) -> list[str]:
        if len(v) != len(set(v)):
            msg = "Duplicate column names are not allowed."
            raise ValueError(msg)
        return v


class DocumentGenSchema(BaseModel):
    fields: list[str] = Field(default_factory=list)
    tables: list[TableSchema] = Field(default_factory=list)

    @field_validator("fields")
    @classmethod
    def check_unique_fields(cls, v: list[str]) -> list[str]:
        if len(v) != len(set(v)):
            msg = "Duplicate field names are not allowed."
            raise ValueError(msg)
        return v


class BaseAnnotationConfig(BaseModel):
    color_name: NameStr
    hex_code: HexCodeStr


class FieldAnnotationConfig(BaseAnnotationConfig):
    pass


class TableAnnotationConfig(BaseAnnotationConfig):
    table_name: NameStr


class AnnotationConfig(BaseModel):
    field: FieldAnnotationConfig
    tables: list[TableAnnotationConfig] = Field(default_factory=list)


class DocumentFormatGenSchema(BaseModel):
    fields: list[DocumentFormatFieldDisplay] = Field(default_factory=list)
    tables: list[DocumentFormatTableDisplay] = Field(default_factory=list)
