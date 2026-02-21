from agents.react import ConversationalAgent as ReActConversationalAgent
from handlers.agents.base import BaseAgentHandler
from models.agent import Agent
from utils.enums import AgentArchitecture


class ConversationalAgentHandler(BaseAgentHandler):
    async def _create_agent_instance(self, conv_id: str, agent_config: Agent) -> ReActConversationalAgent | None:
        if agent_config.advanced_options.architecture == AgentArchitecture.REACT:
            return ReActConversationalAgent(conv_id, agent_config)
        return None
