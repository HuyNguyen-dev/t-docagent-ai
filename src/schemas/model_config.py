from typing import Literal

from pydantic import BaseModel, Field


class ModelConfig(BaseModel):
    """Configuration for a single model (embedding or reranking)."""

    provider: Literal["openai", "google"] = Field(..., description="The model provider (e.g., 'openai', 'googleai')")
    model_name: str = Field(..., description="The specific model name")
    api_key: str = Field(..., description="API key for the model provider")


class MindsDbModelConfigs(BaseModel):
    """Configuration for knowledge base models including embedding and reranking models."""

    embedding_model: ModelConfig | None = Field(
        None,
        description="Configuration for the embedding model",
    )
    reranking_model: ModelConfig | None = Field(
        None,
        description="Configuration for the reranking model",
    )
