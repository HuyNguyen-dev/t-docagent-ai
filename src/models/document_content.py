from beanie import Document

from schemas.document_content import DocumentContentInDB
from settings.mongodb.db_collections import CollectionName


class DocumentContent(DocumentContentInDB, Document):
    # Optional edit overwrite some fields and create index on field

    class Settings:
        name = CollectionName.DOCUMENT_CONTENT.value
