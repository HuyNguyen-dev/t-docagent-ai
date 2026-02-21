from pathlib import Path

from langchain_core.tools import BaseTool, StructuredTool
from langchain_experimental.utilities import PythonREPL

from config import settings
from handlers.llm_configuration import LLMConfigurationHandler
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


class ConversationalTools(LoggerMixin):
    def __init__(self, kb_dicts: list[dict]) -> None:
        self.kb_dicts = kb_dicts
        super().__init__()

    @property
    def tools(self) -> list[BaseTool]:
        """
        Returns a list of tool functions available for conversational agent.

        Returns:
            list: List of bound methods tools of ConversationalTools.
        """
        tools = [
            StructuredTool.from_function(coroutine=self.user_collaboration_needed, parse_docstring=True),
            StructuredTool.from_function(coroutine=self.execute_python_chart_generation, parse_docstring=True),
        ]
        if settings.ENABLE_KNOWNLEDEGE_BASE:
            tools.extend(make_kb_tool(kb, self.query_knowledge_base) for kb in self.kb_dicts if kb is not None)
        return tools

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
