from typing import Literal

from beanie.operators import In
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolCall, ToolMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.types import interrupt

from agents.react.base import BaseChatAgent
from agents.react.conversational_agent.state import ConversationalAgentState
from agents.react.conversational_agent.tools import ConversationalTools
from handlers.llm_configuration import LLMConfigurationHandler
from helpers.llm.chat import LLMService
from helpers.mcp_client import MCPClient
from models.agent import Agent
from models.knowledge_base import KnowledgeBase
from models.runbook import RunBook
from schemas.knowledge_base import KnowledgeBaseToolView
from settings.prompts.conversational_agent import GOAL_DRIVEN_CONVERSATIONAL_AGENT_MESSAGE_SYSTEM, QUESTION_CLASSIFICATION_PROMPT
from utils.constants import DEFAULT_FUNCTION_INTERRUPT, FRIENDLY_QUESTION
from utils.enums import AgentReasoning, ReasoningEffort


class ConversationalAgent(BaseChatAgent):
    def __init__(self, conv_id: str, agent_config: Agent) -> None:
        super().__init__(conv_id, agent_config)
        self.instruction_prompt = GOAL_DRIVEN_CONVERSATIONAL_AGENT_MESSAGE_SYSTEM
        self.agent_state = ConversationalAgentState
        self.kb_names = agent_config.advanced_options.kb_names

    async def _init_agent_properties(self) -> bool:
        agent_db = self.agent_db
        rb_db = await RunBook.find_one(
            RunBook.name == agent_db.run_book.name,
            RunBook.version == agent_db.run_book.version,
        )
        if rb_db is None:
            self.logger.error(
                'event=initialize-worker-agent-failed message="Fetch runbook for agent with name %s and version %s not found."',
                agent_db.run_book.name,
                agent_db.run_book.version,
            )
            return False
        self.run_book = rb_db.prompt

        owner_config = await LLMConfigurationHandler.get_owner_llm_config()
        llm_params = self._prepare_llm_creation_params(agent_db.model, owner_config)

        self.llm = LLMService(
            llm=llm_params.pop("llm_name"),
            include_thoughts=agent_db.advanced_options.reasoning != AgentReasoning.DISABLED,
            effort=ReasoningEffort.MEDIUM,
        ).create_llm(**llm_params)

        if self.llm is None:
            return False

        kb_dbs = await KnowledgeBase.find(
            In(KnowledgeBase.name, self.agent_db.advanced_options.kb_names),
            projection_model=KnowledgeBaseToolView,
        ).to_list()
        conversational_tools = ConversationalTools([kb.model_dump() for kb in kb_dbs])
        self.tools = conversational_tools.tools
        action_tools = await MCPClient().get_tools_from_agent_config(
            action_packages=self.agent_db.action_packages,
        )
        self.tools.extend(action_tools)
        self.llm_with_tools = self.llm.bind_tools(self.tools)
        self.tools_by_name = {tool.name: tool for tool in self.tools}
        return True

    def build_workflow(self, conv_id: str | None = None) -> StateGraph:
        conv_id = conv_id or self.conv_id
        workflow = StateGraph(ConversationalAgentState)
        workflow.add_node("chat_node", self.chat_node)
        workflow.add_node("tools", self.call_tool)
        workflow.add_node("ask_human", self.ask_human)
        workflow.add_edge(START, "chat_node")
        workflow.add_conditional_edges(
            "chat_node",
            self.should_continue,
            path_map=["ask_human", "tools", END],
        )
        workflow.add_edge("ask_human", "chat_node")
        return workflow

    async def ask_human(self, state: MessagesState) -> dict:
        last_message = state["messages"][-1]
        new_msg: list[BaseMessage] = []
        if isinstance(last_message, AIMessage):
            tool_call = last_message.tool_calls[0]
            human_resp = interrupt(tool_call["args"])
            new_msg.extend(
                [
                    ToolMessage(
                        content=human_resp["data"],
                        name=tool_call["name"],
                        tool_call_id=tool_call["id"],
                    ),
                    HumanMessage(content=human_resp["data"]),
                ],
            )
            await self._init_conversation(self.conv_db.id)
            self.conv_db.user_collaboration.hitl = False
            self.conv_db.user_collaboration.reason = ""
            await self.conv_db.save()
        return {"messages": new_msg}

    async def should_continue(self, state: MessagesState) -> Literal["ask_human", "tools", "__end__"]:
        messages = state.get("messages", [])
        last_message = messages[-1]
        if not last_message.tool_calls:
            return END
        if last_message.tool_calls[0]["name"] == DEFAULT_FUNCTION_INTERRUPT:
            tool_call: ToolCall = last_message.tool_calls[0]
            await self._init_conversation(self.conv_db.id)
            self.conv_db.user_collaboration.hitl = True
            self.conv_db.user_collaboration.reason = tool_call["args"]["collaboration_msg"]
            await self.conv_db.save()
            return "ask_human"
        return "tools"

    async def classify_message(self, question: str) -> bool:
        """Classify whether the user message requires using the runbook or not."""
        try:
            owner_config = await LLMConfigurationHandler.get_owner_llm_config()
            llm_params = self._prepare_llm_creation_params(self.agent_db.model, owner_config)
            model_name = llm_params.get("llm_name")
            llm_params.pop("llm_name")
            classification_llm = LLMService(
                llm=model_name,
            ).create_llm(**llm_params)

            classification_prompt = QUESTION_CLASSIFICATION_PROMPT.format_messages()[0]

            classification_response = await classification_llm.ainvoke(
                [
                    classification_prompt,
                    HumanMessage(content=f"Classify this message: {question}"),
                ],
            )

            # Extract classification result
            classification = classification_response.content.strip().upper()
        except Exception:
            self.logger.exception(
                'event=failed-question-classification message="Classification failed, defaulting to use runbook"',
            )
            return False  # Default to using runbook if classification fails
        return classification == FRIENDLY_QUESTION  # Return True if TASK, False if CASUAL
