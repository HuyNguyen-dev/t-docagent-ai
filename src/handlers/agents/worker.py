from agents.react import WorkerAgent as ReActWorkerAgent
from handlers.agents.base import BaseAgentHandler
from models.agent import Agent
from utils.enums import AgentArchitecture


class WorkerAgentHandler(BaseAgentHandler):
    async def _create_agent_instance(self, conv_id: str, agent_config: Agent) -> ReActWorkerAgent | None:
        if agent_config.advanced_options.architecture == AgentArchitecture.REACT:
            return ReActWorkerAgent(conv_id, agent_config)
        return None
