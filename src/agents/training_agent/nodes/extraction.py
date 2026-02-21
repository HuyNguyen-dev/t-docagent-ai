from agents.training_agent.state import TrainingState
from handlers.llm_configuration import LLMConfigurationHandler
from helpers.llm.vision import VisionLLMService
from models.document_format import DocumentFormat
from schemas.document_format import DocumentFormatTable
from schemas.training import GenExtractionData
from utils.constants import KEY_EXTRACTION_CONFIG
from utils.logger.custom_logging import LoggerMixin

# PLEASE DO NOT REFACTOR THIS TO AVOID RE-INITIALIZATION
llm_handler = LLMConfigurationHandler()


class ExtractionNode(LoggerMixin):
    def __init__(self, vision_service: VisionLLMService | None = None) -> None:
        super().__init__()
        self.vision_service = vision_service

    @classmethod
    async def create(cls) -> "ExtractionNode":
        owner_config = await llm_handler.get_owner_llm_config()
        if owner_config is None:
            return cls()

        vision_service = VisionLLMService(
            **llm_handler.get_llm_config_by_key(
                owner_config=owner_config,
                key=KEY_EXTRACTION_CONFIG,
            ),
        )
        return cls(vision_service)

    def _format_table_output(self, table: DocumentFormatTable) -> str:
        """Format table output for system message.

        Args:
            table: The table object containing id and columns

        Returns:
            Formatted string representation of the table output
        """
        col_ids = [col.id for col in table.columns]

        mapped_col_output = [f'"{col_id}": "<value>"' for col_id in col_ids]
        mapped_col_output_text = ",\n\t\t\t\t\t\t".join(mapped_col_output)
        row_text = f"\t\t\t\t\t{{{{\n\t\t\t\t\t\t{mapped_col_output_text}\n\t\t\t\t\t}}}}"

        return f'{{{{\n\t\t\t\t"table_id": "{table.id}", \n\t\t\t\t"columns": \n\t\t\t\t[\n{row_text}\n\t\t\t\t]\n\t\t\t}}}}'

    def _format_system_message(self, system_message: str, document_format: DocumentFormat) -> str:
        """Format the system message with placeholders.

        Args:
            system_message: The base system message template
            document_format: The document format containing fields, tables, etc.

        Returns:
            The formatted system message with placeholders replaced
        """
        formatted_message = system_message

        has_fields = bool(document_format.fields)
        has_tables = bool(document_format.tables)

        if has_fields and not has_tables:
            fields_bullets = [
                f"* Field name **{field.display_name}** (`field_id`: `{field.id}`)"
                + (
                    f" - Following rule: `{field.additional_prompt}`"
                    if field.additional_prompt and field.additional_prompt.strip()
                    else ""
                )
                for field in document_format.fields
            ]
            fields_text = "\n".join(fields_bullets)
            formatted_message = formatted_message.replace(
                "{fields}",
                f"- **Expected Non-Table Fields**:\n {fields_text}",
            )
            fields_output = [f'"{field.id}": "value_of_{field.id}",' for field in document_format.fields]
            fields_output_text = "\n\t".join(fields_output)
            formatted_message = formatted_message.replace(
                "{fields_output_format}",
                f"{fields_output_text}",
            )

        elif has_tables and not has_fields:
            tables_bullets = []
            ids = []
            for table in document_format.tables:
                columns_bullets = [f"  * {col}" for col in table.columns]
                columns_text = "\n".join(columns_bullets)
                tables_bullets.append(f"* **{table.id}**\n{columns_text}")
                ids.append(table.id)
            tables_text = "\n".join(tables_bullets)
            formatted_message = formatted_message.replace(
                "{table_ids}",
                f" - **Table Ids**:\n {ids}",
            )
            formatted_message = formatted_message.replace(
                "{tables}",
                f" - **Table Definitions**:\n {tables_text}",
            )

            # Refactored table output generation
            tables_output = [self._format_table_output(table) for table in document_format.tables]
            tables_output_text = ",\n".join(tables_output)
            formatted_message = formatted_message.replace(
                "{tables_output_format}",
                f"\n[{tables_output_text}]",
            )

        elif has_fields and has_tables:
            fields_bullets = [
                f"* Field name **{field.display_name}** (`field_id`: `{field.id}`)"
                + (
                    f" - Following rule: `{field.additional_prompt}`"
                    if field.additional_prompt and field.additional_prompt.strip()
                    else ""
                )
                for field in document_format.fields
            ]
            fields_text = "\n".join(fields_bullets)
            formatted_message = formatted_message.replace(
                "{fields}",
                f"- **Expected Non-Table Fields**:\n {fields_text}",
            )
            fields_output = [f'"{field.id}": "<value>"' for field in document_format.fields]
            fields_output_text = ",\n\t\t\t".join(fields_output)
            formatted_message = formatted_message.replace(
                "{fields_output_format}",
                f"{fields_output_text}",
            )

            tables_bullets = []
            ids = []
            for table in document_format.tables:
                columns_bullets = [f"  * {col}" for col in table.columns]
                columns_text = "\n".join(columns_bullets)
                tables_bullets.append(f"* **{table.id}**\n{columns_text}")
                ids.append(table.id)
            tables_text = "\n".join(tables_bullets)
            formatted_message = formatted_message.replace(
                "{table_ids}",
                f" - **Table Ids**:\n {ids}",
            )
            formatted_message = formatted_message.replace(
                "{tables}",
                f" - **Table Definitions**:\n {tables_text}",
            )

            tables_output = [self._format_table_output(table) for table in document_format.tables]
            tables_output_text = "\n".join(tables_output)
            formatted_message = formatted_message.replace(
                "{tables_output_format}",
                f"\n\t\t[\n\t\t\t{tables_output_text}\n\t\t]",
            )
        else:
            formatted_message = formatted_message.replace("{fields}\n", "").replace("{fields}", "")
            formatted_message = formatted_message.replace("{fields_output_format}\n", "").replace("{fields_output_format}", "")
            formatted_message = formatted_message.replace("{table_ids}\n", "").replace("{table_ids}", "")
            formatted_message = formatted_message.replace("{tables}\n", "").replace("{tables}", "")
            formatted_message = formatted_message.replace("{tables_output_format}\n", "").replace("{tables_output_format}", "")

        if document_format.extraction_prompt:
            formatted_message = formatted_message.replace(
                "{extraction_prompt}",
                f"- **Extraction Prompt**:\n{document_format.extraction_prompt}",
            )
        else:
            formatted_message = formatted_message.replace(
                "{extraction_prompt}\n",
                "",
            ).replace("{extraction_prompt}", "")

        if document_format.sample_table_rows and not has_fields:
            formatted_message = formatted_message.replace(
                "{sample_table_rows}",
                f"- **Example Table Rows**:\n{document_format.sample_table_rows}",
            )
        else:
            formatted_message = formatted_message.replace("{sample_table_rows}\n", "").replace("{sample_table_rows}", "")

        return formatted_message

    async def extract_using_chain_of_thought(self, state: TrainingState) -> GenExtractionData | None:
        """Extract data using chain of thought approach.

        Args:
            state: The current state containing document format and images

        Returns:
            The extracted data or None if extraction failed
        """
        document_format = state.get("document_format")
        if not document_format:
            self.logger.warning(
                'event=missing-document-format message="No document format provided for extraction"',
            )
            return None
        try:
            formatted_system_message = self._format_system_message(state["system_message"], document_format)

            result = await self.vision_service.acall(
                system_message=formatted_system_message,
                base64_images=state["base64_images"],
                output_parser=state["output_parser"],
                is_pdf=state.get("is_pdf", False),
            )

        except Exception:
            self.logger.exception(
                'event=extraction-error message="Error during extraction"',
            )
            return None
        return result
