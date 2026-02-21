"""
Knowledge Base Handler Module

This module provides comprehensive knowledge base management functionality including:
- Document management and parsing
- Vector database operations
- Chunk management and querying
- Configuration management
"""

from .knowledge_base.base import ParserStrategy, VectorDBCreator
from .knowledge_base.chunk import ChunkService
from .knowledge_base.config import ConfigService
from .knowledge_base.document import DocumentService
from .knowledge_base.knowledge_base import KnowledgeBaseService
from .knowledge_base.parser import ParserStrategyFactory, ParseService
from .knowledge_base.tag import TagService
from .knowledge_base.vector_db import VectorDBFactory

__all__ = [
    "ChunkService",
    "ConfigService",
    "DocumentService",
    "KnowledgeBaseService",
    "ParseService",
    "ParserStrategy",
    "ParserStrategyFactory",
    "TagService",
    "VectorDBCreator",
    "VectorDBFactory",
]
