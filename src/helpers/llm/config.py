from config import settings
from utils.enums import AzureOpenAI, GoogleAIModels, ModelType, OpenAIModels

GOOGLE_API_KEY = settings.GOOGLE_API_KEY
OPENAI_API_KEY = settings.OPENAI_API_KEY
AZURE_OPENAI_API_KEY = settings.AZURE_OPENAI_API_KEY
AZURE_OPENAI_ENDPOINT = settings.AZURE_OPENAI_ENDPOINT
AZURE_OPENAI_GPT4O_DEPLOYMENT_NAME = settings.AZURE_OPENAI_GPT4O_DEPLOYMENT_NAME
AZURE_OPENAI_GPT4O_MINI_DEPLOYMENT_NAME = settings.AZURE_OPENAI_GPT4O_MINI_DEPLOYMENT_NAME
AZURE_LLM_API_VERSION = settings.AZURE_LLM_API_VERSION


MODEL_LIST = [
    # OpenAI
    {
        "model_name": ModelType.OPENAI_GPT_5,
        "multimodal": True,
        "thinking": True,
        "chat_llm": True,
        "embedding": False,
        "rerank": False,
        "open_source": False,
        "max_input_tokens": 272000,
        "litellm_params": {
            "model": f"openai/{OpenAIModels.GPT_5.value}",
            "api_key": OPENAI_API_KEY.get_secret_value() if OPENAI_API_KEY is not None else None,
        },
    },
    {
        "model_name": ModelType.OPENAI_GPT_5_MINI,
        "multimodal": True,
        "thinking": True,
        "chat_llm": True,
        "embedding": False,
        "rerank": False,
        "open_source": False,
        "max_input_tokens": 272000,
        "litellm_params": {
            "model": f"openai/{OpenAIModels.GPT_5_MINI.value}",
            "api_key": OPENAI_API_KEY.get_secret_value() if OPENAI_API_KEY is not None else None,
        },
    },
    {
        "model_name": ModelType.OPENAI_GPT_5_NANO,
        "multimodal": True,
        "thinking": True,
        "chat_llm": True,
        "embedding": False,
        "rerank": False,
        "open_source": False,
        "max_input_tokens": 272000,
        "litellm_params": {
            "model": f"openai/{OpenAIModels.GPT_5_NANO.value}",
            "api_key": OPENAI_API_KEY.get_secret_value() if OPENAI_API_KEY is not None else None,
        },
    },
    {
        "model_name": ModelType.OPENAI_GPT_4O_MINI,
        "multimodal": True,
        "thinking": False,
        "chat_llm": True,
        "embedding": False,
        "rerank": False,
        "open_source": False,
        "max_input_tokens": 100000,
        "litellm_params": {
            "model": f"openai/{OpenAIModels.GPT_4O_MINI.value}",
            "api_key": OPENAI_API_KEY.get_secret_value() if OPENAI_API_KEY is not None else None,
        },
    },
    {
        "model_name": ModelType.OPENAI_GPT_4O,
        "multimodal": True,
        "thinking": False,
        "chat_llm": True,
        "embedding": False,
        "rerank": False,
        "open_source": False,
        "max_input_tokens": 111616,
        "litellm_params": {
            "model": f"openai/{OpenAIModels.GPT_4O.value}",
            "api_key": OPENAI_API_KEY.get_secret_value() if OPENAI_API_KEY is not None else None,
        },
    },
    {
        "model_name": ModelType.OPENAI_GPT_4_1_MINI,
        "multimodal": True,
        "thinking": False,
        "chat_llm": True,
        "embedding": False,
        "rerank": False,
        "open_source": False,
        "max_input_tokens": 1014808,
        "litellm_params": {
            "model": f"openai/{OpenAIModels.GPT_4_1_MINI.value}",
            "api_key": OPENAI_API_KEY.get_secret_value() if OPENAI_API_KEY is not None else None,
        },
    },
    {
        "model_name": ModelType.OPENAI_GPT_4_1,
        "multimodal": True,
        "thinking": False,
        "chat_llm": True,
        "embedding": False,
        "rerank": False,
        "open_source": False,
        "max_input_tokens": 1014808,
        "litellm_params": {
            "model": f"openai/{OpenAIModels.GPT_4_1.value}",
            "api_key": OPENAI_API_KEY.get_secret_value() if OPENAI_API_KEY is not None else None,
        },
    },
    {
        "model_name": ModelType.OPENAI_O_1,
        "multimodal": True,
        "thinking": True,
        "chat_llm": True,
        "embedding": False,
        "rerank": False,
        "open_source": False,
        "max_input_tokens": 100000,
        "litellm_params": {
            "model": f"openai/{OpenAIModels.OPENAI_O_1.value}",
            "api_key": OPENAI_API_KEY.get_secret_value() if OPENAI_API_KEY is not None else None,
        },
    },
    {
        "model_name": ModelType.OPENAI_O_3,
        "multimodal": True,
        "thinking": True,
        "chat_llm": True,
        "embedding": False,
        "rerank": False,
        "open_source": False,
        "max_input_tokens": 100000,
        "litellm_params": {
            "model": f"openai/{OpenAIModels.OPENAI_O_3.value}",
            "api_key": OPENAI_API_KEY.get_secret_value() if OPENAI_API_KEY is not None else None,
        },
    },
    {
        "model_name": ModelType.OPENAI_O_1_MINI,
        "multimodal": True,
        "thinking": True,
        "chat_llm": True,
        "embedding": False,
        "rerank": False,
        "open_source": False,
        "max_input_tokens": 62464,
        "litellm_params": {
            "model": f"openai/{OpenAIModels.OPENAI_O_1_MINI.value}",
            "api_key": OPENAI_API_KEY.get_secret_value() if OPENAI_API_KEY is not None else None,
        },
    },
    {
        "model_name": ModelType.OPENAI_O_3_MINI,
        "multimodal": True,
        "thinking": True,
        "chat_llm": True,
        "embedding": False,
        "rerank": False,
        "open_source": False,
        "max_input_tokens": 100000,
        "litellm_params": {
            "model": f"openai/{OpenAIModels.OPENAI_O_3_MINI.value}",
            "api_key": OPENAI_API_KEY.get_secret_value() if OPENAI_API_KEY is not None else None,
        },
    },
    {
        "model_name": ModelType.OPENAI_O_4_MINI,
        "multimodal": True,
        "thinking": True,
        "chat_llm": True,
        "embedding": False,
        "rerank": False,
        "open_source": False,
        "max_input_tokens": 100000,
        "litellm_params": {
            "model": f"openai/{OpenAIModels.OPENAI_O_4_MINI.value}",
            "api_key": OPENAI_API_KEY.get_secret_value() if OPENAI_API_KEY is not None else None,
        },
    },
    {
        "model_name": ModelType.OPENAI_GPT_3_5_TURBO,
        "multimodal": False,
        "thinking": False,
        "chat_llm": True,
        "embedding": False,
        "rerank": True,
        "open_source": False,
        "max_input_tokens": 12289,
        "litellm_params": {
            "model": f"openai/{OpenAIModels.GPT_3_5_TURBO.value}",
            "api_key": OPENAI_API_KEY.get_secret_value() if OPENAI_API_KEY is not None else None,
        },
    },
    # Azure OpenAI
    {
        "model_name": ModelType.AZURE_OPENAI_GPT_4O_MINI,
        "embedding": False,
        "rerank": True,
        "chat_llm": True,
        "multimodal": True,
        "thinking": False,
        "open_source": False,
        "max_input_tokens": 100000,
        "litellm_params": {
            "model": f"azure-openai/{AzureOpenAI.GPT_4O_MINI.value}",
            "api_key": AZURE_OPENAI_API_KEY.get_secret_value() if AZURE_OPENAI_API_KEY is not None else None,
            "endpoint": str(AZURE_OPENAI_ENDPOINT),
            "deployment_name": AZURE_OPENAI_GPT4O_MINI_DEPLOYMENT_NAME,
            "api_version": AZURE_LLM_API_VERSION,
        },
    },
    {
        "model_name": ModelType.AZURE_OPENAI_GPT_4O,
        "embedding": False,
        "rerank": True,
        "chat_llm": True,
        "multimodal": True,
        "thinking": False,
        "open_source": False,
        "max_input_tokens": 111616,
        "litellm_params": {
            "model": f"azure-openai/{AzureOpenAI.GPT_4O.value}",
            "api_key": AZURE_OPENAI_API_KEY.get_secret_value() if AZURE_OPENAI_API_KEY is not None else None,
            "endpoint": str(AZURE_OPENAI_ENDPOINT),
            "deployment_name": AZURE_OPENAI_GPT4O_DEPLOYMENT_NAME,
            "api_version": AZURE_LLM_API_VERSION,
        },
    },
    {
        "model_name": ModelType.AZURE_OPENAI_GPT_3_5_TURBO,
        "multimodal": False,
        "thinking": False,
        "chat_llm": True,
        "embedding": False,
        "rerank": True,
        "open_source": False,
        "max_input_tokens": 12289,
        "litellm_params": {
            "model": f"azure-openai/{AzureOpenAI.GPT_3_5_TURBO.value}",
            "api_key": AZURE_OPENAI_API_KEY.get_secret_value() if AZURE_OPENAI_API_KEY is not None else None,
            "endpoint": str(AZURE_OPENAI_ENDPOINT),
            "deployment_name": AZURE_OPENAI_GPT4O_MINI_DEPLOYMENT_NAME,
            "api_version": AZURE_LLM_API_VERSION,
        },
    },
    # Gemini
    {
        "model_name": ModelType.GEMINI_2_5_PRO,
        "embedding": False,
        "rerank": True,
        "chat_llm": True,
        "multimodal": True,
        "thinking": True,
        "open_source": False,
        "max_input_tokens": 1048576,
        "litellm_params": {
            "model": f"googleai/{GoogleAIModels.GEMINI_2_5_PRO.value}",
            "api_key": GOOGLE_API_KEY.get_secret_value() if GOOGLE_API_KEY is not None else None,
        },
    },
    {
        "model_name": ModelType.GEMINI_2_5_FLASH,
        "embedding": False,
        "rerank": True,
        "chat_llm": True,
        "multimodal": True,
        "thinking": True,
        "open_source": False,
        "max_input_tokens": 1048576,
        "litellm_params": {
            "model": f"googleai/{GoogleAIModels.GEMINI_2_5_FLASH.value}",
            "api_key": GOOGLE_API_KEY.get_secret_value() if GOOGLE_API_KEY is not None else None,
        },
    },
    {
        "model_name": ModelType.GEMINI_2_5_FLASH_LITE,
        "embedding": False,
        "rerank": True,
        "chat_llm": True,
        "multimodal": True,
        "thinking": True,
        "open_source": False,
        "max_input_tokens": 1048576,
        "litellm_params": {
            "model": f"googleai/{GoogleAIModels.GEMINI_2_5_FLASH_LITE.value}",
            "api_key": GOOGLE_API_KEY.get_secret_value() if GOOGLE_API_KEY is not None else None,
        },
    },
    {
        "model_name": ModelType.GEMINI_2_0_FLASH,
        "embedding": False,
        "rerank": True,
        "chat_llm": True,
        "multimodal": True,
        "thinking": False,
        "open_source": False,
        "max_input_tokens": 1048576,
        "litellm_params": {
            "model": f"googleai/{GoogleAIModels.GEMINI_2_0_FLASH.value}",
            "api_key": GOOGLE_API_KEY.get_secret_value() if GOOGLE_API_KEY is not None else None,
        },
    },
    {
        "model_name": ModelType.GEMINI_2_0_FLASH_LITE,
        "embedding": False,
        "rerank": True,
        "chat_llm": True,
        "multimodal": True,
        "thinking": False,
        "open_source": False,
        "max_input_tokens": 1048576,
        "litellm_params": {
            "model": f"googleai/{GoogleAIModels.GEMINI_2_0_FLASH_LITE.value}",
            "api_key": GOOGLE_API_KEY.get_secret_value() if GOOGLE_API_KEY is not None else None,
        },
    },
    # Embedding Models
    {
        "model_name": ModelType.OPENAI_TEXT_EMBEDDING_3_LARGE,
        "embedding": True,
        "rerank": False,
        "chat_llm": False,
        "multimodal": False,
        "thinking": False,
        "open_source": False,
        "litellm_params": {
            "model": f"openai/{OpenAIModels.TEXT_EMBEDDING_3_LARGE.value}",
            "api_key": OPENAI_API_KEY.get_secret_value() if OPENAI_API_KEY is not None else None,
        },
    },
    {
        "model_name": ModelType.OPENAI_TEXT_EMBEDDING_3_SMALL,
        "embedding": True,
        "rerank": False,
        "chat_llm": False,
        "multimodal": False,
        "thinking": False,
        "open_source": False,
        "litellm_params": {
            "model": f"openai/{OpenAIModels.TEXT_EMBEDDING_3_SMALL.value}",
            "api_key": OPENAI_API_KEY.get_secret_value() if OPENAI_API_KEY is not None else None,
        },
    },
    {
        "model_name": ModelType.OPENAI_TEXT_EMBEDDING_ADA_002,
        "embedding": True,
        "rerank": False,
        "chat_llm": False,
        "multimodal": False,
        "thinking": False,
        "open_source": False,
        "litellm_params": {
            "model": f"openai/{OpenAIModels.TEXT_EMBEDDING_ADA_002.value}",
            "api_key": OPENAI_API_KEY.get_secret_value() if OPENAI_API_KEY is not None else None,
        },
    },
    {
        "model_name": ModelType.AZURE_OPENAI_EMBEDDING_ADA_002,
        "embedding": True,
        "rerank": False,
        "chat_llm": False,
        "multimodal": False,
        "thinking": False,
        "open_source": False,
        "litellm_params": {
            "model": f"azure-openai/{AzureOpenAI.EMBEDDING_ADA_002.value}",
            "api_key": AZURE_OPENAI_API_KEY.get_secret_value() if AZURE_OPENAI_API_KEY is not None else None,
            "endpoint": str(AZURE_OPENAI_ENDPOINT),
            "deployment_name": AZURE_OPENAI_GPT4O_DEPLOYMENT_NAME,
            "api_version": AZURE_LLM_API_VERSION,
        },
    },
    {
        "model_name": ModelType.GEMINI_EMBEDDING_001,
        "embedding": True,
        "rerank": False,
        "chat_llm": False,
        "multimodal": False,
        "thinking": False,
        "open_source": False,
        "litellm_params": {
            "model": f"googleai/{GoogleAIModels.GEMINI_EMBEDDING_001.value}",
            "api_key": GOOGLE_API_KEY.get_secret_value() if GOOGLE_API_KEY is not None else None,
        },
    },
]


ACCEPTED_OPENAI_LLM_MODELS = {
    ModelType.OPENAI_GPT_5,
    ModelType.OPENAI_GPT_5_MINI,
    ModelType.OPENAI_GPT_5_NANO,
    ModelType.OPENAI_GPT_4_1,
    ModelType.OPENAI_GPT_4_1_MINI,
    ModelType.OPENAI_GPT_4O,
    ModelType.OPENAI_GPT_4O_MINI,
    ModelType.OPENAI_O_1,
    ModelType.OPENAI_O_1_MINI,
    ModelType.OPENAI_O_3,
    ModelType.OPENAI_O_3_MINI,
    ModelType.OPENAI_O_4_MINI,
    ModelType.OPENAI_GPT_3_5_TURBO,
}

ACCEPTED_AZURE_OPENAI_MODELS = {
    ModelType.AZURE_OPENAI_GPT_4O_MINI,
    ModelType.AZURE_OPENAI_GPT_4O,
    ModelType.AZURE_OPENAI_GPT_O_1,
    ModelType.AZURE_OPENAI_GPT_O_3,
    ModelType.AZURE_OPENAI_GPT_O_3_MINI,
    ModelType.AZURE_OPENAI_GPT_O_1_MINI,
    ModelType.AZURE_OPENAI_GPT_O_4_MINI,
    ModelType.AZURE_OPENAI_GPT_3_5_TURBO,
}

ACCEPTED_GOOGLE_AI_MODELS = {
    ModelType.GEMINI_2_5_PRO,
    ModelType.GEMINI_2_5_FLASH,
    ModelType.GEMINI_2_5_FLASH_LITE,
    ModelType.GEMINI_2_0_FLASH,
    ModelType.GEMINI_2_0_FLASH_LITE,
}

ACCEPTED_OPENAI_EMBEDDING_MODELS = {
    ModelType.OPENAI_TEXT_EMBEDDING_3_LARGE,
    ModelType.OPENAI_TEXT_EMBEDDING_3_SMALL,
    ModelType.OPENAI_TEXT_EMBEDDING_ADA_002,
}

ACCEPTED_OPENAI_RERANK_MODELS = {
    OpenAIModels.GPT_3_5_TURBO,
}

ACCEPTED_AZURE_OPENAI_EMBEDDING_MODELS = {
    ModelType.AZURE_OPENAI_EMBEDDING_ADA_002,
}

ACCEPTED_AZURE_OPENAI_RERANK_MODELS = {
    ModelType.AZURE_OPENAI_GPT_3_5_TURBO,
}

ACCEPTED_GOOGLE_AI_EMBEDDING_MODELS = {
    ModelType.GEMINI_EMBEDDING_001,
}
