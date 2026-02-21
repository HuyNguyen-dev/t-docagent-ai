from beanie import Document

from schemas.knowledge_base import KnowledgeBaseInDB
from settings.mongodb.db_collections import CollectionName


class KnowledgeBase(KnowledgeBaseInDB, Document):
    """Knowledge base model for MongoDB operations using Beanie."""

    class Settings:
        name = CollectionName.KNOWLEDGE_BASE.value
