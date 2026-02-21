from beanie import Document

from schemas.message import MessageInDB
from settings.mongodb.db_collections import CollectionName


class Message(MessageInDB, Document):
    class Settings:
        name = CollectionName.MESSAGE.value
