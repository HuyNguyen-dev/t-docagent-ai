from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from utils.constants import TIMEZONE
from utils.enums import DocWorkItemStage, DocWorkItemState


class DocumentWorkItemInDB(BaseModel):
    id: str = Field(
        default_factory=lambda: f"dwi-{uuid4()!s}",
        alias="_id",
        alias_priority=2,
    )
    df_id: str
    doc_uri: str
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(TIMEZONE),
        description="Timestamp at the time of object creation",
    )
    last_run: datetime = Field(
        default_factory=lambda: datetime.now(TIMEZONE),
        description="Timestamp at the time of object creation",
    )
    stage: DocWorkItemStage = DocWorkItemStage.TRAINING
    state: DocWorkItemState = DocWorkItemState.COMPLETED
    is_workflow: bool = False


class DocumentWorkItemDeleteQuery(BaseModel):
    id: str = Field(
        alias="_id",
        alias_priority=2,
    )
    doc_uri: str


class DetailedDocumentWorkItem(BaseModel):
    # --- Top Section from UI ---
    name: str
    format_name: str
    format_state: str
    last_run: datetime
    first_added: datetime
    doc_uri: str
    dt_id: str

    # --- Document Type Fields Section ---
    model_config = ConfigDict(extra="allow")
