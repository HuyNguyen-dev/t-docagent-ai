import os
from typing import Any

import google.auth.exceptions
import openai
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_openai import AzureOpenAIEmbeddings, OpenAIEmbeddings

from helpers.llm.config import ModelType
from utils.enums import LLMProvider
from utils.functions import decrypt_and_migrate
from utils.llm import filter_models
from utils.logger.custom_logging import LoggerMixin

EmbeddingTypes = OpenAIEmbeddings | AzureOpenAIEmbeddings | GoogleGenerativeAIEmbeddings


class EmbeddingService(LoggerMixin):
    """
    Usage:
    embedding = EmbeddingService(
        emb=ModelType.OPENAI_EMBEDDING
    ).create_embedding()
    """

    def __init__(
        self,
        emb: str | None = ModelType.OPENAI_TEXT_EMBEDDING_3_LARGE,
    ) -> None:
        self.emb = emb
        super().__init__()

    def create_embedding(
        self,
        **kwargs: dict[str, Any],
    ) -> EmbeddingTypes | None:
        return self.select(**kwargs)

    def select(
        self,
        is_default: bool = True,
        **kwargs: dict[str, Any],
    ) -> EmbeddingTypes | None:
        provider = kwargs.get("provider") if not is_default else None
        api_key = ""
        if is_default:
            model_list = filter_models(self.emb)
            if not model_list:
                return None

            model_config = model_list[0]
            params = model_config["litellm_params"]
            model = params["model"]

            splited = model.split("/", 1)
            model_provider, model_name = splited[0], splited[-1]

            api_key = params.get("api_key")
            endpoint = params.get("endpoint")
            deployment_name = params.get("deployment_name")
            api_version = params.get("api_version")
        else:
            model_provider = kwargs.pop("provider")
            model_name = None
            if provider != LLMProvider.AZURE_OPENAI:
                model_list = filter_models(model_name or self.emb)
                if not model_list:
                    return None

                model_config = model_list[0]
                params = model_config["litellm_params"]
                model = params["model"]
                api_key = params.get("api_key", "")

                splited = model.split("/", 1)
                model_name = splited[-1]
            else:
                model_name = kwargs.pop("model_name", None)

            api_key = kwargs.pop("api_key", "") or api_key
            endpoint = kwargs.pop("endpoint", None)
            deployment_name = kwargs.pop("deployment_name", None)
            api_version = kwargs.pop("api_version", None)
            if os.environ.get("ENV_STATE") != "dev":
                api_key = decrypt_and_migrate(api_key)

        try:
            if model_provider.startswith("openai"):
                model_settings = {
                    "model": model_name,
                    "api_key": api_key,
                }
                return OpenAIEmbeddings(**model_settings)

            if model_provider.startswith("azure-openai"):
                model_settings = {
                    "model": model_name,
                    "azure_deployment": deployment_name,
                    "api_key": api_key,
                    "azure_endpoint": endpoint,
                    "api_version": api_version,
                }
                return AzureOpenAIEmbeddings(**model_settings)

            if model_provider.startswith("googleai"):
                model_settings = {
                    "model": model_name,
                    "api_key": api_key,
                }
                model_settings.update(kwargs)
                return GoogleGenerativeAIEmbeddings(**model_settings)

        except openai.APIConnectionError:
            self.logger.exception(
                'event=init-embedding-instance-failed message="API Connection Error"',
            )
        except (
            openai.AuthenticationError,
            google.auth.exceptions.DefaultCredentialsError,
            openai.OpenAIError,
        ) as e:
            self.logger.exception(
                'event=init-embedding-instance-failed message="Authentication/Configuration error: %s"',
                type(e).__name__,
            )
        except Exception:
            self.logger.exception(
                'event=init-embedding-instance-failed message="An unexpected error occurred during Embedding testing."',
            )
        return None
