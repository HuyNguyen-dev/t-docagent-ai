from beanie import Document

from schemas.action_package import ActionPackageInDB
from settings.mongodb.db_collections import CollectionName


class ActionPackage(ActionPackageInDB, Document):
    # Optional edit overwrite some fields and create index on field

    class Settings:
        name = CollectionName.ACTION_PACKAGE.value
