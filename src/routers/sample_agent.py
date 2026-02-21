from fastapi import Depends, Query, Response, status
from fastapi.responses import StreamingResponse
from fastapi.routing import APIRouter

from helpers.jwt_auth import require_scopes_cached
from initializer import sample_agent
from schemas.llm import LLMInput, LLMResponse
from utils.enums import APIScope
from utils.llm import ACCEPTED_LLM_MODELS

router = APIRouter(prefix="/sample-agent", dependencies=[Depends(require_scopes_cached(APIScope.AGENT_EXECUTION))])


@router.post("/ainvoke")
async def ainvoke(
    response: Response,
    llm_input: LLMInput,
    model_name: str = Query(
        enum=list(ACCEPTED_LLM_MODELS),
        description="Select Model LLM",
    ),
) -> LLMResponse:
    """
    Invoke the sample agent for LLM completion.

    This endpoint allows for a single invocation of the sample agent with a given prompt and LLM model.

    **Required Scopes:** `agent_execution`
    """
    llm_response = await sample_agent.ainvoke_graph_flow(model_name, llm_input.prompt)
    if llm_response:
        response.status_code = status.HTTP_200_OK
        return LLMResponse(model=model_name, data=llm_response, done=True)

    response.status_code = status.HTTP_400_BAD_REQUEST
    return LLMResponse(model=model_name, data="No response.", done=True)


@router.post("/astream")
async def astream(
    response: Response,
    llm_input: LLMInput,
    model_name: str = Query(
        enum=list(ACCEPTED_LLM_MODELS),
        description="Select Model LLM",
    ),
) -> StreamingResponse:
    """
    Stream LLM completion from the sample agent.

    This endpoint allows for streaming responses from the sample agent for a given prompt and LLM model.

    **Required Scopes:** `agent_execution`
    """
    llm_response = await sample_agent.astream_graph_flow(model_name, llm_input.prompt)
    if llm_response:
        response.status_code = status.HTTP_200_OK
        return llm_response

    response.status_code = status.HTTP_400_BAD_REQUEST
    return response
