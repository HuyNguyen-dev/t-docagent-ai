from pathlib import Path
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool
from langchain_experimental.utilities import PythonREPL

from config import settings
from handlers.llm_configuration import LLMConfigurationHandler
from models.conversation import Conversation
from models.document_content import DocumentContent
from models.document_work_item import DocumentWorkItem
from utils.constants import DATA_CHART_DIR
from utils.functions import make_kb_tool
from utils.logger.custom_logging import LoggerMixin

# PLEASE DO NOT REFACTOR THIS TO AVOID RE-INITIALIZATION
kb_handler = None
if settings.ENABLE_KNOWNLEDEGE_BASE:
    from handlers.knowledge_base import KnowledgeBaseHandler

    llm_handler = LLMConfigurationHandler()
    kb_handler = KnowledgeBaseHandler(llm_handler=llm_handler)

python_repl = PythonREPL()


class DefaultTools(LoggerMixin):
    def __init__(self, conv_id: str, kb_dicts: list[dict]) -> None:
        self.conv_id = conv_id
        self.kb_dicts = kb_dicts
        self.conv_db = None
        self.dwi_id = None
        super().__init__()

    @property
    def tools(self) -> list[BaseTool]:
        """
        Returns a list of tool functions available for LLM-driven workflows.

        Returns:
            list: List of bound methods tools of DefaultTools.
        """
        tools = [
            StructuredTool.from_function(coroutine=self.get_work_item_content, parse_docstring=True),
            StructuredTool.from_function(coroutine=self.update_status_for_work_item, parse_docstring=True),
            StructuredTool.from_function(coroutine=self.get_training_logs_and_metrics, parse_docstring=True),
            StructuredTool.from_function(coroutine=self.user_collaboration_needed, parse_docstring=True),
            StructuredTool.from_function(coroutine=self.execute_python_chart_generation, parse_docstring=True),
        ]
        if settings.ENABLE_KNOWNLEDEGE_BASE:
            tools.extend(make_kb_tool(kb, self.query_knowledge_base) for kb in self.kb_dicts if kb is not None)
        return tools

    async def _get_conversation_by_id(self) -> None:
        conv_db = await Conversation.get(self.conv_id)
        if conv_db is not None:
            self.dwi_id = conv_db.dwi_id or None
        self.conv_db = conv_db

    async def get_work_item_content(self) -> dict:
        """
        Fetches and returns the data content of a Work Item (WI).

        Returns:
            dict: If the call completes without error, returns a dictionary with key "success"
                    and the data content as value.  ex {'success': '<data or content>'
                  If an error occurs or the item is not found, returns a dictionary with key "error"
                    and the error message as value. {'error': '<error message>'}
        """
        msg = f"Document Content information with id {self.dwi_id} not found in the database."
        if self.dwi_id is None:
            return {"error": msg}

        dc_db = await DocumentContent.find_one(DocumentContent.dwi_id == self.dwi_id)
        if dc_db is None:
            return {"error": msg}
        content = dc_db.model_dump()
        content.pop("metadata")
        return {"success": content}

    async def get_training_logs_and_metrics(self) -> dict:
        """
        Retrieves the training logs and metrics for the current Work Item (WI).

        This function fetches the metadata associated with the document content of the WI,
        which contains logs and metrics generated during the training process.

        Returns:
            dict: If successful, returns a dictionary with key "success" and the logs/metrics as value,
                  e.g., {'success': <logs_and_metrics_dict>}.
                  If an error occurs or the item is not found, returns a dictionary with key "error"
                  and the error message as value, e.g., {'error': '<error message>'}.
        """
        msg = f"Document Content information with id {self.dwi_id} not found in the database."
        if self.dwi_id is None:
            return {"error": msg}

        dc_db = await DocumentContent.find_one(DocumentContent.dwi_id == self.dwi_id)
        if dc_db is None:
            return {"error": msg}
        content = dc_db.model_dump()
        return {"success": content.pop("metadata")}

    async def update_status_for_work_item(
        self,
        stage: str,
        state: str,
    ) -> dict:
        """
        Updates status the stage and state of a Work Item (WI) in the database.

        Args:
            stage (str): The current stage of the agent process, e.g., "Validation" or "Processing".
            state (str): The status of the current stage, e.g., "In Process", "Failed", "Success",
                or "User Collaboration Needed".

        Returns:
            dict: If the call completes without error, success message if the update is performed,
                    returns a dictionary with key "success" and the result validation as value.
                    ex {'success': '<data or content>'
                If an error occurs or the process validation failure, returns a dictionary with key "error"
                and the error message as value. ex {'error': '<error message>'}
        """
        msg = f"Document Content information with id {self.dwi_id} not found in the database."
        if self.dwi_id is None:
            return {"error": msg}

        dwi_db = await DocumentWorkItem.get(self.dwi_id)
        await dwi_db.set({"stage": stage, "state": state})
        return {"success": "Update status information success."}

    async def update_content_for_work_item(
        self,
        transformed_content: dict[str, Any],
        computed_content: dict[str, Any],
    ) -> str:
        """
        Update the transformed_content and computed_content fields of a Work Item's Content in the database.

        Args:
            transformed_content (dict): A dictionary of transformed content for the DWI,
                such as normalized or extracted data.
            computed_content (dict): A dictionary of computed results or values for the DWI,
                such as calculations or summaries.

        Returns:
            str: Success message if the update is performed, or an error message if the DWI content is not found.
        """
        msg = f"Document Content information with id {self.dwi_id} not found in the database."
        if self.dwi_id is None:
            return msg
        try:
            dc_db = await DocumentContent.find_one(DocumentContent.dwi_id == self.dwi_id)
            if dc_db is None:
                return msg
            await dc_db.set(
                {
                    "transformed_content": transformed_content,
                    "computed_content": computed_content,
                },
            )
        except Exception:
            self.logger.exception(
                'event=update-content-dwi-exception message="Failed to update content for DWI %s"',
                self.dwi_id,
            )
            return "Failed to update content for DWI"
        return "Update content information success."

    async def user_collaboration_needed(
        self,
        collaboration_msg: str,
    ) -> str:
        """
        Handle an interrupt in the workflow that requires human-in-the-loop review, approval, or action.

        Args:
            collaboration_msg (str): A message describing why the workflow is interrupted and what needs human attention.

        Returns:
            bool: True if the user accepts/approves and the workflow should continue, False if ignored or not accepted.
        """
        self.logger.debug(
            'event=call-function-need-collaboration_need message="Reason: %s',
            collaboration_msg,
        )

    async def query_knowledge_base(
        self,
        kb_name: str,
        query: str,
    ) -> dict:
        """
        Query a specific knowledge base to retrieve relevant information with optional context expansion.

        Args:
            kb_name (str): The name of the knowledge base to query.
            query (str): The search query or question to find relevant information.

        Returns:
            str: The retrieved information or answer from the knowledge base.
        """
        chunks, citations = await kb_handler.query(
            kb_name=kb_name,
            query=query,
        )
        content = "".join(chunk.content for chunk in chunks)
        return {
            "success": {
                "content": content,
                "citations": citations,
            },
        }

    async def execute_python_chart_generation(
        self,
        code: str,
        description: str = "Python code to execute and generate a chart",
        save_folder_path: str = str(DATA_CHART_DIR),
    ) -> dict:
        """
        A function to execute Python code using PythonREPL to plot a chart based on the provided code.
        All generated charts will be saved to the src/data/charts/ directory.

        Notes:
            You need have a line code to check exited folder to save, if not existed you must create the folder
            So, You must have a line code to save image chart to this folder.
            The name file you can generate, remember it should unique.

        Args:
            code (str): The Python code to execute
            description (str): Description of what the code does
            save_folder_path (str): The folder path to store the generate chart

        Returns:
            dict: The output of the executed code or error message
        """
        try:
            save_folder_path: Path = Path(save_folder_path)
            if not DATA_CHART_DIR.exists():
                DATA_CHART_DIR.mkdir(exist_ok=True)

            if not save_folder_path.exists():
                save_folder_path.mkdir(exist_ok=True)

            self.logger.debug(
                'event=execute-python-generate-chartmessage="Executing Python code: %s and save in path %s"',
                description,
                save_folder_path,
            )
            # Ensure the code saves charts to ./data directory
            if "plt.savefig" in code and "src/data/charts" not in code:
                # Replace any savefig calls to use ./data directory
                import re

                code = re.sub(
                    r"plt\.savefig\(['\"]([^'\"]*)['\"]",
                    r"plt.savefig('src/data/charts/\1'",
                    code,
                )

            result = python_repl.run(code)
        except Exception as e:
            error_msg = f"Error executing Python code: {e!s}"
            self.logger.debug(
                'event=execute-python-generate-chart-failedmessage="Executing Python code: %s and save in path %s"error=%s',
                description,
                save_folder_path,
                error_msg,
            )
            return {
                "error": error_msg,
            }
        return {
            "success": f"Code executed successfully. Output:\n{result}",
        }
