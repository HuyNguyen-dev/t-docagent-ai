from pydantic import BaseModel, Field


class DocumentFields(BaseModel):
    fields: dict[str, str] = Field(default_factory=dict)


class DocumentTable(BaseModel):
    table_id: str = Field(default="")
    columns: list[dict[str, str]] = Field(default_factory=list)


class FieldExtractionData(BaseModel):
    fields: dict[str, str] = Field(default_factory=dict)


class TableExtractionData(BaseModel):
    tables: list[DocumentTable] = Field(default_factory=list)


class GenExtractionData(BaseModel):
    fields: dict[str, str] = Field(default_factory=dict)
    tables: list[DocumentTable] = Field(default_factory=list)


class FieldExtractionMetrics(BaseModel):
    total_fields: int = Field(default=0)
    extracted_fields: int = Field(default=0)
    missing_fields: int = Field(default=0)
    success_fields: int = Field(default=0)
    accuracy: float = Field(default=0.0)
    errors: dict[str, list[str]] = Field(default_factory=dict)


class TableMetrics(BaseModel):
    total_tables: int = Field(default=0)
    extracted_tables: int = Field(default=0)
    total_extracted_rows: int = Field(default=0)
    success_extracted_rows: int = Field(default=0)
    failed_extracted_rows: int = Field(default=0)
    structure_accuracy: float = Field(default=0.0)
    table_extract_completeness: float = Field(default=0.0)
    errors: dict[str, list[str]] = Field(default_factory=dict)


class ValidationMetrics(BaseModel):
    total_validations: int = Field(default=0)
    passed_validations: int = Field(default=0)
    failed_validations: int = Field(default=0)


class ResultMetrics(BaseModel):
    success_rate: float = Field(default=0.0)
    total_items: int = Field(default=0)
    success_items: int = Field(default=0)
    failed_items: int = Field(default=0)
    processing_time: float = Field(default=0.0)
    quality_pipeline_score: float = Field(default=0.0)


class PerformanceMetrics(BaseModel):
    mapping_accuracy: float = Field(default=0.0)
    consistency_accuracy: float = Field(default=0.0)
    validation_score: float = Field(default=0.0)
    error_rate: float = Field(default=0.0)
    field_metrics: FieldExtractionMetrics = Field(default_factory=FieldExtractionMetrics)
    table_metrics: TableMetrics = Field(default_factory=TableMetrics)
    validation_metrics: ValidationMetrics = Field(default_factory=ValidationMetrics)
    result_metrics: ResultMetrics = Field(default_factory=ResultMetrics)
