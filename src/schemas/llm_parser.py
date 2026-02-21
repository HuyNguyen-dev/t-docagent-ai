from pydantic import BaseModel


class DocumentMetadata(BaseModel):
    main_heading: str | None = ""
    parent_heading: str | None = ""  # Allow None for top-level headings


class DocumentChunk(BaseModel):
    content: str
    metadata: DocumentMetadata = DocumentMetadata()


class DocumentContent(BaseModel):
    document: list[DocumentChunk]
