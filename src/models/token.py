from typing import ClassVar

from beanie import Document, Indexed
from pymongo import IndexModel

from schemas.token import TokenInDB
from settings.mongodb.db_collections import CollectionName


class Token(TokenInDB, Document):
    """Token model for MongoDB using Beanie."""

    # Add indexes for efficient queries
    token_hash: Indexed(str, unique=True)  # Unique index on token hash
    user_id: Indexed(str)  # Index on user_id for fast user token lookups

    class Settings:
        name = CollectionName.TOKEN.value
        indexes: ClassVar[list[IndexModel]] = [
            IndexModel([("user_id", 1), ("is_active", 1)]),  # Compound index for active user tokens
            IndexModel([("expires_at", 1)], sparse=True),  # Index for expiration cleanup
            IndexModel([("created_at", -1)]),  # Index for sorting by creation date
        ]
