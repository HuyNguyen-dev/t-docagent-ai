from beanie import Document

from schemas.llm_configuration import LLMConfigurationInDB
from settings.mongodb.db_collections import CollectionName


class LLMConfiguration(LLMConfigurationInDB, Document):
    # Optional edit overwrite some fields and create index on field

    class Settings:
        name = CollectionName.LLM_CONFIGURATION.value
