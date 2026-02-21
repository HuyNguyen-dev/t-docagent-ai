from typing import Any

from agents.training_agent.state import TrainingState
from schemas.document_format import DocumentFormatTable
from utils.logger.custom_logging import LoggerMixin


class MappingNode(LoggerMixin):
    """Node that maps extracted data fields and tables to target format based on DocumentFormat mapping."""

    def map_extraction(self, state: TrainingState) -> TrainingState:
        """Maps extracted fields and tables using the document format mappings."""
        if not state.get("document_format"):
            self.logger.info(
                'event=skip-mapping message="No document format provided, skipping mapping"',
            )
            return state

        if state.get("extracted_fields"):
            state = self._map_extracted_fields(state)

        if state.get("extracted_tables"):
            state = self._map_extracted_tables(state)

        return state

    def _map_extracted_fields(self, state: TrainingState) -> TrainingState:
        document_format = state["document_format"]
        document_type = state["document_type"]

        if not document_format.fields:
            return state

        try:
            self.logger.info('event=start-field-mapping message="Starting field mapping"')

            mapped_data_format_fields = {}
            mapped_data_type = {}
            extracted_fields = state["extracted_fields"]

            # Handle the new dict structure for fields
            if isinstance(extracted_fields, dict):
                for source_id, value in extracted_fields.items():
                    for field_mapping in document_format.fields:
                        if source_id == field_mapping.id:
                            target_value = field_mapping.static_value or value
                            mapped_data_format_fields[field_mapping.mapped_to] = target_value

            for mapping in document_type.fields.properties:
                mapped_data_type[mapping.id] = mapped_data_format_fields.get(mapping.id, "")

            state["mapped_fields"] = mapped_data_type
            self.logger.info(
                'event=fields-mapped message="Successfully mapped %d fields"',
                len(mapped_data_type),
            )

        except Exception:
            self.logger.exception('event=field-mapping-error message="Error during field mapping"')

        return state

    def _map_extracted_tables(self, state: TrainingState) -> TrainingState:
        document_format = state["document_format"]
        document_type = state["document_type"]

        if not document_format.tables:
            return state

        try:
            self.logger.info('event=start-table-mapping message="Starting table mapping"')

            table_mappings = {table.id: table for table in document_format.tables}
            mapped_tables = []

            for table_data in state["extracted_tables"]:
                table_id = table_data.table_id
                if not table_id or table_id not in table_mappings:
                    self.logger.warning(
                        'event=invalid-table-id message="Invalid or missing table ID: %s"',
                        table_id,
                    )
                    continue

                mapping_table = table_mappings[table_id]
                table_rows = table_data.columns

                mapped_table_data = {
                    "table_id": table_id,
                    "columns": self._map_table_data(table_rows, mapping_table),
                }
                mapped_tables.append(mapped_table_data)
                self.logger.info(
                    'event=table-mapped message="Successfully mapped table: %s"',
                    table_id,
                )

            mapped_data_type_table = {}
            for table in document_type.tables:
                for mapped_table in mapped_tables:
                    if table.id == mapped_table["table_id"]:
                        mapped_data_type_table[table.id] = {
                            "table_id": mapped_table["table_id"],
                            "columns": mapped_table["columns"],
                        }

            state["mapped_tables"] = mapped_data_type_table
            self.logger.info(
                'event=tables-mapped message="Successfully mapped %s tables"',
                len(mapped_tables),
            )

        except Exception:
            self.logger.exception(
                'event=table-mapping-error message="Error during table mapping"',
            )

        return state

    def _map_table_data(
        self,
        table_data: list[dict[str, str]],
        mapping_table: DocumentFormatTable,
    ) -> list[dict[str, Any]]:
        """Maps table data using the provided mapping table configuration."""
        try:
            column_mapping = {col.id: col.mapped_to for col in mapping_table.columns}

            mapped_rows = []
            for idx, row_data in enumerate(table_data):
                if not isinstance(row_data, dict):
                    continue

                mapped_row = self._map_row(row_data, column_mapping)
                if mapped_row:
                    mapped_rows.append(mapped_row)
                else:
                    self.logger.warning(
                        'event=empty-mapped-row message="No valid mappings found for row %s"',
                        idx,
                    )

        except Exception:
            self.logger.exception(
                'event=table-data-mapping-error message="Error mapping table data: %s"',
            )
            return []
        return mapped_rows

    def _map_row(self, row_data: dict[str, Any], column_mapping: dict[str, str]) -> dict[str, Any]:
        """Maps a single table row using the provided column mapping."""
        try:
            mapped_row = {}

            # Each column dict has a single key-value pair
            for field_id, value in row_data.items():
                if field_id in list(column_mapping.keys()):
                    mapped_row[column_mapping[field_id]] = value
                else:
                    mapped_row[column_mapping[field_id]] = ""
                    self.logger.debug(
                        'event=no-column-mapping message="No mapping found for field ID %s"',
                        field_id,
                    )
            if not mapped_row:
                self.logger.warning(
                    'event=empty-mapped-row message="No columns were mapped in this row"',
                )
            else:
                self.logger.debug(
                    'event=row-mapped message="Successfully mapped row with %d columns"',
                    len(mapped_row),
                )

        except Exception:
            self.logger.exception(
                'event=row-mapping-error message="Error mapping row"',
            )
            return {}
        return mapped_row
