from abc import ABC, abstractmethod
from typing import Literal

import orjson
import tiktoken
from langchain.prompts import SystemMessagePromptTemplate
from langchain.tools import BaseTool
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage, trim_messages
from langchain_core.runnables import RunnableConfig
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import AzureChatOpenAI, ChatOpenAI
from langgraph.graph import MessagesState, StateGraph
from langgraph.types import Command

from helpers.agui_event import AGUI
from models.agent import Agent
from models.conversation import Conversation
from models.llm_configuration import LLMConfiguration
from schemas.agent import AgentLLMModel
from utils.constants import DEFAULT_MAX_TOKEN, DEFAULT_MESSAGE_LENGTH, TRIMMING_MESSAGE_RATIO
from utils.enums import LLMProvider, RedisChannelName
from utils.llm import filter_models
from utils.logger.custom_logging import LoggerMixin


class BaseChatAgent(LoggerMixin, ABC):
    def __init__(self, conv_id: str, agent_config: Agent) -> None:
        self.conv_id = conv_id
        self.conv_db = None
        self.agent_db = agent_config
        self.llm = None
        self.run_book = None
        self.llm_with_tools = None
        self.tools_by_name = None
        self.tools: list[BaseTool] = None
        self.sse_event = AGUI(chanel=f"{RedisChannelName.CONVERSATION}:{conv_id}")
        self.instruction_prompt: SystemMessagePromptTemplate | None = None
        super().__init__()

    @property
    def system_message(self) -> BaseMessage:
        prompt_variables = self._init_instruction_prompt_variables()
        if self.instruction_prompt is None:
            return SystemMessagePromptTemplate.from_template(
                f"You are {self.agent_db.name}, an AI agent created to be engaging and provide helpful assistance.",
            )
        return self.instruction_prompt.format_messages(**prompt_variables)[0]

    def _init_instruction_prompt_variables(self) -> dict:
        return {
            "name": f"{self.agent_db.name} Agent",
            "description": self.agent_db.description,
            "tools": "\n".join(
                [f"- {tool.name}: {tool.description}" for tool in self.tools],
            )
            if self.tools is not None
            else "no tools",
            "run_book": self.run_book,
        }

    def _prepare_llm_creation_params(
        self,
        agt_llm_config: AgentLLMModel,
        owner_config: LLMConfiguration | None,
    ) -> dict[str, any]:
        llm_params = {
            "is_default": False,
            "provider": agt_llm_config.provider,
            "llm_name": agt_llm_config.name,
        }

        if agt_llm_config.provider == LLMProvider.AZURE_OPENAI:
            if agt_llm_config.api_key and agt_llm_config.api_key.get_secret_value():
                llm_params.update(
                    {
                        "api_key": agt_llm_config.api_key.get_secret_value(),
                        "deployment_name": agt_llm_config.deployment_name,
                        "endpoint": agt_llm_config.base_url,
                        "api_version": agt_llm_config.api_version,
                    },
                )
            elif owner_config and owner_config.azure_openai:
                found_azure_config = False
                for az_config in owner_config.azure_openai:
                    if az_config.name == agt_llm_config.name:
                        llm_params.update(
                            {
                                "api_key": az_config.api_key.get_secret_value() or "",
                                "deployment_name": az_config.deployment_name,
                                "endpoint": az_config.base_url,
                                "api_version": az_config.api_version,
                            },
                        )
                        found_azure_config = True
                        break
                if not found_azure_config:
                    self.logger.warning(
                        "event=worker-agent-llm-config-missing "
                        "message='Azure config named %s not found in owner's default configurations.'",
                        agt_llm_config.name,
                    )
                    llm_params["api_key"] = ""
            else:
                self.logger.warning(
                    "event=worker-agent-llm-config-missing "
                    "message='No Azure OpenAI API key provided for agent and no owner config found.'",
                )
                llm_params["api_key"] = ""
        else:  # OpenAI or Google
            if agt_llm_config.api_key and agt_llm_config.api_key.get_secret_value():
                llm_params["api_key"] = agt_llm_config.api_key.get_secret_value()
            elif owner_config:
                if agt_llm_config.provider == LLMProvider.OPENAI and owner_config.openai_api_key:
                    llm_params["api_key"] = owner_config.openai_api_key.get_secret_value()
                elif agt_llm_config.provider == LLMProvider.GOOGLE_AI and owner_config.google_api_key:
                    llm_params["api_key"] = owner_config.google_api_key.get_secret_value()
                else:
                    self.logger.warning(
                        "event=worker-agent-llm-config-missing "
                        "message='No default API key found for provider %s in owner config.'",
                        agt_llm_config.provider,
                    )
                    llm_params["api_key"] = ""
            else:
                self.logger.warning(
                    "event=worker-agent-llm-config-missing "
                    "message='No API key provided for agent and no owner config found for provider %s.'",
                    agt_llm_config.provider,
                )
                llm_params["api_key"] = ""
        return llm_params

    @abstractmethod
    def build_workflow(self, conv_id: str | None = None) -> StateGraph:
        """Build and return the agent's workflow graph (StateGraph)."""

    async def chat_node(self, state: MessagesState, config: RunnableConfig) -> dict:
        llm_model = self.llm_with_tools if self.llm_with_tools is not None else self.llm
        messages = state["messages"]  # Initialize messages with the full state
        if len(state["messages"]) > DEFAULT_MESSAGE_LENGTH:
            if isinstance(llm_model.bound, ChatGoogleGenerativeAI):
                model_name = llm_model.model.split("/")[1]
            elif isinstance(llm_model.bound, ChatOpenAI):
                model_name = f"openai-{llm_model.model_name}"
            elif isinstance(llm_model.bound, AzureChatOpenAI):
                model_name = f"azure-openai-{llm_model.model_name}"
            max_input_tokens = filter_models([model_name])[0]["max_input_tokens"]
            max_input_tokens = max(DEFAULT_MAX_TOKEN, int(max_input_tokens) * TRIMMING_MESSAGE_RATIO)
            if model_name.startswith(("gpt-3.5-turbo-0301", "gpt-3.5-turbo", "gpt-4", "gemini")):
                messages = trim_messages(
                    messages=state["messages"],
                    token_counter=llm_model,
                    strategy="last",
                    max_tokens=max_input_tokens,
                    start_on="human",
                    end_on=("human", "tool"),
                    include_system=True,
                )
            else:
                self.logger.warning(
                    'event=trim_messages-error message="The model has been not supported to generate token yet."',
                )
                messages = self._trim_messages_fallback(
                    messages=state["messages"],
                    last_n_messages=DEFAULT_MESSAGE_LENGTH,
                    end_on=("human", "tool"),
                )
        try:
            response = await llm_model.ainvoke(messages, config=config)
        except Exception as e:
            self.logger.exception(
                'event=chat-node-call-llm-failed message="Got Exception Error"',
            )
            error_message = AIMessage(
                content="I apologize, but I'm experiencing technical difficulties. "
                f"Please try again in a moment. Error: {type(e).__name__}",
                additional_kwargs={"error": str(e)},
            )
            return {"messages": [error_message]}
        return {"messages": [response]}

    async def call_tool(self, state: MessagesState) -> Command[Literal["chat_node"]]:
        result = []
        for tool_call in state["messages"][-1].tool_calls:
            tool = self.tools_by_name[tool_call["name"]]
            try:
                observation: dict | str = await tool.ainvoke(tool_call["args"])
                try:
                    if isinstance(observation, str):
                        observation = orjson.loads(observation)
                    content = observation["success"] if "error" not in observation else observation["error"]
                    status = "error" if "error" in observation else "success"
                except Exception:
                    content = observation
                    status = "error" if observation == "" else "success"
                result.append(
                    ToolMessage(
                        content=content,
                        name=tool_call["name"],
                        tool_call_id=tool_call["id"],
                        status=status,
                    ),
                )
            except Exception:
                self.logger.exception(
                    'event=call-tool-failed message="Agent call tool: %s with args=%s has error."',
                    tool_call["name"],
                    tool_call["args"],
                )
                result.append(
                    ToolMessage(
                        content="",
                        name=tool_call["name"],
                        tool_call_id=tool_call["id"],
                        status="error",
                    ),
                )
            continue
        return Command(goto="chat_node", update={"messages": result})

    async def _init_conversation(self, conv_id: str | None) -> bool:
        """Initialize the conversation DB for the agent."""
        if conv_id is None:
            self.logger.error(
                'event=initialize-agent-failed message="Conversation ID not provided."',
            )
            return False
        self.conv_db = await Conversation.get(conv_id)
        if self.conv_db is None:
            self.logger.error(
                'event=initialize-agent-failed message="Conversation with id %s not found."',
                conv_id,
            )
            return False
        return True

    @abstractmethod
    async def _init_agent_properties(self) -> bool:
        """Initialize the agent's LLM, tools, and any other properties. Child classes should extend this if needed."""
        # This method should be extended by subclasses to load LLM, tools, etc.
        return True

    async def initialize_properties(self, conv_id: str | None = None) -> bool:
        """Initialize the agent's properties, including conversation DB, LLM, and tools."""
        try:
            conv_id = conv_id or self.conv_id
            if not await self._init_conversation(conv_id):
                return False
            if not await self._init_agent_properties():
                return False
        except Exception:
            self.logger.exception(
                'event=initialize-agent-exception message="Exception occurred during initialization."',
            )
            return False
        return True

    @abstractmethod
    async def ask_human(self, state: MessagesState) -> dict:
        """Escalates the conversation to a human agent or signals that human intervention is required."""

    @abstractmethod
    async def should_continue(self, state: MessagesState) -> Literal["ask_human", "tools", "__end__"]:
        """
        Determine the next step the chat agent should take based on the current message state.

        Parameters:
            state (MessagesState): The current state of the message conversation, which includes
                                user inputs, previous responses, and metadata for decision-making.

        Returns:
            Literal["ask_human", "tools", "__end__"]:
                - "ask_human": The agent decides to escalate the conversation to a human.
                - "tools": The agent will proceed by invoking tools to assist in the response.
                - "__end__": The conversation should be terminated or no further action is needed.
        """

    def _trim_messages_fallback(
        self,
        messages: dict[str, any],
        last_n_messages: int | None = None,
        max_input_tokens: int | None = None,
        start_on: str | None = None,
        end_on: str | tuple[str, ...] = ("human", "tool"),
    ) -> dict[str, any]:
        if last_n_messages is not None:
            trimmed = messages[-last_n_messages:]
        else:
            trimmed = []
            total_tokens = 0
            encoding = tiktoken.get_encoding("cl100k_base")
            for msg in reversed(messages):
                if isinstance(msg, HumanMessage):
                    msg_tokens = len(encoding.encode(msg.content[0]["text"]))
                else:
                    msg_tokens = len(encoding.encode(msg.content))
                if total_tokens + msg_tokens > max_input_tokens:
                    break
                trimmed.append(msg)
                total_tokens += msg_tokens

            # restore order
            trimmed.reverse()

            # ensure we start on a specific role
            if start_on:
                while trimmed and trimmed[0].type != start_on:
                    trimmed.pop(0)

            # ensure we end on a specific role
            if end_on:
                if isinstance(end_on, str):
                    end_on = (end_on,)
                while trimmed and trimmed[-1].type not in end_on:
                    trimmed.pop()

        return trimmed
