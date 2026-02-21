from fastapi import APIRouter, Response, status

from config import default_configs
from schemas.response import BasicResponse
from services.license_validator import LicenseValidator

router = APIRouter(prefix="/license")
license_validator = LicenseValidator()
api_config = default_configs.get("API", {})


@router.get("/status")
async def get_license_status() -> BasicResponse:
    """Get current license status and information"""
    validation_result = await license_validator.validate_license()
    license_info = await license_validator.get_license_info(validation_result)
    validation_stats = await license_validator.get_validation_stats(validation_result)

    return BasicResponse(
        status="success",
        data={
            "application_name": api_config["API_NAME"],
            "version": api_config["API_VERSION"],
            "email": api_config["API_EMAIL"],
            **license_info.model_dump(),
            "validation_stats": validation_stats.model_dump(),
        },
        message="License status retrieved successfully",
    )


@router.get("/features")
async def get_license_features() -> BasicResponse:
    """Get list of enabled features"""
    validation_result = await license_validator.validate_license()
    license_info = await license_validator.get_license_info(validation_result)

    if license_info.status != "valid":
        return BasicResponse(
            status="success",
            data={
                "features": [],
                "reason": license_info.reason,
            },
            message="License features retrieved",
        )

    features = license_info.features or []

    return BasicResponse(
        status="success",
        data={
            "features": features,
            "count": len(features),
            "license_tier": license_info.license_tier,
        },
        message="License features retrieved successfully",
    )


@router.get("/validate")
async def validate_license() -> BasicResponse:
    """Validate current license and return detailed results"""
    validation_result = await license_validator.validate_license()

    # Add additional context
    if validation_result.valid:
        expiry_warning = await license_validator.check_expiry_warning(validation_result=validation_result)
        validation_result_dict = validation_result.model_dump()
        validation_result_dict["expiry_warning"] = expiry_warning.model_dump()
    else:
        validation_result_dict = validation_result.model_dump()

    return BasicResponse(
        status="success",
        data=validation_result_dict,
        message="License validation completed",
    )


@router.get("/limits")
async def get_license_limits() -> BasicResponse:
    """Get license usage limits and current status"""
    validation_result = await license_validator.validate_license()
    license_info = await license_validator.get_license_info(validation_result)

    if license_info.status != "valid":
        return BasicResponse(
            status="success",
            data={
                "limits": {},
                "reason": license_info.reason,
            },
            message="License limits retrieved",
        )

    limits = {
        "max_users": license_info.max_users or 0,
        "features": license_info.features or [],
        "license_tier": license_info.license_tier or "unknown",
        "days_remaining": license_info.days_remaining or 0,
        "expiry_date": license_info.expiry_date,
    }

    return BasicResponse(
        status="success",
        data={
            "limits": limits,
            "status": "active",
        },
        message="License limits retrieved successfully",
    )


@router.get("/expiry")
async def get_expiry_info() -> BasicResponse:
    """Get license expiry information and warnings"""
    validation_result = await license_validator.validate_license()
    expiry_warning = await license_validator.check_expiry_warning(validation_result=validation_result)
    license_info = await license_validator.get_license_info(validation_result)

    expiry_info = {
        "status": license_info.status,
        "days_remaining": license_info.days_remaining or 0,
        "expiry_date": license_info.expiry_date,
        "warning": expiry_warning.warning,
        "expired": expiry_warning.expired,
        "warning_threshold": expiry_warning.warning_threshold or 30,
    }

    # Add grace period info if applicable
    if expiry_info["expired"] and expiry_info["days_remaining"] >= -30:  # Within 30 days overdue
        expiry_info["grace_period_active"] = True
        expiry_info["days_overdue"] = abs(expiry_info["days_remaining"])
    else:
        expiry_info["grace_period_active"] = False
        expiry_info["days_overdue"] = 0

    return BasicResponse(
        status="success",
        data=expiry_info,
        message="License expiry information retrieved",
    )


@router.get("/stats")
async def get_license_stats() -> BasicResponse:
    """Get comprehensive license statistics for monitoring"""
    validation_result = await license_validator.validate_license()
    license_info = await license_validator.get_license_info(validation_result)
    validation_stats = await license_validator.get_validation_stats(validation_result)
    expiry_info = await license_validator.check_expiry_warning(validation_result=validation_result)

    stats = {
        "license_info": license_info.model_dump(),
        "validation_stats": validation_stats.model_dump(),
        "expiry_info": expiry_info.model_dump(),
        "timestamp": license_info.last_checked,
        "system_info": {
            "license_key_present": bool(license_validator.license_key is not None),
            "encryption_key_present": bool(license_validator.encryption_key is not None),
            "customer_id_present": bool(license_validator.customer_id is not None),
        },
    }

    return BasicResponse(
        status="success",
        data=stats,
        message="License statistics retrieved successfully",
    )


@router.post("/feature-check")
async def check_feature(feature: str) -> BasicResponse:
    """Check if a specific feature is enabled"""
    validation_result = await license_validator.validate_license()
    is_enabled = await license_validator.is_feature_enabled(feature, validation_result)
    license_info = await license_validator.get_license_info(validation_result)

    return BasicResponse(
        status="success",
        data={
            "feature": feature,
            "enabled": is_enabled,
            "license_status": license_info.status,
        },
        message=f"Feature '{feature}' check completed",
    )


@router.get("/health")
async def license_health_check(response: Response) -> BasicResponse:
    """License-specific health check"""
    validation_result = await license_validator.validate_license()
    license_info = await license_validator.get_license_info(validation_result)

    health_status = {
        "license_present": bool(license_validator.license_key is not None),
        "encryption_key_present": bool(license_validator.encryption_key is not None),
        "customer_id_present": bool(license_validator.customer_id is not None),
        "license_valid": validation_result.valid,
        "license_status": license_info.status,
        "days_remaining": license_info.days_remaining or 0,
        "last_validation": license_info.last_checked,
    }

    # Determine overall health
    if health_status["license_valid"] and health_status["license_present"]:
        overall_status = "healthy"
        response.status_code = status.HTTP_200_OK
    elif health_status["license_present"] and health_status["days_remaining"] > 0:
        overall_status = "warning"
        response.status_code = status.HTTP_200_OK
    else:
        overall_status = "unhealthy"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    health_status["overall_status"] = overall_status

    return BasicResponse(
        status="success",
        data=health_status,
        message=f"License health check: {overall_status}",
    )
