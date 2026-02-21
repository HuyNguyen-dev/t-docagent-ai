import os
from typing import Any

import google.auth.exceptions
import openai
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import AzureChatOpenAI, ChatOpenAI

from helpers.llm.config import ModelType
from utils.constants import DEFAULT_TEMPERATURE
from utils.enums import REASONING_BUDGET, LLMProvider, ReasoningEffort
from utils.functions import decrypt_and_migrate
from utils.llm import filter_models
from utils.logger.custom_logging import LoggerMixin

LLMTypes = ChatOpenAI | AzureChatOpenAI | ChatGoogleGenerativeAI


class LLMService(LoggerMixin):
    """
    Usage:
    llm_low = LLMService(
        llm=ModelType.OPENAI_GPT_4_OMNI,
        include_thoughts=True,
        effort=ReasoningEffort.LOW
    ).create_llm()
    """

    def __init__(
        self,
        llm: str | None = ModelType.GEMINI_2_0_FLASH,
        include_thoughts: bool = False,
        effort: ReasoningEffort = ReasoningEffort.MEDIUM,
    ) -> None:
        self.llm = llm
        self.include_thoughts = include_thoughts
        self.effort = effort
        super().__init__()

    def create_llm(
        self,
        temperature: float = DEFAULT_TEMPERATURE,
        is_default: bool = True,
        **kwargs: dict[str, Any],
    ) -> LLMTypes | None:
        return self.select(temperature, is_default, **kwargs)

    def select(
        self,
        temperature: float = 0.4,
        is_default: bool = True,
        **kwargs: dict[str, Any],
    ) -> LLMTypes | None:
        provider = kwargs.get("provider") if not is_default else None
        api_key = ""
        if is_default:
            model_list = filter_models(self.llm)
            if not model_list:
                return None

            model_config = model_list[0]
            params = model_config["litellm_params"]
            model = params["model"]

            splited = model.split("/", 1)
            model_provider, model_name = splited[0], splited[-1]

            thinking_mode = model_config.get("thinking", False)
            if thinking_mode:
                temperature = 1.0
            thinking = self.include_thoughts and thinking_mode

            api_key = params.get("api_key")
            endpoint = params.get("endpoint")
            deployment_name = params.get("deployment_name")
            api_version = params.get("api_version")
        else:
            model_provider = kwargs.pop("provider")
            model_name = None
            if provider != LLMProvider.AZURE_OPENAI:
                model_list = filter_models(model_name or self.llm)
                if not model_list:
                    return None

                model_config = model_list[0]
                params = model_config["litellm_params"]
                model = params["model"]
                api_key = params.get("api_key", "")

                splited = model.split("/", 1)
                model_name = splited[-1]
                thinking_mode = model_config.get("thinking", False)
                if thinking_mode:
                    temperature = 1.0
                thinking = self.include_thoughts and thinking_mode
            else:
                model_name = kwargs.pop("model_name", None)
                thinking = self.include_thoughts

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
                    "temperature": temperature,
                    "streaming": True,
                }
                if thinking:
                    model_settings["reasoning"] = {
                        "effort": self.effort.value,
                        "summary": "auto",
                    }
                return ChatOpenAI(**model_settings)

            if model_provider.startswith("azure-openai"):
                model_settings = {
                    "model": model_name,
                    "azure_deployment": deployment_name,
                    "api_key": api_key,
                    "azure_endpoint": endpoint,
                    "api_version": api_version,
                    "temperature": temperature,
                    "streaming": True,
                }
                if thinking:
                    model_settings["reasoning"] = {
                        "effort": self.effort.value,
                        "summary": "auto",
                    }
                return AzureChatOpenAI(**model_settings)

            if model_provider.startswith("googleai"):
                model_settings = {
                    "model": model_name,
                    "api_key": api_key,
                    "temperature": temperature,
                }
                if thinking:
                    model_settings["thinking_budget"] = REASONING_BUDGET[self.effort]
                    model_settings["include_thoughts"] = True

                model_settings.update(kwargs)
                return ChatGoogleGenerativeAI(**model_settings)
        except openai.APIConnectionError:
            self.logger.exception(
                'event=init-llm-instance-failed message="API Connection Error"',
            )
        except (openai.AuthenticationError, google.auth.exceptions.DefaultCredentialsError, openai.OpenAIError) as e:
            self.logger.exception(
                'event=init-llm-instance-failed message="Authentication/Configuration error: %s"',
                type(e).__name__,
            )
        except Exception:
            self.logger.exception(
                'event=init-llm-instance-failed message="An unexpected error occurred during LLM testing."',
            )
        return None
