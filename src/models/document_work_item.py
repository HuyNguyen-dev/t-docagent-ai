from beanie import Document

from schemas.document_work_item import DocumentWorkItemInDB
from settings.mongodb.db_collections import CollectionName


class DocumentWorkItem(DocumentWorkItemInDB, Document):
    # Optional edit overwrite some fields and create index on field

    class Settings:
        name = CollectionName.DOCUMENT_WORK_ITEM.value
