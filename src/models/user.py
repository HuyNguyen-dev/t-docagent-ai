from typing import ClassVar

from beanie import Document, Indexed
from pymongo import IndexModel

from schemas.user import UserInDB
from settings.mongodb.db_collections import CollectionName


class User(UserInDB, Document):
    """User model for MongoDB using Beanie."""

    # Add indexes for efficient queries
    email: Indexed(str, unique=True)  # Unique index on email
    role: Indexed(str)  # Index on role for filtering
    status: Indexed(str)  # Index on status for filtering

    class Settings:
        name = CollectionName.USER.value
        indexes: ClassVar[list[IndexModel]] = [
            IndexModel([("role", 1), ("status", 1)]),  # Compound index for role/status filtering
            IndexModel([("created_at", -1)]),  # Index for sorting by creation date
            IndexModel([("last_seen_at", -1)], sparse=True),  # Index for last activity
        ]
