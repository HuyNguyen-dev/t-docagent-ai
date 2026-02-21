from collections.abc import AsyncGenerator
from typing import Annotated

import orjson
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse

from helpers.jwt_auth import require_scopes_cached
from initializer import kb_handler, redis_pubsub_manager
from schemas.chunks import (
    AddChunkRequest,
    DeleteChunksRequest,
    UpdateChunkRequest,
)
from schemas.document import DocumentUpdate
from schemas.knowledge_base import (
    EmptyKnowledgeBaseRequest,
    ExternalKnowledgeBaseRequest,
    KnowledgeBaseUpdate,
    PreviewChunkResponse,
    RetrievalMode,
)
from schemas.llm_configuration import LLMConfigurationInput
from schemas.model_config import ModelConfig
from schemas.response import BasicResponse
from schemas.tag import TagCreateRequest, TagUpdate
from utils.common import is_valid_url, validate_and_process
from utils.enums import APIScope, ChunkingMode, ParserType, RedisChannelName

router = APIRouter(prefix="/knowledge-base", dependencies=[])


@router.post(
    "/config/set",
    dependencies=[
        Depends(require_scopes_cached(APIScope.LLM_ACCESS)),
    ],
)
async def set_config(
    response: Response,
    config_input: LLMConfigurationInput,
) -> BasicResponse:
    """
    Set the MindsDB configuration for embedding and reranking models.

    **Required Scopes:** `llm_access`
    """
    try:
        success = await kb_handler.set_config(config_input)
        if not success:
            response.status_code = status.HTTP_400_BAD_REQUEST
            return BasicResponse(
                status="failed",
                message="Failed to set MindsDB configuration.",
                data=None,
            )
        response.status_code = status.HTTP_200_OK
        return BasicResponse(
            status="success",
            message="MindsDB configuration set successfully.",
            data=None,
        )
    except Exception as e:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return BasicResponse(
            status="failed",
            message=f"Failed to set MindsDB configuration: {e!s}",
            data=None,
        )


@router.get(
    "/config/get",
    dependencies=[
        Depends(require_scopes_cached(APIScope.KB_ADMIN)),
    ],
)
async def get_config(
    response: Response,
) -> BasicResponse:
    """
    Get the current MindsDB configuration.

    **Required Scopes:** `kb_admin`
    """
    config = await kb_handler.get_config()
    if config is None:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return BasicResponse(
            status="failed",
            message="Failed to retrieve MindsDB configuration.",
            data=None,
        )

    response.status_code = status.HTTP_200_OK
    return BasicResponse(
        status="success",
        message="MindsDB configuration retrieved successfully.",
        data=config.model_dump(),
    )


@router.post(
    "/config/default-llm",
    dependencies=[
        Depends(require_scopes_cached(APIScope.KB_ADMIN)),
    ],
)
async def set_default_llm(
    response: Response,
    llm_config: ModelConfig,
) -> BasicResponse:
    """
    Set the default LLM configuration for MindsDB using available API keys.

    **Required Scopes:** `kb_admin`
    """
    success = await kb_handler.set_default_llm(llm_config=llm_config)
    if not success:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return BasicResponse(
            status="failed",
            message="Failed to set default LLM configuration.",
            data=None,
        )
    response.status_code = status.HTTP_200_OK
    return BasicResponse(
        status="success",
        message="Default LLM configuration set successfully.",
        data=None,
    )


@router.post(
    "/chunks/preview",
    dependencies=[
        Depends(require_scopes_cached(APIScope.KB_ADMIN)),
    ],
)
async def preview_chunk(
    response: Response,
    file: UploadFile,
    chunking_mode: ChunkingMode,
    chunk_length: Annotated[int, Query(ge=100, le=1000, description="Chunk length (100-1000)")] = 500,
    chunk_overlap: Annotated[int, Query(ge=0, le=1000, description="Chunk overlap (0-1000)")] = 50,
) -> BasicResponse:
    """Preview chunks from uploaded document and return total chunk count."""
    if not validate_and_process(file):
        response.status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
        return BasicResponse(
            status="failed",
            message="Only PDF/doc/docx/txt/html files are supported.",
            data=None,
        )
    chunks_data = await kb_handler.preview_chunk(
        chunking_mode=chunking_mode,
        chunk_length=chunk_length,
        chunk_overlap=chunk_overlap,
        file=file,
    )
    if not chunks_data:
        resp = BasicResponse(
            status="failed",
            message="Failed to preview chunk.",
            data=None,
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
    else:
        # Calculate total chunks from the preview data
        total_chunks = len(chunks_data) if isinstance(chunks_data, list) else 0

        # Create response data
        response_data = PreviewChunkResponse(
            chunks=chunks_data,
            total_chunks=total_chunks,
            document_name=file.filename or "Unknown Document",
        )

        resp = BasicResponse(
            status="success",
            message="Preview chunk created successfully.",
            data=response_data.model_dump(),
        )
        response.status_code = status.HTTP_200_OK
    return resp


@router.post(
    "/datasets/{kb_id}/documents/{doc_id}/chunks/preview",
    dependencies=[
        Depends(require_scopes_cached(APIScope.KB_ADMIN)),
    ],
)
async def preview_chunk_in_update(
    response: Response,
    kb_id: str,
    doc_id: str,
    chunking_mode: ChunkingMode,
    chunk_length: Annotated[int, Query(ge=100, le=1000, description="Chunk length (100-1000)")] = 500,
    chunk_overlap: Annotated[int, Query(ge=0, le=1000, description="Chunk overlap (0-1000)")] = 50,
) -> BasicResponse:
    """Preview chunks from uploaded document and return total chunk count."""
    chunks_data = await kb_handler.preview_chunk_in_update(
        kb_id=kb_id,
        doc_id=doc_id,
        chunking_mode=chunking_mode,
        chunk_length=chunk_length,
        chunk_overlap=chunk_overlap,
    )
    if not chunks_data:
        resp = BasicResponse(
            status="failed",
            message="Failed to preview chunk.",
            data=None,
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
    else:
        # Calculate total chunks from the preview data
        total_chunks = len(chunks_data) if isinstance(chunks_data, list) else 0

        # Create response data
        response_data = PreviewChunkResponse(
            chunks=chunks_data,
            total_chunks=total_chunks,
            document_name="",
        )

        resp = BasicResponse(
            status="success",
            message="Preview chunk created successfully.",
            data=response_data.model_dump(),
        )
        response.status_code = status.HTTP_200_OK
    return resp


@router.post(
    "/datasets",
    dependencies=[
        Depends(require_scopes_cached(APIScope.KB_ADMIN)),
    ],
)
async def create_empty_kb(
    response: Response,
    request: EmptyKnowledgeBaseRequest,
) -> BasicResponse:
    """Create an empty knowledge base with the specified name."""
    success, kb_id = await kb_handler.create_empty_kb(
        kb_name=request.kb_name,
        description=request.description,
    )
    if not success:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return BasicResponse(
            status="failed",
            message="Failed to create empty kb.",
            data=None,
        )
    response.status_code = status.HTTP_201_CREATED
    return BasicResponse(
        status="success",
        message="Empty KB is created successfully.",
        data=kb_id,
    )


@router.post(
    "/dataset/from-file",
    dependencies=[
        Depends(require_scopes_cached(APIScope.KB_ADMIN)),
    ],
)
async def create_from_file(
    response: Response,
    background_tasks: BackgroundTasks,
    kb_input: str,
    file: Annotated[UploadFile, File(...)],
) -> BasicResponse:
    """Create a knowledge base with the specified name."""
    if not validate_and_process(file):
        response.status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
        return BasicResponse(
            status="failed",
            message="Only PDF/doc/docx/txt/html files are supported.",
            data=None,
        )
    kb = await kb_handler.create_from_file(
        new_kb_input=kb_input,
        file=file,
        background_tasks=background_tasks,
    )
    response.status_code = status.HTTP_202_ACCEPTED
    return BasicResponse(
        status="success",
        message="Knowledge base creation started in the background.",
        data=kb.model_dump(),
    )


@router.post(
    "/dataset/from-url",
    dependencies=[
        Depends(require_scopes_cached(APIScope.KB_ADMIN)),
    ],
)
async def create_from_url(
    response: Response,
    background_tasks: BackgroundTasks,
    kb_input: str,
    url_name: str,
    url: str,
) -> BasicResponse:
    """Create a knowledge base with the specified name."""
    if not is_valid_url(url):
        response.status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
        return BasicResponse(
            status="failed",
            message="Only url http/https are supported.",
            data=None,
        )
    kb = await kb_handler.create_from_url(
        new_kb_input=kb_input,
        url_name=url_name,
        url=url,
        background_tasks=background_tasks,
    )
    response.status_code = status.HTTP_202_ACCEPTED
    return BasicResponse(
        status="success",
        message="Knowledge base creation started in the background.",
        data=kb.model_dump(),
    )


async def event_generator(kb_id: str, request: Request) -> AsyncGenerator[bytes, None]:
    """Generate knowledge base creation events."""
    channel = f"{RedisChannelName.KB}:{kb_id}"
    async for message in redis_pubsub_manager.get_messages(channel):
        if await request.is_disconnected():
            break
        yield f"data: {orjson.dumps(message).decode('utf-8')}\n\n"


@router.get("/datasets/{kb_id}/events/stream")
def stream(kb_id: str, request: Request) -> StreamingResponse:
    """Stream knowledge base creation events using Server-Sent Events."""
    return StreamingResponse(
        event_generator(kb_id, request),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no"},
    )


@router.post(
    "/dataset/external",
    dependencies=[
        Depends(require_scopes_cached(APIScope.KB_ADMIN)),
    ],
)
async def create_from_external(
    response: Response,
    request: ExternalKnowledgeBaseRequest,
) -> BasicResponse:
    """Create a knowledge base with the specified name."""
    success = await kb_handler.create_from_external(
        kb_name=request.kb_name.lower(),
        description=request.description,
        vector_db_config=request.vector_db_config,
    )
    if not success:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return BasicResponse(
            status="failed",
            message=f"Failed to create knowledge base '{request.kb_name}'.",
            data=None,
        )
    response.status_code = status.HTTP_201_CREATED
    return BasicResponse(
        status="success",
        message=f"Knowledge base '{request.kb_name}' created successfully.",
        data=None,
    )


@router.post(
    "/datasets/{kb_id}/insert-file",
    dependencies=[
        Depends(require_scopes_cached(APIScope.KB_ADMIN)),
    ],
)
async def insert_content_file(
    response: Response,
    background_tasks: BackgroundTasks,
    kb_id: str,
    parser_type: ParserType,
    file: Annotated[UploadFile, File(...)],
    config: str | None = None,
) -> BasicResponse:
    """
    Insert content from a file into a knowledge base.

    This endpoint parses a document using the specified LLM parser and inserts its content into the knowledge base.

    **Required Scopes:** `kb_admin`
    """
    if not validate_and_process(file):
        response.status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
        return BasicResponse(
            status="failed",
            message="Only PDF/doc/docx/txt/html files are supported.",
            data=None,
        )
    doc_id = await kb_handler.insert_file_content(
        background_tasks=background_tasks,
        kb_id=kb_id,
        file=file,
        parser_type=parser_type,
        config=config,
    )
    if doc_id is not None:
        response.status_code = status.HTTP_200_OK
        return BasicResponse(
            status="success",
            message="Document parsed successfully.",
            data=doc_id,
        )
    response.status_code = status.HTTP_400_BAD_REQUEST
    return BasicResponse(
        status="failed",
        message="Document is already parsed with current configuration.",
        data=doc_id,
    )


@router.post(
    "/datasets/{kb_id}/insert-url",
    dependencies=[
        Depends(require_scopes_cached(APIScope.KB_ADMIN)),
    ],
)
async def insert_content_url(
    response: Response,
    background_tasks: BackgroundTasks,
    kb_id: str,
    parser_type: ParserType,
    url_name: str,
    url: str,
    config: str | None = None,
) -> BasicResponse:
    """
    Insert content from a file into a knowledge base.

    This endpoint parses a document using the specified LLM parser and inserts its content into the knowledge base.

    **Required Scopes:** `kb_admin`
    """
    if not is_valid_url(url):
        response.status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
        return BasicResponse(
            status="failed",
            message="Only url http/https are supported.",
            data=None,
        )
    doc_id = await kb_handler.insert_url_content(
        background_tasks=background_tasks,
        kb_id=kb_id,
        parser_type=parser_type,
        url_name=url_name,
        url=url,
        config=config,
    )

    response.status_code = status.HTTP_200_OK
    return BasicResponse(
        status="success",
        message="Document parsed successfully.",
        data=doc_id,
    )


@router.post(
    "/datasets/{kb_id}/query",
    dependencies=[
        Depends(require_scopes_cached(APIScope.KB_ADMIN)),
    ],
)
async def query(
    response: Response,
    kb_id: str,
    query: str,
    retrieval_mode: RetrievalMode | None = None,
) -> BasicResponse:
    """
    Query a knowledge base by its name.

    **Required Scopes:** `kb_admin`
    """
    kb_name = await kb_handler.get_kb_name_by_id(kb_id)
    content, citations = await kb_handler.query(
        kb_name=kb_name.lower(),
        query=query,
        retrieval_mode=retrieval_mode,
    )

    if (content is None and not []) or (citations is None and not {}):
        response.status_code = status.HTTP_400_BAD_REQUEST
        return BasicResponse(
            status="failed",
            message=f"No results found for query '{query}' in knowledge base '{kb_name}'.",
            data=None,
        )
    data = {
        "content": content,
        "citations": citations,
    }
    response.status_code = status.HTTP_200_OK
    return BasicResponse(
        status="success",
        message=f"Query results for '{query}' in knowledge base '{kb_name}'",
        data=data,
    )


@router.get(
    "/datasets",
    dependencies=[
        Depends(require_scopes_cached(APIScope.KB_ADMIN)),
    ],
)
async def list_kbs(
    response: Response,
) -> BasicResponse:
    """
    List all available knowledge bases (no pagination).

    **Required Scopes:** `kb_admin`
    """
    kb_names = await kb_handler.list_for_agents()

    if kb_names is None:
        resp = BasicResponse(
            status="failed",
            message="Failed to retrieve knowledge base list.",
            data=None,
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
    else:
        resp = BasicResponse(
            status="success",
            message=f"Found {len(kb_names)} knowledge base(s).",
            data={
                "total_items": len(kb_names),
                "knowledge_bases": kb_names,
            },
        )
        response.status_code = status.HTTP_200_OK
    return resp


@router.get(
    "/dashboard",
    dependencies=[
        Depends(require_scopes_cached(APIScope.KB_ADMIN)),
    ],
)
async def get_kb_dashboard(
    response: Response,
    page: Annotated[int, Query(ge=1, description="Page number (1-based)")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Number of items per page")] = 10,
    tags: Annotated[list[str] | None, Query(description="Filter by exact tag name")] = None,
    search: Annotated[str | None, Query(description="Search keyword in name, description, or tag")] = None,
) -> BasicResponse:
    """
    Get comprehensive dashboard information for all knowledge bases with optional filtering and search.

    Returns detailed statistics, counts, and information about all knowledge bases
    including document counts, chunk counts, vector types, and data source distributions.
    Can be filtered by exact tag name and searched by keyword in name, description, or tag.

    **Required Scopes:** `kb_admin`

    """
    page_response = await kb_handler.kb_dashboard(page=page, page_size=page_size, tags=tags, search=search)

    if page_response is None:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return BasicResponse(
            status="failed",
            message="Failed to retrieve knowledge base dashboard.",
            data=None,
        )

    message = f"Successfully retrieved dashboard for {page_response.metadata.total_items} knowledge base(s)."
    filters = []
    if tags:
        filters.append(f"tags: '{tags}'")
    if search and search.strip():
        filters.append(f"search: '{search.strip()}'")

    if filters:
        message += f" Filtered by {', '.join(filters)}."

    response.status_code = status.HTTP_200_OK
    return BasicResponse(
        status="success",
        message=message,
        data=page_response.model_dump(),
    )


@router.delete(
    "/datasets/{kb_id}",
    dependencies=[
        Depends(require_scopes_cached(APIScope.KB_ADMIN)),
    ],
)
async def delete(
    kb_id: str,
    response: Response,
) -> BasicResponse:
    """
    Delete a knowledge base by its name or ID.

    **Required Scopes:** `kb_admin`
    """

    success = await kb_handler.delete(kb_id=kb_id)

    if not success:
        resp = BasicResponse(
            status="failed",
            message=f"Failed to delete knowledge base '{kb_id}'.",
            data=None,
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
    else:
        resp = BasicResponse(
            status="success",
            message=f"Knowledge base '{kb_id}' deleted successfully.",
            data=None,
        )
        response.status_code = status.HTTP_200_OK
    return resp


@router.get(
    "/datasets/{kb_id}/details",
    dependencies=[
        Depends(require_scopes_cached(APIScope.KB_ADMIN)),
    ],
)
async def get_kb_details(
    response: Response,
    kb_id: str,
) -> BasicResponse:
    """
    Get detailed information for a specific knowledge base.

    Returns comprehensive information about the knowledge base including
    configuration, document counts, chunk counts, and status information.
    """
    kb_details = await kb_handler.get_kb_detail(kb_id)

    if kb_details is None:
        response.status_code = status.HTTP_404_NOT_FOUND
        return BasicResponse(
            status="failed",
            message=f"Knowledge base '{kb_id}' not found.",
            data=None,
        )

    response.status_code = status.HTTP_200_OK
    return BasicResponse(
        status="success",
        message=f"Successfully retrieved details for knowledge base '{kb_id}'.",
        data=kb_details.model_dump(),
    )


@router.get(
    "/datasets/{kb_id}/documents",
    dependencies=[
        Depends(require_scopes_cached(APIScope.KB_ADMIN)),
    ],
)
async def get_kb_documents(
    response: Response,
    kb_id: str,
    page: Annotated[int, Query(ge=1, description="Page number (1-based)")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Number of items per page")] = 10,
    search: Annotated[str | None, Query(description="Search keyword in document id, name, or metadata")] = None,
) -> BasicResponse:
    """
        Get all documents for a specific knowledge base with pagination.
    default=10
        including statistics, document types, and individual document details.

    """
    page_response = await kb_handler.list_kb_documents(kb_id=kb_id, page=page, page_size=page_size, search=search)

    if page_response is None:
        resp = BasicResponse(
            status="failed",
            message=f"Knowledge base '{kb_id}' not found or no documents available.",
            data=None,
        )
        response.status_code = status.HTTP_404_NOT_FOUND
    else:
        resp = BasicResponse(
            status="success",
            message=(
                f"Successfully retrieved {len(page_response.items)} documents for knowledge base '{kb_id}' (page {page})."
                + (f" Filtered by search: '{search.strip()}'." if search and search.strip() else "")
            ),
            data=page_response.model_dump(),
        )
        response.status_code = status.HTTP_200_OK
    return resp


@router.get(
    "/datasets/{kb_id}/documents/{doc_id}",
    dependencies=[
        Depends(require_scopes_cached(APIScope.KB_ADMIN)),
    ],
)
async def get_kb_document(
    response: Response,
    kb_id: str,
    doc_id: str,
) -> BasicResponse:
    """
    Get a specific knowledge base document by ID.

    Returns detailed information about the document including metadata,
    chunking mode, word count, and upload time.
    """
    document = await kb_handler.get_kb_document(kb_id, doc_id)

    if document is None:
        response.status_code = status.HTTP_404_NOT_FOUND
        return BasicResponse(
            status="failed",
            message=f"Document with ID '{doc_id}' not found.",
            data=None,
        )

    response.status_code = status.HTTP_200_OK
    return BasicResponse(
        status="success",
        message=f"Successfully retrieved document '{document.name}' from {kb_id}.",
        data=document.model_dump(),
    )


@router.put(
    "/datasets/{kb_id}/documents/{doc_id}",
    dependencies=[
        Depends(require_scopes_cached(APIScope.KB_ADMIN)),
    ],
)
async def update_kb_document(
    response: Response,
    background_tasks: BackgroundTasks,
    kb_id: str,
    doc_id: str,
    update_data: DocumentUpdate,
) -> BasicResponse:
    """
    Update a knowledge base document.

    Allows updating the document name, chunking mode, word count, and metadata.
    """
    # Run update in background and return immediately
    await kb_handler.update_kb_document(
        kb_id=kb_id,
        doc_id=doc_id,
        update_data=update_data,
        background_tasks=background_tasks,
    )

    response.status_code = status.HTTP_202_ACCEPTED
    return BasicResponse(
        status="success",
        message=f"Update for document '{doc_id}' has been scheduled.",
        data={"doc_id": doc_id},
    )


@router.delete(
    "/datasets/{kb_id}/documents/{doc_id}",
    dependencies=[
        Depends(require_scopes_cached(APIScope.KB_ADMIN)),
    ],
)
async def delete_kb_document(
    response: Response,
    kb_id: str,
    doc_id: str,
) -> BasicResponse:
    """
    Delete a knowledge base document by ID.

    Permanently removes the document from the knowledge base.
    This action cannot be undone.
    """
    success = await kb_handler.delete_kb_document(kb_id=kb_id, doc_id=doc_id)

    if not success:
        response.status_code = status.HTTP_404_NOT_FOUND
        return BasicResponse(
            status="failed",
            message=f"Document with ID '{doc_id}' not found or could not be deleted.",
            data=None,
        )

    response.status_code = status.HTTP_200_OK
    return BasicResponse(
        status="success",
        message=f"Document with ID '{doc_id}' deleted successfully.",
        data={"deleted_document_id": doc_id},
    )


@router.put(
    "/datasets/{kb_id}",
    dependencies=[
        Depends(require_scopes_cached(APIScope.KB_ADMIN)),
    ],
)
async def update_knowledge_base(
    response: Response,
    kb_id: str,
    update_data: KnowledgeBaseUpdate,
) -> BasicResponse:
    """
    Update a knowledge base configuration and properties.

    Allows updating the tag, configuration (embedding model, chunk settings, etc.),
    and active status of an existing knowledge base.
    """
    # Call the handler to update the knowledge base
    success = await kb_handler.update_kb(
        kb_id=kb_id,
        tags=update_data.tags or None,
        description=update_data.description if update_data.description != "" else None,
        config=update_data.config,
        is_active=update_data.is_active,
    )

    if not success:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return BasicResponse(
            status="failed",
            message=f"Failed to update knowledge base '{kb_id}'.",
            data=success,
        )

    response.status_code = status.HTTP_200_OK
    return BasicResponse(
        status="success",
        message=f"Knowledge base '{kb_id}' updated successfully.",
        data=success,
    )


@router.get(
    "/datasets/{kb_id}/documents/{doc_id}/chunks",
    dependencies=[
        Depends(require_scopes_cached(APIScope.KB_ADMIN)),
    ],
)
async def get_document_chunks(
    response: Response,
    kb_id: str,
    doc_id: str,
    search: str | None = "",
    page: int = 1,
    page_size: int = 10,
) -> BasicResponse:
    """
    Get all chunks for a specific document with pagination support using pgvector.

    Args:
        kb_id: Knowledge base ID
        doc_id: Document ID
        search: Search keyword (optional)
        page: Page number (default: 1)
        page_size: Items per page (default: 10, max: 100)
        search_method: Search method - "keyword", "hybrid", or "semantic" (default: "keyword")
        hybrid_weight: Weight for hybrid search (0.0 = only vector, 1.0 = only BM25, default: 0.5)

    Returns:
        BasicResponse with ChunksResponse data containing chunks, pagination info, and document stats
    """
    # Validate pagination parameters
    page = max(page, 1)
    if page_size < 1 or page_size > 100:
        page_size = 10

    page_response = await kb_handler.get_all_chunks_with_paging(
        kb_id=kb_id,
        doc_id=doc_id,
        search=search,
        page=page,
        page_size=page_size,
    )

    if page_response is None:
        response.status_code = status.HTTP_404_NOT_FOUND
        return BasicResponse(
            status="failed",
            message=f"Document with ID '{doc_id}' not found or no chunks available.",
            data=None,
        )

    response.status_code = status.HTTP_200_OK
    return BasicResponse(
        status="success",
        message=f"Chunks retrieved successfully for document '{doc_id}'.",
        data=page_response.model_dump(),
    )


@router.post(
    "/datasets/{kb_id}/documents/{doc_id}/chunks",
    dependencies=[
        Depends(require_scopes_cached(APIScope.KB_ADMIN)),
    ],
)
async def add_chunk_to_document(
    response: Response,
    kb_id: str,
    doc_id: str,
    request: AddChunkRequest,
) -> BasicResponse:
    """
    Add a new chunk to a specific document.

    Returns:
        BasicResponse with AddChunkResponse data containing operation result and chunk ID
    """
    # Validate request data
    if not request.content or not request.content.strip():
        response.status_code = status.HTTP_400_BAD_REQUEST
        return BasicResponse(
            status="failed",
            message="Chunk content cannot be empty.",
            data=None,
        )
    # Call the handler to add the chunk
    success = await kb_handler.add_chunk(
        kb_id=kb_id,
        doc_id=doc_id,
        content=request.content.strip(),
    )

    if not success:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return BasicResponse(
            status="failed",
            message="Failed to add chunk to document.",
            data=success,
        )

    response.status_code = status.HTTP_201_CREATED
    return BasicResponse(
        status="success",
        message=f"Chunk added successfully to document '{doc_id}'.",
        data=success,
    )


@router.delete(
    "/datasets/{kb_id}/documents/{doc_id}/chunks",
    dependencies=[
        Depends(require_scopes_cached(APIScope.KB_ADMIN)),
    ],
)
async def delete_chunks_from_document(
    response: Response,
    kb_id: str,
    doc_id: str,
    request: DeleteChunksRequest,
) -> BasicResponse:
    """
    Delete multiple chunks from a specific document.

    Returns:
        BasicResponse with DeleteChunksResponse data containing operation result
    """
    # Validate request data
    if not request.chunk_ids or len(request.chunk_ids) == 0:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return BasicResponse(
            status="failed",
            message="At least one chunk ID must be provided for deletion.",
            data=None,
        )

    # Call the handler to delete the chunks
    success = await kb_handler.delete_chunks(
        kb_id=kb_id,
        doc_id=doc_id,
        chunk_ids=request.chunk_ids,
    )

    if not success:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return BasicResponse(
            status="failed",
            message=f"Failed to delete chunks from document '{doc_id}'.",
            data=success,
        )

    response.status_code = status.HTTP_200_OK
    return BasicResponse(
        status="success",
        message=f"Chunks deleted successfully from document '{doc_id}'.",
        data=success,
    )


@router.put(
    "/datasets/{kb_id}/documents/{doc_id}/chunks/{chunk_id}",
    dependencies=[
        Depends(require_scopes_cached(APIScope.KB_ADMIN)),
    ],
)
async def update_chunk_in_document(
    response: Response,
    kb_id: str,
    doc_id: str,
    chunk_id: str,
    request: UpdateChunkRequest,
) -> BasicResponse:
    """
    Update an existing chunk in a specific document.

    Returns:
        BasicResponse with UpdateChunkResponse data containing operation result
    """
    # Validate request data
    if not request.content or not request.content.strip():
        response.status_code = status.HTTP_400_BAD_REQUEST
        return BasicResponse(
            status="failed",
            message="Chunk content cannot be empty.",
            data=None,
        )

    # Call the handler to update the chunk
    success = await kb_handler.update_chunk(
        kb_id=kb_id,
        doc_id=doc_id,
        chunk_id=chunk_id,
        content=request.content.strip(),
    )

    if not success:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return BasicResponse(
            status="failed",
            message=f"Failed to update chunk '{chunk_id}' in document '{doc_id}'.",
            data=None,
        )

    response.status_code = status.HTTP_200_OK
    return BasicResponse(
        status="success",
        message=f"Chunk '{chunk_id}' updated successfully in document '{doc_id}'.",
        data=success,
    )


# Tag Management APIs
@router.post(
    "/tags",
    dependencies=[
        Depends(require_scopes_cached(APIScope.KB_ADMIN)),
    ],
)
async def create_tag(
    response: Response,
    request: TagCreateRequest,
) -> BasicResponse:
    """
    Create a new tag.

    **Required Scopes:** `kb_admin`

    Args:
        request: Tag creation request containing tag name
    """
    tag = await kb_handler.create_tag(request.name)

    if tag is None:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return BasicResponse(
            status="failed",
            message=f"Failed to create tag '{request.name}'. Tag name may already exist.",
            data=None,
        )

    response.status_code = status.HTTP_201_CREATED
    return BasicResponse(
        status="success",
        message=f"Tag '{tag.name}' created successfully.",
        data={
            "id": tag.id,
            "name": tag.name,
            "created_at": tag.created_at.isoformat(),
        },
    )


@router.get(
    "/tags/dropdown",
    dependencies=[
        Depends(require_scopes_cached(APIScope.KB_ADMIN)),
    ],
)
async def list_tags(
    response: Response,
    page: Annotated[int, Query(ge=1, description="Page number (1-based)")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Number of items per page")] = 10,
    search: Annotated[str | None, Query(description="Optional keyword to search in tag name (case-insensitive)")] = None,
    active_only: Annotated[bool, Query(description="Whether to show only active tags")] = True,
) -> BasicResponse:
    """
    List tags with pagination and optional search.

    **Required Scopes:** `kb_admin`

    Args:
        page: Page number (1-based, default: 1)
        page_size: Number of items per page (default: 10, max: 100)
        search: Optional keyword to search in tag name (case-insensitive)
        active_only: Whether to show only active tags (default: True)
    """
    page_response = await kb_handler.list_tags(page=page, page_size=page_size, search=search, active_only=active_only)

    if page_response is None:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return BasicResponse(
            status="failed",
            message="Failed to retrieve tags.",
            data=None,
        )

    response.status_code = status.HTTP_200_OK
    return BasicResponse(
        status="success",
        message=f"Successfully retrieved {len(page_response.items)} tag(s) on page {page}.",
        data=page_response.model_dump(),
    )


@router.get(
    "/tags/{tag_id}",
    dependencies=[
        Depends(require_scopes_cached(APIScope.KB_ADMIN)),
    ],
)
async def get_tag(
    response: Response,
    tag_id: str,
) -> BasicResponse:
    """
    Get a specific tag by ID.

    **Required Scopes:** `kb_admin`

    Args:
        tag_id: ID of the tag to retrieve
    """
    tag = await kb_handler.get_tag_by_id(tag_id)

    if tag is None:
        response.status_code = status.HTTP_404_NOT_FOUND
        return BasicResponse(
            status="failed",
            message=f"Tag with ID '{tag_id}' not found.",
            data=None,
        )

    response.status_code = status.HTTP_200_OK
    return BasicResponse(
        status="success",
        message=f"Successfully retrieved tag '{tag.name}'.",
        data={
            "id": tag.id,
            "name": tag.name,
            "created_at": tag.created_at.isoformat(),
            "created_by": tag.created_by,
            "is_active": tag.is_active,
        },
    )


@router.put(
    "/tags/{tag_id}",
    dependencies=[
        Depends(require_scopes_cached(APIScope.KB_ADMIN)),
    ],
)
async def update_tag(
    response: Response,
    tag_id: str,
    tag_update: TagUpdate,
) -> BasicResponse:
    """
    Update an existing tag.

    **Required Scopes:** `kb_admin`

    Args:
        tag_id: ID of the tag to update
        tag_update: Updated tag information
    """
    # Validate that at least one field is provided
    if not any(
        [
            tag_update.name is not None,
            tag_update.is_active is not None,
        ],
    ):
        response.status_code = status.HTTP_400_BAD_REQUEST
        return BasicResponse(
            status="failed",
            message="At least one field (name or is_active) must be provided for update.",
            data=None,
        )

    tag = await kb_handler.update_tag(tag_id, tag_update)

    if tag is None:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return BasicResponse(
            status="failed",
            message=f"Failed to update tag with ID '{tag_id}'. Tag may not exist or name may already be in use.",
            data=None,
        )

    response.status_code = status.HTTP_200_OK
    return BasicResponse(
        status="success",
        message=f"Tag '{tag.name}' updated successfully.",
        data={
            "id": tag.id,
            "name": tag.name,
            "is_active": tag.is_active,
        },
    )


@router.delete(
    "/tags/{tag_id}",
    dependencies=[
        Depends(require_scopes_cached(APIScope.KB_ADMIN)),
    ],
)
async def delete_tag(
    response: Response,
    tag_id: str,
) -> BasicResponse:
    """
    Delete a tag by ID.

    **Required Scopes:** `kb_admin`

    Args:
        tag_id: ID of the tag to delete

    Note:
        Cannot delete tags that are being used by knowledge bases.
    """
    success = await kb_handler.delete_tag(tag_id)

    if not success:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return BasicResponse(
            status="failed",
            message=f"Failed to delete tag with ID '{tag_id}'. Tag may not exist or is being used by knowledge bases.",
            data=None,
        )

    response.status_code = status.HTTP_200_OK
    return BasicResponse(
        status="success",
        message=f"Tag with ID '{tag_id}' deleted successfully.",
        data=tag_id,
    )
