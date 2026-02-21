from beanie import Document

from schemas.runbook import RunbookInDB
from settings.mongodb.db_collections import CollectionName


class RunBook(RunbookInDB, Document):
    class Settings:
        name = CollectionName.RUN_BOOK.value
