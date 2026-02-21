from datetime import datetime

from agents.training_agent.state import TrainingState
from schemas.training import (
    FieldExtractionMetrics,
    ResultMetrics,
    TableMetrics,
    ValidationMetrics,
)
from utils.constants import TIMEZONE
from utils.logger.custom_logging import LoggerMixin


class AnalyzeMetricsNode(LoggerMixin):
    """
    Node for analyzing various metrics related to extraction, mapping, and performance.
    """

    def _analyze_field_extraction(self, state: TrainingState) -> FieldExtractionMetrics:
        """
        Analyze field extraction metrics in detail.
        """
        try:
            errors: dict[str, list[str]] = {}
            extracted_fields = state.get("extracted_fields", {})
            document_format = state.get("document_format", {})
            expected_fields = getattr(document_format, "fields", []) if document_format else []

            field_metrics = FieldExtractionMetrics()
            field_metrics.total_fields = len(expected_fields)

            if extracted_fields:
                field_metrics.extracted_fields = len(extracted_fields)

                extracted_keys = list(extracted_fields.keys()) if isinstance(extracted_fields, dict) else []

                if expected_fields:
                    expected_field_ids = {getattr(f, "id", "") for f in expected_fields}
                    missing_fields = expected_field_ids - set(extracted_keys)
                    field_metrics.missing_fields = len(missing_fields)

                    if missing_fields:
                        error_msg = f"Missing expected fields: {', '.join(missing_fields)}"
                        errors.setdefault("field_validation", []).append(error_msg)
                        self.logger.warning(
                            "event=missing-fields "
                            "missing_count=%d missing_fields=%s "
                            'message="Missing expected fields during extraction"',
                            len(missing_fields),
                            ", ".join(missing_fields),
                        )
                else:
                    field_metrics.missing_fields = 0
            else:
                field_metrics.extracted_fields = 0
                field_metrics.missing_fields = field_metrics.total_fields

                if field_metrics.total_fields > 0:
                    error_msg = f"No fields extracted - expected {field_metrics.total_fields} fields"
                    errors.setdefault("field_validation", []).append(error_msg)
                    self.logger.warning(
                        'event=no-fields-extracted expected_fields=%d message="No fields were extracted from document"',
                        field_metrics.total_fields,
                    )

            field_metrics.success_fields = (
                field_metrics.extracted_fields - field_metrics.missing_fields if field_metrics.extracted_fields > 0 else 0
            )
            field_metrics.accuracy = (
                field_metrics.extracted_fields / field_metrics.total_fields if field_metrics.total_fields > 0 else 0.0
            )
            field_metrics.errors = errors

            if errors:
                total_errors = sum(len(error_list) for error_list in errors.values())
                self.logger.warning(
                    'event=field-validation-errors error_count=%d message="Field validation errors found during analysis"',
                    total_errors,
                )

            self.logger.info(
                "event=field-extraction-analysis "
                "total=%d extracted=%d missing=%d accuracy=%.2f "
                'message="Field extraction analysis completed"',
                field_metrics.total_fields,
                field_metrics.extracted_fields,
                field_metrics.missing_fields,
                field_metrics.accuracy,
            )

        except Exception:
            self.logger.exception(
                'event=field-extraction-analysis-error message="Error analyzing field extraction"',
            )
            return FieldExtractionMetrics()
        return field_metrics

    def _analyze_table_structure(self, state: TrainingState) -> TableMetrics:
        """
        Analyze table structure and completeness metrics.
        """
        try:
            errors: dict[str, list[str]] = {}
            extracted_tables = state.get("extracted_tables", []) or []
            document_format = state.get("document_format", {}) or {}
            document_type = state.get("document_type", {}) or {}
            expected_tables = getattr(document_format, "tables", []) if document_format else []
            required_columns = {
                getattr(table, "id", ""): table.columns.required for table in getattr(document_type, "tables", [])
            }

            table_metrics = TableMetrics()
            table_metrics.total_tables = len(expected_tables)

            extracted_map = {}
            for table in extracted_tables:
                if hasattr(table, "table_id"):
                    extracted_map[table.table_id] = table

            matched_tables = 0
            total_extracted_rows = 0
            success_extracted_rows = 0
            total_cells = 0
            filled_cells = 0

            for expected_table in expected_tables:
                table_id = getattr(expected_table, "id", "")
                if table_id not in extracted_map:
                    error_msg = f"Expected table '{table_id}' was not extracted"
                    errors.setdefault("table_validation", []).append(error_msg)
                    self.logger.warning(
                        'event=missing-table table_id=%s message="Expected table was not found in extracted data"',
                        table_id,
                    )
                    continue

                matched_tables += 1
                data = extracted_map[table_id]

                columns = getattr(data, "columns", [])
                if not isinstance(columns, list):
                    columns = []

                for row_index, row in enumerate(columns):
                    empty_cells = []
                    if isinstance(row, dict):
                        total_cells += len(row)
                        total_extracted_rows += 1

                        table_required_columns = required_columns.get(table_id, [])
                        for column_key, column_value in row.items():
                            if column_key in table_required_columns and (column_value is None or str(column_value).strip() == ""):
                                empty_cells.append(column_key)

                        if len(empty_cells) > 0:
                            error_msg = (
                                f"Table '{table_id}' row {row_index + 1} has {len(empty_cells)} "
                                f"empty required cells: {', '.join(empty_cells)}"
                            )
                            errors.setdefault("table_validation", []).append(error_msg)
                            self.logger.warning(
                                "event=empty-table-cells "
                                "table_id=%s row=%d empty_cells=%d total_cells=%d empty_columns=%s "
                                'message="Table row contains empty required cells"',
                                table_id,
                                row_index + 1,
                                len(empty_cells),
                                len(row),
                                ", ".join(empty_cells),
                            )

                        if len(empty_cells) == 0:
                            success_extracted_rows += 1

                        filled_count = len(row) - len(empty_cells)
                        filled_cells += filled_count

            table_metrics.extracted_tables = matched_tables
            table_metrics.total_extracted_rows = total_extracted_rows
            table_metrics.success_extracted_rows = success_extracted_rows
            table_metrics.failed_extracted_rows = total_extracted_rows - success_extracted_rows

            table_metrics.structure_accuracy = (
                (matched_tables / table_metrics.total_tables) if table_metrics.total_tables > 0 else 0.0
            )

            table_metrics.table_extract_completeness = (filled_cells / total_cells) if total_cells > 0 else 0.0

            table_metrics.errors = errors
            if errors:
                total_errors = sum(len(error_list) for error_list in errors.values())
                self.logger.warning(
                    'event=table-validation-errors error_count=%d message="Table validation errors found during analysis"',
                    total_errors,
                )

            self.logger.info(
                "event=table-structure-analysis "
                "total=%d extracted=%d structure_accuracy=%.2f table_extract_completeness=%.2f "
                'message="Table structure analysis completed"',
                table_metrics.total_tables,
                table_metrics.extracted_tables,
                table_metrics.structure_accuracy,
                table_metrics.table_extract_completeness,
            )

        except Exception:
            self.logger.exception(
                'event=table-structure-analysis-error message="Error analyzing table structure"',
            )
            return TableMetrics()

        return table_metrics

    def _analyze_validation_status(self, state: TrainingState) -> ValidationMetrics:
        """
        Analyze validation status in detail.
        """
        try:
            validation_metrics = ValidationMetrics()
            extracted_fields = state.get("extracted_fields", {}) or {}
            extracted_tables = state.get("extracted_tables", []) or []

            total_fields = len(extracted_fields) if extracted_fields else 0
            total_tables = len(extracted_tables)

            validation_metrics.total_validations = total_fields + total_tables
            validation_metrics.failed_validations = len(state["metrics"].field_metrics.errors) + len(
                state["metrics"].table_metrics.errors,
            )
            validation_metrics.passed_validations = (
                validation_metrics.total_validations - validation_metrics.failed_validations
                if validation_metrics.total_validations > 0
                else 0
            )

            self.logger.info(
                'event=validation-status-analysis total=%d passed=%d failed=%d message="Validation status analysis completed"',
                validation_metrics.total_validations,
                validation_metrics.passed_validations,
                validation_metrics.failed_validations,
            )

        except Exception:
            self.logger.exception(
                'event=validation-status-analysis-error message="Error analyzing validation status"',
            )
            return ValidationMetrics()
        return validation_metrics

    def _calculate_mapping_accuracy(self, state: TrainingState) -> float:
        """
        Calculate the accuracy of field and table mapping.
        Accuracy = (successful_mappings / total_mappings)
        Includes both document_format and document_type mappings.
        """
        try:
            extracted_fields = state.get("extracted_fields", {})
            extracted_tables = state.get("extracted_tables", [])
            document_format = state.get("document_format", {})
            document_type = state.get("document_type", {})

            if not document_format or not document_type:
                return 0.0

            # === Step 1: Expected Field IDs (from format and type) ===
            format_field_ids = set()
            if hasattr(document_format, "fields"):
                for field in document_format.fields:
                    if hasattr(field, "mapped_to") and field.mapped_to:
                        format_field_ids.add(field.mapped_to)

            type_field_ids = set()
            required_fields = state["document_type"].fields.required if state.get("document_type") else []
            if hasattr(document_type, "fields") and hasattr(document_type.fields, "properties"):
                for field in document_type.fields.properties:
                    if hasattr(field, "id") and field.id:
                        type_field_ids.add(field.id)

            expected_field_ids = format_field_ids.intersection(type_field_ids)

            # === Step 2: Extracted Field IDs ===
            extracted_field_ids = set()
            if extracted_fields and isinstance(extracted_fields, dict):
                extracted_field_ids.update(extracted_fields.keys())

            # Get mapped_to values for successfully extracted fields
            successfully_mapped_fields = set()
            if hasattr(document_format, "fields"):
                for field in document_format.fields:
                    if (
                        hasattr(field, "id")
                        and hasattr(field, "mapped_to")
                        and field.id in extracted_field_ids
                        and field.mapped_to
                    ):
                        successfully_mapped_fields.add(field.mapped_to)

            missing_required_fields = set(required_fields) - set(successfully_mapped_fields)
            if missing_required_fields:
                error_msg = f"Missing required filed {missing_required_fields}"
                state["metrics"].field_metrics.errors["field_validation"].append(error_msg)

            # === Step 3: Expected Table Cell IDs ===
            format_table_ids = {}
            if hasattr(document_format, "tables"):
                for table in document_format.tables:
                    table_id = getattr(table, "id", "")
                    if table_id and hasattr(table, "columns"):
                        format_table_ids[table_id] = {
                            getattr(col, "mapped_to", "")
                            for col in table.columns
                            if hasattr(col, "mapped_to") and getattr(col, "mapped_to", "")
                        }

            type_table_ids = {}
            required_columns = {}
            if hasattr(document_type, "tables"):
                for table in document_type.tables:
                    table_id = getattr(table, "id", "")
                    required_columns[table_id] = table.columns.required
                    if table_id and hasattr(table, "columns") and hasattr(table.columns, "properties"):
                        type_table_ids[table_id] = {
                            getattr(col, "id", "")
                            for col in table.columns.properties
                            if (hasattr(col, "id") and getattr(col, "id", ""))
                        }

            all_table_ids = set(format_table_ids.keys()).union(set(type_table_ids.keys()))
            expected_table_cell_ids = {
                table_id: format_table_ids.get(table_id, set()).intersection(type_table_ids.get(table_id, set()))
                for table_id in all_table_ids
            }

            # === Step 4: Extracted Table Cell IDs ===
            extracted_table_cell_ids = {}
            for table in extracted_tables:
                if hasattr(table, "table_id"):
                    table_id = table.table_id
                    columns = getattr(table, "columns", [])
                    keys = []
                    for row in columns:
                        if isinstance(row, dict):
                            for table in document_format.tables:
                                if table.id == table_id:
                                    keys.extend(col.mapped_to for col in table.columns if col.id in row)

                    extracted_table_cell_ids[table_id] = keys

                    missing_required_fields = set(required_columns.get(table_id, [])) - set(keys)
                    if missing_required_fields:
                        error_msg = f"Missing required filed {missing_required_fields}"
                        if "table_validation" in state["metrics"].field_metrics.errors:
                            state["metrics"].field_metrics.errors["table_validation"].append(error_msg)
                        else:
                            state["metrics"].field_metrics.errors["table_validation"] = [error_msg]

            # === Step 5: Calculate Matches ===
            successful_field_matches = len(expected_field_ids.intersection(successfully_mapped_fields))

            successful_table_matches = 0
            for table_id, expected_cells in expected_table_cell_ids.items():
                extracted_cells = extracted_table_cell_ids.get(table_id, set())
                successful_table_matches += len(expected_cells.intersection(extracted_cells))

            total_expected_fields = len(expected_field_ids)
            total_expected_table_cells = sum(len(cells) for cells in expected_table_cell_ids.values())

            total_mappings = total_expected_fields + total_expected_table_cells
            successful_mappings = successful_field_matches + successful_table_matches

            accuracy = (successful_mappings / total_mappings) if total_mappings > 0 else 0.0

            self.logger.info(
                "event=mapping-accuracy-calculated "
                "accuracy=%.2f total_mappings=%d successful_mappings=%d "
                'message="Mapping accuracy calculated"',
                accuracy,
                total_mappings,
                successful_mappings,
            )

        except Exception:
            self.logger.exception(
                'event=mapping-accuracy-error message="Error calculating mapping accuracy"',
            )
            return 0.0

        return accuracy

    def _calculate_consistency_accuracy(self, state: TrainingState) -> float:
        """
        Calculate consistency score based on field extraction and table completeness.
        """
        try:
            document_format = state.get("document_format", {})
            if not state.get("metrics"):
                return 0.0

            field_accuracy = state["metrics"].field_metrics.accuracy
            table_completeness = state["metrics"].table_metrics.table_extract_completeness
            if document_format.fields and not document_format.tables:
                return field_accuracy
            if not document_format.fields and document_format.tables:
                return table_completeness

            return field_accuracy * 0.5 + table_completeness * 0.5
        except Exception:
            self.logger.exception(
                'event=consistency-score-error message="Error calculating consistency score"',
            )
            return 0.0

    def _calculate_processing_time(self, state: TrainingState) -> float:
        """
        Calculate total processing time in seconds.
        """
        try:
            start_time = state.get("start_time")
            if start_time is None:
                return 0.0

            processing_time = datetime.now(TIMEZONE) - start_time
            processing_seconds = processing_time.total_seconds()

            self.logger.info(
                'event=processing-time-calculated message="Processing time calculated" time=%.2f seconds',
                processing_seconds,
            )
        except Exception:
            self.logger.exception(
                'event=processing-time-error message="Error calculating processing time"',
            )
            return 0.0
        return processing_seconds

    def _calculate_validation_score(self, state: TrainingState) -> float:
        """
        Calculate validation score based on validation errors.
        """
        try:
            if state["metrics"].validation_metrics.total_validations == 0:
                return 0.0

            score = state["metrics"].validation_metrics.passed_validations / state["metrics"].validation_metrics.total_validations
            score = max(0.0, min(1.0, score))

            self.logger.info(
                'event=validation-score-calculated score=%.2fmessage="Validation score calculated"',
                score,
            )

        except Exception:
            self.logger.exception(
                'event=validation-score-error message="Error calculating validation score"',
            )
            return 0.0
        return score

    async def _calculate_result_metrics(self, state: TrainingState) -> ResultMetrics:
        """
        Calculate metrics specific to the final results.
        """
        try:
            result_metrics = ResultMetrics()

            if state["metrics"].field_metrics.extracted_fields == 0:
                result_metrics.success_items = 0
            else:
                result_metrics.success_items = (
                    state["metrics"].field_metrics.extracted_fields - state["metrics"].field_metrics.missing_fields
                ) + (state["metrics"].table_metrics.total_extracted_rows - state["metrics"].table_metrics.failed_extracted_rows)

            result_metrics.failed_items = (
                state["metrics"].field_metrics.missing_fields + state["metrics"].table_metrics.failed_extracted_rows
            )

            result_metrics.total_items = (
                state["metrics"].field_metrics.total_fields + state["metrics"].table_metrics.total_extracted_rows
            )

            if result_metrics.total_items is not None and result_metrics.success_items is not None:
                if result_metrics.total_items > 0:
                    result_metrics.success_rate = result_metrics.success_items / result_metrics.total_items
                else:
                    result_metrics.success_rate = 0
            else:
                result_metrics.success_rate = 0

            weights = {
                "consistency": 0.4,
                "validation": 0.3,
                "mapping": 0.3,
            }

            consistency_accuracy = state.get("metrics", {}).consistency_accuracy if state.get("metrics") else 0.0
            validation_score = state.get("metrics", {}).validation_score if state.get("metrics") else 0.0
            mapping_score = state.get("metrics", {}).mapping_accuracy if state.get("metrics") else 0.0

            result_metrics.quality_pipeline_score = (
                consistency_accuracy * weights["consistency"]
                + validation_score * weights["validation"]
                + mapping_score * weights["mapping"]
            )

            result_metrics.processing_time = self._calculate_processing_time(state)

            self.logger.info(
                'event=result-metrics-calculated message="Result metrics calculated" '
                "success_rate=%.2f%% quality_score=%.2f%% processing_time=%.2f seconds "
                "total=%d successful=%d failed=%d",
                result_metrics.success_rate,
                result_metrics.quality_pipeline_score,
                result_metrics.processing_time,
                result_metrics.total_items,
                result_metrics.success_items,
                result_metrics.failed_items,
            )

        except Exception:
            self.logger.exception(
                'event=result-metrics-error message="Error calculating result metrics"',
            )
            return ResultMetrics()
        return result_metrics

    async def analyze_metrics(self, state: TrainingState) -> TrainingState:
        """
        Analyze all metrics and update the state with results.
        """
        self.logger.info(
            'event=start-metrics-analysis message="Starting comprehensive metrics analysis"',
        )

        try:
            if "metrics" not in state or state["metrics"] is None:
                from schemas.training import PerformanceMetrics

                state["metrics"] = PerformanceMetrics()

            # Calculate detailed metrics
            state["metrics"].field_metrics = self._analyze_field_extraction(state)
            state["metrics"].table_metrics = self._analyze_table_structure(state)
            state["metrics"].validation_metrics = self._analyze_validation_status(state)

            # Calculate overall metrics
            state["metrics"].mapping_accuracy = self._calculate_mapping_accuracy(state)
            state["metrics"].consistency_accuracy = self._calculate_consistency_accuracy(state)
            state["metrics"].validation_score = self._calculate_validation_score(state)

            # Calculate result metrics
            state["metrics"].result_metrics = await self._calculate_result_metrics(state)

            field_errors = list(state["metrics"].field_metrics.errors.get("field_validation", []))
            table_errors = list(state["metrics"].table_metrics.errors.get("table_validation", []))

            if field_errors or table_errors:
                state["error"] = "Validation Process Failure"

            state["result_summary"] = {
                "logs": {
                    "field": {
                        "error": field_errors,
                    },
                    "table": {
                        "error": table_errors,
                    },
                },
                "metrics": {
                    "item": {
                        **state["metrics"].result_metrics.model_dump(),
                        **state["metrics"].model_dump(include={"mapping_accuracy", "consistency_accuracy"}),
                    },
                    "field": {
                        **state["metrics"].field_metrics.model_dump(
                            include={"total_fields", "success_fields", "accuracy"},
                        ),
                    },
                    "table": {
                        **state["metrics"].table_metrics.model_dump(
                            exclude={"extracted_tables", "failed_extracted_rows", "errors"},
                        ),
                    },
                },
            }

            self.logger.info(
                "event=metrics-analysis-completed "
                'message="Metrics analysis completed successfully" '
                "field_accuracy=%.2f table_completeness=%.2f mapping_accuracy=%.2f",
                state["metrics"].field_metrics.accuracy,
                state["metrics"].table_metrics.table_extract_completeness,
                state["metrics"].mapping_accuracy,
            )

        except Exception:
            self.logger.exception(
                'event=metrics-analysis-error message="Error during metrics analysis"',
            )

        return state
