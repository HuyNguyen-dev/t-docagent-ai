from typing import ClassVar

from beanie import Document, Indexed
from pymongo import IndexModel

from schemas.user import RoleInDB
from settings.mongodb.db_collections import CollectionName


class Role(RoleInDB, Document):
    """Role model for MongoDB using Beanie."""

    # Add indexes for efficient queries
    name: Indexed(str, unique=True)  # Unique index on role name
    created_by: Indexed(str)  # Index on creator for filtering

    class Settings:
        name = CollectionName.ROLE.value
        indexes: ClassVar[list[IndexModel]] = [
            IndexModel([("created_at", -1)]),  # Index for sorting by creation date
            IndexModel([("is_system_role", 1)]),  # Index for filtering system roles
        ]
