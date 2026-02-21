from beanie import Document

from schemas.document_format import DocumentFormatInDB
from settings.mongodb.db_collections import CollectionName


class DocumentFormat(DocumentFormatInDB, Document):
    # Optional edit overwrite some fields and create index on field

    class Settings:
        name = CollectionName.DOCUMENT_FORMAT.value
