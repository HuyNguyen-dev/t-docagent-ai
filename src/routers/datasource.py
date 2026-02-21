from fastapi import APIRouter, Depends, Response, status

from helpers.jwt_auth import require_scopes_cached
from initializer import data_source_handler
from schemas.datasource import (
    DataSourceConfig,
    DatasourceTestRequest,
)
from schemas.response import BasicResponse
from utils.enums import APIScope

router = APIRouter(prefix="/datasource", dependencies=[])


@router.post(
    "",
    dependencies=[
        Depends(require_scopes_cached(APIScope.DATASOURCE_ADMIN)),
    ],
)
async def create(
    response: Response,
    ds_config: DataSourceConfig,
) -> BasicResponse:
    """
    Create a new data source connection.

    Supports PostgreSQL, MySQL, MongoDB, Elasticsearch, and SQLite.

    **Required Scopes:** `datasource_admin`
    """
    success = await data_source_handler.create(ds_config)

    if not success:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return BasicResponse(
            status="failed",
            message=f"Failed to create {ds_config.ds_type} data source '{ds_config.config.db_name}'.",
            data=None,
        )

    response.status_code = status.HTTP_201_CREATED
    return BasicResponse(
        status="success",
        message=(f"{ds_config.ds_type.title()} data source '{ds_config.config.db_name}' created successfully."),
        data=None,
    )


@router.post(
    "/test",
    dependencies=[
        Depends(require_scopes_cached(APIScope.DATASOURCE_ADMIN)),
    ],
)
async def test(
    response: Response,
    test_request: DatasourceTestRequest,
) -> BasicResponse:
    """
    Test the connection to a data source.

    **Required Scopes:** `datasource_admin`
    """
    success = await data_source_handler.test_connection(test_request.db_name)

    if not success:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return BasicResponse(
            status="failed",
            message=f"Failed to connect to data source '{test_request.db_name}'.",
            data=None,
        )

    response.status_code = status.HTTP_200_OK
    return BasicResponse(
        status="success",
        message=f"Successfully connected to data source '{test_request.db_name}'.",
        data=None,
    )


@router.get(
    "",
    dependencies=[
        Depends(require_scopes_cached(APIScope.DATASOURCE_ADMIN)),
    ],
)
async def list_datasources(
    response: Response,
) -> BasicResponse:
    """
    List all available data sources.

    **Required Scopes:** `datasource_admin`
    """
    datasources = await data_source_handler.list_all()

    if datasources is None:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return BasicResponse(
            status="failed",
            message="Failed to retrieve data source list.",
            data=None,
        )

    if not datasources:
        response.status_code = status.HTTP_200_OK
        return BasicResponse(
            status="success",
            message="No data sources found.",
            data={"datasources": []},
        )

    response.status_code = status.HTTP_200_OK
    return BasicResponse(
        status="success",
        message=f"Found {len(datasources)} data source(s).",
        data={"datasources": datasources},
    )


@router.get(
    "/{db_name}/tables",
    dependencies=[
        Depends(require_scopes_cached(APIScope.DATASOURCE_ADMIN)),
    ],
)
async def get_tables(
    response: Response,
    db_name: str,
) -> BasicResponse:
    """
    Get list of tables from a data source.

    **Required Scopes:** `datasource_admin`
    """
    tables = await data_source_handler.get_tables(db_name)

    if tables is None:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return BasicResponse(
            status="failed",
            message=f"Failed to retrieve tables from data source '{db_name}'.",
            data=None,
        )

    if not tables:
        response.status_code = status.HTTP_200_OK
        return BasicResponse(
            status="success",
            message=f"No tables found in data source '{db_name}'.",
            data={"tables": []},
        )

    response.status_code = status.HTTP_200_OK
    return BasicResponse(
        status="success",
        message=f"Found {len(tables)} table(s) in data source '{db_name}'.",
        data={"tables": tables},
    )
