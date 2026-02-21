from beanie import Document

from schemas.tag import TagInDB
from settings.mongodb.db_collections import CollectionName


class Tag(TagInDB, Document):
    """Tag model for MongoDB operations using Beanie."""

    class Settings:
        name = CollectionName.TAG.value
