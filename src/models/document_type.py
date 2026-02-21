from beanie import Document

from schemas.document_type import DocumentTypeInDB
from settings.mongodb.db_collections import CollectionName


class DocumentType(DocumentTypeInDB, Document):
    # Optional edit overwrite some fields and create index on field

    class Settings:
        name = CollectionName.DOUCMENT_TYPE.value
