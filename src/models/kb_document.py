from beanie import Document

from schemas.document import DocumentInDB
from settings.mongodb.db_collections import CollectionName


class KBDocument(DocumentInDB, Document):
    """Knowledge base model for MongoDB operations using Beanie."""

    class Settings:
        name = CollectionName.KB_DOCUMENT.value
