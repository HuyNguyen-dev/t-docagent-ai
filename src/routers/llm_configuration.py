from fastapi import APIRouter, Depends, Response, status

from helpers.jwt_auth import require_scopes_cached
from initializer import di_handler, llm_handler
from schemas.llm_configuration import LLMConfigurationInput, LLMConfigurationTest
from schemas.response import BasicResponse
from utils.enums import APIScope

router = APIRouter(prefix="/llm-configurations")


@router.post(
    "/test",
    status_code=status.HTTP_200_OK,
    dependencies=[
        Depends(require_scopes_cached(APIScope.LLM_ACCESS)),
    ],
)
async def test_llm_configuration(
    response: Response,
    config_test: LLMConfigurationTest,
) -> BasicResponse:
    """
    Test LLM Configuration.

    This endpoint allows for testing the validity of an LLM configuration.

    **Required Scopes:** `llm_access`
    """
    result = await llm_handler.test_llm_configuration(config_test)
    if not result:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return BasicResponse(
            status="failed",
            message="Test LLM configuration failed",
            data=None,
        )
    response.status_code = status.HTTP_200_OK
    return BasicResponse(
        status="success",
        message="LLM configuration test successful.",
        data=True,
    )


@router.put(
    "",
    status_code=status.HTTP_200_OK,
    dependencies=[
        Depends(require_scopes_cached(APIScope.LLM_ACCESS)),
    ],
)
async def update_llm_configuration(
    response: Response,
    config_input: LLMConfigurationInput,
) -> BasicResponse:
    """
    Update LLM Configuration.

    This endpoint allows for updating the LLM configuration.

    **Required Scopes:** `llm_access`
    """
    updated_config = await llm_handler.update_llm_configuration(config_input)
    if not updated_config:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return BasicResponse(
            status="failed",
            message="Failed to update LLM configuration",
            data=None,
        )
    await di_handler.refresh_vision_service()
    return BasicResponse(
        status="success",
        message="LLM configuration updated successfully.",
        data=updated_config.model_dump(),
    )


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    dependencies=[
        Depends(require_scopes_cached(APIScope.LLM_ACCESS)),
    ],
)
async def get_llm_configuration(
    response: Response,
) -> BasicResponse:
    """
    Get LLM Configuration.

    This endpoint retrieves the current LLM configuration.

    **Required Scopes:** `llm_access`
    """
    llm_config = await llm_handler.get_llm_configuration()
    if not llm_config:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return BasicResponse(
            status="failed",
            message="LLM configuration not found.",
            data=None,
        )
    return BasicResponse(
        status="success",
        message="LLM configuration retrieved successfully.",
        data=llm_config.model_dump(),
    )


@router.get(
    "/azure-names",
    status_code=status.HTTP_200_OK,
    dependencies=[
        Depends(require_scopes_cached(APIScope.LLM_ACCESS)),
    ],
)
async def get_azure_config_names(
    response: Response,
) -> BasicResponse:
    """
    Get Azure OpenAI configuration names for the owner.
    """
    names = await llm_handler.get_azure_config_names()
    if names is None:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return BasicResponse(
            status="failed",
            message="Failed to retrieve Azure OpenAI configuration names.",
            data=None,
        )
    return BasicResponse(
        status="success",
        message="Azure OpenAI configuration names retrieved successfully.",
        data=names,
    )
