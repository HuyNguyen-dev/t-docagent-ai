from typing import Literal, cast

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from agents.basic.state import BasicState
from agents.basic.tools import add, get_weather, multiply
from helpers.llm.chat import LLMService

tools = [get_weather, add, multiply]


async def chat_node(
    state: BasicState,
    config: RunnableConfig,
) -> Command[Literal["__end__", "tools"]]:
    messages = state["messages"]
    model_name = config.get("configurable", {}).get("model_name", "gemini-2.0-flash")
    llm = LLMService(model_name).create_llm()
    llm_with_tools = llm.bind_tools(tools)
    response = await llm_with_tools.ainvoke(messages)

    ai_message = cast(AIMessage, response)

    goto = "__end__"
    if ai_message.tool_calls:
        goto = "tools"

    return Command(
        goto=goto,
        update={
            "messages": response,
        },
    )
