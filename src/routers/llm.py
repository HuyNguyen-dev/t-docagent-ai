import asyncio
from collections.abc import AsyncGenerator

from fastapi import Depends, Query, Response, status
from fastapi.responses import StreamingResponse
from fastapi.routing import APIRouter

from helpers.jwt_auth import require_scopes_cached
from helpers.llm.chat import LLMService
from helpers.llm.config import (
    ACCEPTED_AZURE_OPENAI_EMBEDDING_MODELS,
    ACCEPTED_AZURE_OPENAI_MODELS,
    ACCEPTED_AZURE_OPENAI_RERANK_MODELS,
    ACCEPTED_GOOGLE_AI_EMBEDDING_MODELS,
    ACCEPTED_GOOGLE_AI_MODELS,
    ACCEPTED_OPENAI_EMBEDDING_MODELS,
    ACCEPTED_OPENAI_LLM_MODELS,
    ACCEPTED_OPENAI_RERANK_MODELS,
)
from schemas.llm import LLMInput, LLMResponse
from schemas.response import BasicResponse
from utils.enums import APIScope, LLMProvider, ModelObjectType
from utils.llm import ACCEPTED_LLM_MODELS

router = APIRouter(prefix="/llm", dependencies=[])
model_type_dict = {
    LLMProvider.OPENAI: {
        ModelObjectType.CHAT_LLM: ACCEPTED_OPENAI_LLM_MODELS,
        ModelObjectType.EMBEDDING: ACCEPTED_OPENAI_EMBEDDING_MODELS,
        ModelObjectType.RERANK: ACCEPTED_OPENAI_RERANK_MODELS,
    },
    LLMProvider.GOOGLE_AI: {
        ModelObjectType.CHAT_LLM: ACCEPTED_GOOGLE_AI_MODELS,
        ModelObjectType.EMBEDDING: ACCEPTED_GOOGLE_AI_EMBEDDING_MODELS,
        ModelObjectType.RERANK: ACCEPTED_GOOGLE_AI_MODELS,
    },
    LLMProvider.AZURE_OPENAI: {
        ModelObjectType.CHAT_LLM: ACCEPTED_AZURE_OPENAI_MODELS,
        ModelObjectType.EMBEDDING: ACCEPTED_AZURE_OPENAI_EMBEDDING_MODELS,
        ModelObjectType.RERANK: ACCEPTED_AZURE_OPENAI_RERANK_MODELS,
    },
}


@router.get(
    "/list-models",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_scopes_cached(APIScope.LLM_ACCESS)),
    ],
)
def list_models(
    response: Response,
    llm_provider: str = Query(
        enum=list(LLMProvider.to_list()),
        description="Select LLM Provider",
    ),
    llm_object: str = Query(
        enum=list(ModelObjectType.to_list()),
        description="Select LLM Object Type",
        default=ModelObjectType.CHAT_LLM,
    ),
) -> BasicResponse:
    """
    List all available LLM models for a given provider.

    **Required Scopes:** `llm_access`
    """
    response.status_code = status.HTTP_200_OK
    data = list(model_type_dict[llm_provider][llm_object])
    return BasicResponse(
        status="success",
        message=f"Get list models {llm_object} of {llm_provider} successfully",
        data=data,
    )


@router.post(
    "/complete",
    response_model=LLMResponse,
    dependencies=[
        Depends(require_scopes_cached(APIScope.API)),
    ],
)
async def complete(
    response: Response,
    llm_input: LLMInput,
    model_name: str = Query(
        enum=list(ACCEPTED_LLM_MODELS),
        description="Select Model LLM",
    ),
) -> LLMResponse:
    """
    Perform LLM completion for a given prompt.

    **Required Scopes:** `api`
    """
    llm = LLMService(llm=model_name).create_llm(temperature=0.2)

    completion_response = await llm.ainvoke(llm_input.prompt)

    if completion_response.content:
        response.status_code = status.HTTP_200_OK
    else:
        response.status_code = status.HTTP_400_BAD_REQUEST
    return LLMResponse(model=model_name, data=completion_response.content, done=True)


@router.post(
    "/complete/astream",
    dependencies=[
        Depends(require_scopes_cached(APIScope.API)),
    ],
)
async def astream_complete(
    llm_input: LLMInput,
    model_name: str = Query(
        enum=list(ACCEPTED_LLM_MODELS),
        description="Select LLM Model",
    ),
) -> StreamingResponse:
    """
    Perform LLM completion with streaming response.

    **Required Scopes:** `api`
    """
    await asyncio.sleep(0)
    llm = LLMService(llm=model_name).create_llm(temperature=0.2)
    completion_gen = llm.astream(llm_input.prompt)

    async def response_generator(completion_gen: any) -> AsyncGenerator:
        async for completion_response in completion_gen:
            if completion_response.content:
                yield (
                    LLMResponse(
                        model=model_name,
                        data=completion_response.content,
                        done=False,
                    ).model_dump_json()
                    + "\n"
                )
        yield (
            LLMResponse(
                model=model_name,
                data="",
                done=True,
            ).model_dump_json()
            + "\n"
        )

    return StreamingResponse(
        response_generator(completion_gen),
        media_type="application/x-ndjson",
    )
