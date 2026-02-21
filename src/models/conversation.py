from beanie import Document

from schemas.conversation import ConversationInDB
from settings.mongodb.db_collections import CollectionName


class Conversation(ConversationInDB, Document):
    # Optional edit overwrite some fields and create index on field

    class Settings:
        name = CollectionName.CONVERSATION.value
