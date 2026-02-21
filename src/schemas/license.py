"""
License schemas and models.

This module contains Pydantic models for license-related data structures.
"""

from typing import Any

from pydantic import BaseModel, Field


class LicenseValidationResult(BaseModel):
    """Schema for license validation result."""

    valid: bool = Field(..., description="Whether the license is valid")
    reason: str | None = Field(None, description="Reason for validation result")
    customer_id: str | None = Field(None, description="Customer identifier")
    issued_at: str | None = Field(None, description="License issued date")
    expiry_date: str | None = Field(None, description="License expiry date")
    days_remaining: int | None = Field(None, description="Days remaining until expiry")
    features: list[str] | None = Field(default_factory=list, description="Enabled features")
    license_tier: str | None = Field(None, description="License tier")
    license_id: str | None = Field(None, description="License identifier")
    status: str | None = Field(None, description="License status")

    class Config:
        from_attributes = True


class LicenseInfo(BaseModel):
    """Schema for license information."""

    status: str = Field(..., description="License status (valid/invalid)")
    reason: str | None = Field(None, description="Reason if invalid")
    customer_id: str | None = Field(None, description="Customer identifier")
    license_tier: str | None = Field(None, description="License tier")
    features: list[str] | None = Field(default_factory=list, description="Enabled features")
    days_remaining: int | None = Field(None, description="Days remaining until expiry")
    expiry_date: str | None = Field(None, description="License expiry date")
    last_checked: str = Field(..., description="Last validation timestamp")
    max_users: int | None = Field(None, description="Maximum allowed users")

    class Config:
        from_attributes = True


class ExpiryWarning(BaseModel):
    """Schema for license expiry warning."""

    warning: bool = Field(..., description="Whether expiry warning should be shown")
    expired: bool = Field(..., description="Whether license has expired")
    reason: str | None = Field(None, description="Reason for warning")
    days_remaining: int | None = Field(None, description="Days remaining")
    expiry_date: str | None = Field(None, description="Expiry date")
    warning_threshold: int | None = Field(None, description="Warning threshold in days")
    days_overdue: int | None = Field(None, description="Days overdue if expired")

    class Config:
        from_attributes = True


class ValidationStats(BaseModel):
    """Schema for license validation statistics."""

    license_present: bool = Field(..., description="Whether license key is present")
    encryption_key_present: bool = Field(..., description="Whether encryption key is present")
    customer_id_present: bool = Field(..., description="Whether customer ID is present")
    license_valid: bool = Field(..., description="Whether license is valid")
    customer_id: str | None = Field(None, description="Customer identifier")
    license_tier: str | None = Field(None, description="License tier")
    days_remaining: int = Field(default=0, description="Days remaining")
    features_count: int = Field(default=0, description="Number of enabled features")
    last_validation: str = Field(..., description="Last validation timestamp")
    validation_reason: str = Field(..., description="Validation result reason")

    class Config:
        from_attributes = True


class LicenseFeatures(BaseModel):
    """Schema for license features information."""

    features: list[str] = Field(default_factory=list, description="List of enabled features")
    count: int = Field(default=0, description="Number of features")
    license_tier: str | None = Field(None, description="License tier")
    reason: str | None = Field(None, description="Reason if features unavailable")

    class Config:
        from_attributes = True


class LicenseLimits(BaseModel):
    """Schema for license limits and usage."""

    max_users: int = Field(default=0, description="Maximum allowed users")
    features: list[str] = Field(default_factory=list, description="Enabled features")
    license_tier: str = Field(default="unknown", description="License tier")
    days_remaining: int = Field(default=0, description="Days remaining")
    expiry_date: str | None = Field(None, description="Expiry date")
    status: str = Field(default="inactive", description="License status")
    reason: str | None = Field(None, description="Reason if limits unavailable")

    class Config:
        from_attributes = True


class ExpiryInfo(BaseModel):
    """Schema for license expiry information."""

    status: str = Field(..., description="License status")
    days_remaining: int = Field(default=0, description="Days remaining")
    expiry_date: str | None = Field(None, description="Expiry date")
    warning: bool = Field(default=False, description="Whether expiry warning should be shown")
    expired: bool = Field(default=False, description="Whether license has expired")
    warning_threshold: int = Field(default=30, description="Warning threshold in days")
    grace_period_active: bool = Field(default=False, description="Whether grace period is active")
    days_overdue: int = Field(default=0, description="Days overdue if expired")

    class Config:
        from_attributes = True


class LicenseStats(BaseModel):
    """Schema for comprehensive license statistics."""

    license_info: LicenseInfo = Field(..., description="License information")
    validation_stats: ValidationStats = Field(..., description="Validation statistics")
    expiry_info: ExpiryWarning = Field(..., description="Expiry information")
    timestamp: str = Field(..., description="Statistics timestamp")
    system_info: dict[str, bool] = Field(..., description="System configuration info")

    class Config:
        from_attributes = True


class FeatureCheck(BaseModel):
    """Schema for feature check result."""

    feature: str = Field(..., description="Feature name")
    enabled: bool = Field(..., description="Whether feature is enabled")
    license_status: str = Field(..., description="License status")

    class Config:
        from_attributes = True


class LicenseHealth(BaseModel):
    """Schema for license health check."""

    license_present: bool = Field(..., description="Whether license key is present")
    encryption_key_present: bool = Field(..., description="Whether encryption key is present")
    customer_id_present: bool = Field(..., description="Whether customer ID is present")
    license_valid: bool = Field(..., description="Whether license is valid")
    license_status: str = Field(..., description="License status")
    days_remaining: int = Field(default=0, description="Days remaining")
    last_validation: str | None = Field(None, description="Last validation timestamp")
    overall_status: str = Field(..., description="Overall health status")

    class Config:
        from_attributes = True


class LicenseStatus(BaseModel):
    """Schema for license status response."""

    status: str = Field(..., description="License status")
    data: dict[str, Any] = Field(..., description="License data")
    validation_stats: ValidationStats = Field(..., description="Validation statistics")
    message: str = Field(..., description="Status message")

    class Config:
        from_attributes = True
