from beanie import Document

from schemas.agent import AgentInDB
from settings.mongodb.db_collections import CollectionName


class Agent(AgentInDB, Document):
    # Optional edit overwrite some fields and create index on field

    class Settings:
        name = CollectionName.AGENT.value
