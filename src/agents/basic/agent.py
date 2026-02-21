from langgraph.graph import START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

from agents.basic.chat import chat_node
from agents.basic.state import BasicState
from agents.basic.tools import add, get_weather, multiply

tools = [get_weather, add, multiply]
# Define Graph and add Nodes
workflow = StateGraph(BasicState)
workflow.add_node("chat_node", chat_node)
tool_node = ToolNode(tools=tools)
workflow.add_node("tools", tool_node)

# Add Edges
workflow.add_edge(START, "chat_node")
workflow.add_edge("tools", "chat_node")
workflow.compile()

# Add config or compile parameters
compile_kwargs = {
    "checkpointer": None,
    "store": None,
    "interrupt_before": None,
    "interrupt_after": None,
    "debug": False,
    "name": "basic_agent",
}

basic_graph: CompiledStateGraph = workflow.compile(**compile_kwargs)
