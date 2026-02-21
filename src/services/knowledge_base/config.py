from handlers.llm_configuration import LLMConfigurationHandler
from initializer import mindsdb_client
from schemas.llm_configuration import BaseLLMModelConfig, LLMConfigurationInput
from schemas.model_config import MindsDbModelConfigs, ModelConfig
from utils.constants import KEY_SCHEMA_EMBEDDING_CONFIG, KEY_SCHEMA_RERANK_CONFIG
from utils.enums import ModelProvider
from utils.functions import decrypt_and_migrate
from utils.logger.custom_logging import LoggerMixin


class ConfigService(LoggerMixin):
    """Service for managing MindsDB configuration."""

    def __init__(self, llm_handler: LLMConfigurationHandler) -> None:
        super().__init__()
        self._llm_handler = llm_handler

    async def set_config(self, config_input: LLMConfigurationInput) -> bool:
        """Set the MindsDB configuration for embedding and reranking models."""
        owner_config = await self._llm_handler.get_owner_llm_config()
        if config_input.rerank is not None:
            rerank_model = config_input.rerank.name
            reranking_provider = config_input.rerank.provider
            await owner_config.update(
                {
                    "$set": {
                        "rerank": BaseLLMModelConfig(**config_input.rerank.model_dump()).model_dump(),
                    },
                },
            )
            reranking_config = self._llm_handler.get_llm_config_by_key(
                owner_config=owner_config,
                key=KEY_SCHEMA_RERANK_CONFIG,
            )
            config = MindsDbModelConfigs(
                reranking_model=ModelConfig(
                    model_name=rerank_model,
                    provider="google" if reranking_provider == ModelProvider.GOOGLE_AI else "openai",
                    api_key=decrypt_and_migrate(
                        reranking_config["api_key"],
                    ),
                ),
            )
            self.logger.debug(
                'event=config-set has_reranking=%s message="Setting MindsDB configuration"',
                config.reranking_model is not None,
            )
            await mindsdb_client.set_config(config)
        if config_input.embedding is not None:
            embedding_model = config_input.embedding.name
            embedding_provider = config_input.embedding.provider
            await owner_config.update(
                {
                    "$set": {
                        "embedding": BaseLLMModelConfig(**config_input.embedding.model_dump()).model_dump(),
                    },
                },
            )
            embedding_config = self._llm_handler.get_llm_config_by_key(
                owner_config=owner_config,
                key=KEY_SCHEMA_EMBEDDING_CONFIG,
            )
            config = MindsDbModelConfigs(
                embedding_model=ModelConfig(
                    model_name=embedding_model,
                    provider="google" if embedding_provider == ModelProvider.GOOGLE_AI else "openai",
                    api_key=decrypt_and_migrate(
                        embedding_config["api_key"],
                    ),
                ),
            )
            self.logger.debug(
                'event=config-set has_embedding=%s message="Setting MindsDB configuration"',
                config.embedding_model is not None,
            )

            await mindsdb_client.set_config(config)
        self.logger.info(
            'event=config-set-success message="MindsDB configuration set successfully"',
        )
        return True

    async def get_config(self) -> MindsDbModelConfigs | None:
        """Get the current MindsDB configuration."""
        self.logger.info(
            'event=config-get message="Retrieving MindsDB configuration"',
        )
        config = await mindsdb_client.get_config()
        if config:
            self.logger.info(
                "event=config-get-success "
                "has_embedding=%s "
                "has_reranking=%s "
                'message="MindsDB configuration retrieved successfully"',
                config.embedding_model is not None,
                config.reranking_model is not None,
            )
            return config
        return None

    async def set_default_llm(self, llm_config: ModelConfig) -> bool:
        """Set the default LLM configuration for the MindsDB client."""
        self.logger.info(
            'event=default-llm-set message="Setting default LLM configuration"',
        )
        success = await mindsdb_client.set_default_llm(llm_config)
        self.logger.info(
            'event=default-llm-set-success message="Default LLM configuration set successfully"',
        )
        if not success:
            self.logger.error(
                'event=default-llm-set-failed message="Failed to set default LLM configuration"',
            )
            return False
        return success
