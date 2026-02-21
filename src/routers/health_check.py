from fastapi import status
from fastapi.responses import ORJSONResponse
from fastapi.routing import APIRouter

from config import default_configs

router = APIRouter()
api_config = default_configs.get("API", {})


@router.get(
    "/health",
    responses={
        200: {
            "description": api_config.get("API_DESCRIPTION"),
            "content": {"application/json": {"example": {"REVISION": "0.0.1"}}},
        },
    },
)
def health_check() -> ORJSONResponse:
    """
    Perform a health check of the API.

    Returns the API revision, name, and description.

    **Required Scopes:** `system_health`
    """
    content = {
        "REVISION": api_config.get("API_VERSION"),
        "NAME": api_config.get("API_NAME"),
        "DESCRIPTION": api_config.get("API_DESCRIPTION"),
    }
    return ORJSONResponse(content=content, status_code=status.HTTP_200_OK)
