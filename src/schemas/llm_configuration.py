from uuid import uuid4

from pydantic import BaseModel, Field, SecretStr

from utils.enums import LLMProvider


class BaseAzureLLMConfig(BaseModel):
    api_key: SecretStr = Field(default=SecretStr(""))
    deployment_name: str = ""
    base_url: str = ""
    api_version: str = "2025-04-01-preview"


class BaseLLMConfig(BaseModel):
    provider: LLMProvider = LLMProvider.GOOGLE_AI
    name: str = Field(max_length=100, default="")
    api_key: SecretStr = Field(default=SecretStr(""))


class AzureLLMConfig(BaseAzureLLMConfig):
    name: str = Field(max_length=100, default="")


class BaseLLMModelConfig(BaseAzureLLMConfig, BaseLLMConfig):
    pass


class BaseAzureLLMConfigResponse(BaseModel):
    api_key: str = ""
    deployment_name: str = ""
    base_url: str = ""
    api_version: str = "2025-04-01-preview"


class BaseLLMConfigResponse(BaseModel):
    provider: LLMProvider = LLMProvider.GOOGLE_AI
    name: str = Field(max_length=100, default="")
    api_key: str = ""


class AzureLLMConfigResponse(BaseAzureLLMConfigResponse):
    name: str = Field(max_length=100, default="")


class BaseLLMModelConfigResponse(BaseAzureLLMConfigResponse, BaseLLMConfigResponse):
    pass


class LangSmithSetup(BaseModel):
    name: str = Field(max_length=100, default="")
    is_tracing: bool = False
    api_key: SecretStr = Field(default=SecretStr(""))


class LangSmithSetupResponse(BaseModel):
    name: str = Field(max_length=100, default="")
    is_tracing: bool = False
    api_key: str = ""


class BaseLLMConfiguration(BaseModel):
    openai_api_key: SecretStr = ""
    google_api_key: SecretStr = ""
    azure_openai: list[AzureLLMConfig] = Field(default_factory=list)
    schema_discovery: BaseLLMModelConfig = Field(default_factory=BaseLLMModelConfig)
    extraction: BaseLLMModelConfig = Field(default_factory=BaseLLMModelConfig)
    embedding: BaseLLMModelConfig = Field(default_factory=BaseLLMModelConfig)
    rerank: BaseLLMModelConfig = Field(default_factory=BaseLLMModelConfig)
    langsmith: LangSmithSetup = Field(default_factory=LangSmithSetup)


class LLMConfigurationInput(BaseModel):
    openai_api_key: SecretStr | None = None
    google_api_key: SecretStr | None = None
    azure_openai: list[AzureLLMConfig] | None = None
    schema_discovery: BaseLLMModelConfig | None = None
    extraction: BaseLLMModelConfig | None = None
    embedding: BaseLLMModelConfig | None = None
    rerank: BaseLLMModelConfig | None = None
    langsmith: LangSmithSetup | None = None


class LLMConfigurationTest(BaseModel):
    openai_api_key: SecretStr | None = None
    google_api_key: SecretStr | None = None
    azure_openai: AzureLLMConfig | None = None
    schema_discovery: BaseLLMModelConfig | None = None
    embedding: BaseLLMModelConfig | None = None
    rerank: BaseLLMModelConfig | None = None


class LLMConfigurationInDB(BaseLLMConfiguration):
    id: str = Field(
        default_factory=lambda: f"lc-{uuid4()!s}",
        alias="_id",
        alias_priority=2,
    )
    user_id: str


class LLMConfigurationResponse(BaseModel):
    openai_api_key: str | None = None
    google_api_key: str | None = None
    azure_openai: list[AzureLLMConfigResponse] | None = None
    schema_discovery: BaseLLMModelConfigResponse | None = None
    extraction: BaseLLMModelConfigResponse | None = None
    embedding: BaseLLMModelConfigResponse | None = None
    rerank: BaseLLMModelConfigResponse | None = None
    langsmith: LangSmithSetupResponse | None = None

    @classmethod
    def from_db_model(cls, db_config: LLMConfigurationInDB) -> "LLMConfigurationResponse":
        """
        Transforms a LLMConfigurationInDB object into an LLMConfigurationResponse object,
        unwrapping all SecretStr values into plain strings.
        """
        # 1. Unwrap SecretStr to plain str using .get_secret_value()
        #    If the secret value is an empty string, we'll convert it to None for clarity.
        openai_key = db_config.openai_api_key.get_secret_value()
        google_key = db_config.google_api_key.get_secret_value()

        # 2. Transform the list of AzureLLMConfig to AzureLLMConfigResponse
        azure_configs = (
            [
                AzureLLMConfigResponse(
                    **{
                        **az.model_dump(),
                        "api_key": az.api_key.get_secret_value(),
                    },
                )
                for az in db_config.azure_openai
            ]
            if db_config.azure_openai
            else None
        )

        schema_discovery = BaseLLMModelConfigResponse(
            **{
                **db_config.schema_discovery.model_dump(),
                "api_key": db_config.schema_discovery.api_key.get_secret_value(),
            },
        )
        extraction = BaseLLMModelConfigResponse(
            **{
                **db_config.extraction.model_dump(),
                "api_key": db_config.extraction.api_key.get_secret_value(),
            },
        )
        embedding = BaseLLMModelConfigResponse(
            **{
                **db_config.embedding.model_dump(),
                "api_key": db_config.embedding.api_key.get_secret_value(),
            },
        )
        rerank = BaseLLMModelConfigResponse(
            **{
                **db_config.rerank.model_dump(),
                "api_key": db_config.rerank.api_key.get_secret_value(),
            },
        )
        langsmith = LangSmithSetupResponse(
            **{
                **db_config.langsmith.model_dump(),
                "api_key": db_config.langsmith.api_key.get_secret_value(),
            },
        )
        # 3. Create the final response object, passing the unwrapped values.
        #    An empty string for a key becomes None in the final response.
        return cls(
            openai_api_key=openai_key or "",
            google_api_key=google_key or "",
            azure_openai=azure_configs,
            schema_discovery=schema_discovery,
            extraction=extraction,
            embedding=embedding,
            rerank=rerank,
            langsmith=langsmith,
        )
