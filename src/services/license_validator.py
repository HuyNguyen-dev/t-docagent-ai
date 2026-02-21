import base64
import json
from datetime import datetime, timedelta

import httpx
from cryptography.fernet import Fernet

from config import settings
from schemas.license import (
    ExpiryWarning,
    LicenseInfo,
    LicenseValidationResult,
    ValidationStats,
)
from utils.constants import TIMEZONE
from utils.logger.custom_logging import LoggerMixin


class LicenseValidator(LoggerMixin):
    """
    Customer-side license validator supporting both offline and online validation modes.

    Offline mode: Requires LICENSE_KEY, LICENSE_ENCRYPTION_KEY, and CUSTOMER_ID
    Online mode: Requires LICENSE_KEY and VALIDATION_LICENSE_ENDPOINT
    """

    def __init__(self) -> None:
        super().__init__()
        # Store SecretStr objects directly, access secret values only when needed
        self.license_key = settings.LICENSE_KEY
        self.encryption_key = settings.LICENSE_ENCRYPTION_KEY
        self.customer_id = settings.CUSTOMER_ID
        self.validation_endpoint = settings.VALIDATION_LICENSE_ENDPOINT

        if self.encryption_key:
            self.cipher = Fernet(self.encryption_key.get_secret_value().encode())
        else:
            self.cipher = None
            self.logger.warning(
                'event=license-validator-init message="License validator initialized without encryption key" status=disabled',
            )

    async def _validate_license_online(self) -> LicenseValidationResult:
        """
        Validate license online by calling the validation endpoint (async version)

        Returns:
            LicenseValidationResult: Validation result from the online API
        """
        if not self.license_key:
            return LicenseValidationResult(
                valid=False,
                reason="No license key provided",
            )

        if not self.validation_endpoint:
            return LicenseValidationResult(
                valid=False,
                reason="No validation endpoint provided",
            )

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.validation_endpoint,
                    json={"license_key": self.license_key.get_secret_value()},
                    headers={"Content-Type": "application/json"},
                )

                if response.status_code != 200:
                    return LicenseValidationResult(
                        valid=False,
                        reason=f"License validation API returned status {response.status_code}",
                    )

                api_response = response.json()

                # Handle API response structure
                if api_response.get("status") == "success" and api_response.get("data", {}).get("valid"):
                    license_info = api_response["data"]["license_info"]
                    expires_in_days = api_response["data"]["expires_in_days"]

                    self.logger.info(
                        "event=online-license-validated "
                        'message="Online license validation successful" customer_id=%s days_remaining=%s license_tier=%s',
                        license_info["customer_id"],
                        expires_in_days,
                        license_info["license_tier"],
                    )

                    return LicenseValidationResult(
                        valid=True,
                        customer_id=license_info["customer_id"],
                        issued_at=license_info["issued_at"],
                        expiry_date=license_info["expiry_date"],
                        days_remaining=max(0, expires_in_days),
                        features=license_info["features"],
                        license_tier=license_info["license_tier"],
                        reason="License is valid",
                        license_id=license_info.get("license_id"),
                        status=license_info.get("status"),
                    )
                error_message = api_response.get("data", {}).get("error_message") or api_response.get("message", "Unknown error")
                return LicenseValidationResult(
                    valid=False,
                    reason=f"License validation failed: {error_message}",
                )

        except httpx.TimeoutException:
            self.logger.exception(
                'event=online-license-validation-timeout message="Online license validation timed out"',
            )
            return LicenseValidationResult(
                valid=False,
                reason="License validation request timed out",
            )
        except httpx.RequestError as e:
            self.logger.exception('event=online-license-validation-error message="Online license validation request failed"')
            return LicenseValidationResult(
                valid=False,
                reason=f"License validation request failed: {e!s}",
            )

    def _validate_license_offline(self) -> LicenseValidationResult:
        """
        Validate license offline using local encryption/decryption

        Returns:
            LicenseValidationResult: Validation result from offline validation
        """
        # Check if license components are available
        if not self.license_key:
            return LicenseValidationResult(
                valid=False,
                reason="No license key provided",
            )

        if not self.encryption_key:
            return LicenseValidationResult(
                valid=False,
                reason="No encryption key provided",
            )

        if not self.cipher:
            return LicenseValidationResult(
                valid=False,
                reason="License validator not properly initialized",
            )

        try:
            encrypted_payload = base64.urlsafe_b64decode(self.license_key.get_secret_value().encode())
        except Exception as e:
            return LicenseValidationResult(
                valid=False,
                reason=f"Invalid license key format: {e!s}",
            )

        # Decrypt the payload
        try:
            decrypted_payload = self.cipher.decrypt(encrypted_payload)
        except Exception as e:
            return LicenseValidationResult(
                valid=False,
                reason=f"Failed to decrypt license: {e!s}",
            )

        # Parse JSON payload
        try:
            license_data = json.loads(decrypted_payload.decode())
        except Exception as e:
            return LicenseValidationResult(
                valid=False,
                reason=f"Invalid license data format: {e!s}",
            )

        # Validate required fields
        required_fields = ["customer_id", "issued_at", "expiry_days", "features", "license_tier"]
        for field in required_fields:
            if field not in license_data:
                return LicenseValidationResult(
                    valid=False,
                    reason=f"Missing required field: {field}",
                )

        # Validate customer ID match
        if self.customer_id and license_data["customer_id"] != self.customer_id.get_secret_value():
            return LicenseValidationResult(
                valid=False,
                reason=f"License is for different customer: {license_data['customer_id']}",
            )

        # Calculate expiry
        issued_at = datetime.fromisoformat(license_data["issued_at"])
        expiry_date = issued_at.replace(hour=23, minute=59, second=59) + timedelta(days=license_data["expiry_days"] - 1)
        current_time = datetime.now(TIMEZONE)
        days_remaining = (expiry_date - current_time).days

        # Check if expired
        if current_time > expiry_date:
            return LicenseValidationResult(
                valid=False,
                reason="Your license has expired. Please renew your license to continue.",
                expiry_date=expiry_date.isoformat(),
                days_remaining=0,
                customer_id=license_data["customer_id"],
            )

        # License is valid
        self.logger.info(
            "event=offline-license-validated "
            'message="Offline license validation successful" customer_id=%s days_remaining=%s license_tier=%s',
            license_data["customer_id"],
            days_remaining,
            license_data["license_tier"],
        )

        return LicenseValidationResult(
            valid=True,
            customer_id=license_data["customer_id"],
            issued_at=license_data["issued_at"],
            expiry_date=expiry_date.isoformat(),
            days_remaining=max(0, days_remaining),
            features=license_data["features"],
            license_tier=license_data["license_tier"],
            reason="License is valid",
        )

    async def validate_license(self) -> LicenseValidationResult:
        """
        Validate the license key and return validation result.

        Automatically determines validation mode:
        - Offline mode: If LICENSE_KEY, LICENSE_ENCRYPTION_KEY, and CUSTOMER_ID are provided
        - Online mode: If LICENSE_KEY and VALIDATION_LICENSE_ENDPOINT are provided

        Returns:
            LicenseValidationResult: Validation result
        """

        # Check if license key is available
        if not self.license_key:
            return LicenseValidationResult(
                valid=False,
                reason="No license key provided",
            )

        # Determine validation mode based on available configuration
        has_offline_config = self.license_key and self.encryption_key and self.customer_id

        has_online_config = self.license_key and self.validation_endpoint

        if has_offline_config:
            # Use offline validation mode
            self.logger.debug("event=license-validation-mode mode=offline")
            return self._validate_license_offline()
        if has_online_config:
            # Use online validation mode
            self.logger.debug("event=license-validation-mode mode=online")
            return await self._validate_license_online()
        return LicenseValidationResult(
            valid=False,
            reason="Insufficient configuration for license validation. Need either "
            "(LICENSE_KEY + LICENSE_ENCRYPTION_KEY + CUSTOMER_ID) for offline mode "
            "or (LICENSE_KEY + VALIDATION_LICENSE_ENDPOINT) for online mode",
        )

    async def get_license_info(self, validation_result: LicenseValidationResult = None) -> LicenseInfo:
        """
        Get license information without full validation
        Useful for status checks and monitoring
        """
        if validation_result is None:
            validation_result = await self.validate_license()

        if not validation_result.valid:
            return LicenseInfo(
                status="invalid",
                reason=validation_result.reason,
                customer_id=validation_result.customer_id,
                last_checked=datetime.now(TIMEZONE).isoformat(),
            )

        return LicenseInfo(
            status="valid",
            customer_id=validation_result.customer_id,
            license_tier=validation_result.license_tier,
            features=validation_result.features,
            days_remaining=validation_result.days_remaining,
            expiry_date=validation_result.expiry_date,
            last_checked=datetime.now(TIMEZONE).isoformat(),
        )

    async def is_feature_enabled(self, feature: str, validation_result: LicenseValidationResult = None) -> bool:
        """
        Check if a specific feature is enabled in the license

        Args:
            feature: Feature name to check

        Returns:
            bool: True if feature is enabled, False otherwise
        """
        if validation_result is None:
            validation_result = await self.validate_license()

        if not validation_result.valid:
            return False

        features = validation_result.features or []
        return feature in features

    async def get_remaining_users(self, current_users: int, validation_result: LicenseValidationResult = None) -> int:
        """
        Get the number of remaining user slots available

        Args:
            current_users: Current number of active users

        Returns:
            int: Number of remaining user slots (negative if over limit)
        """
        if validation_result is None:
            validation_result = await self.validate_license()

        if not validation_result.valid:
            return 0

        max_users = getattr(validation_result, "max_users", 0) or 0
        return max_users - current_users

    async def check_expiry_warning(
        self,
        warning_days: int = 30,
        validation_result: LicenseValidationResult = None,
    ) -> ExpiryWarning:
        """
        Check if license is approaching expiry

        Args:
            warning_days: Number of days before expiry to show warning

        Returns:
            ExpiryWarning: Warning information
        """
        if validation_result is None:
            validation_result = await self.validate_license()

        if not validation_result.valid:
            return ExpiryWarning(
                warning=False,
                expired=True,
                reason=validation_result.reason,
            )

        days_remaining = validation_result.days_remaining or 0

        if days_remaining <= 0:
            return ExpiryWarning(
                warning=False,
                expired=True,
                days_remaining=days_remaining,
                expiry_date=validation_result.expiry_date,
            )

        if days_remaining <= warning_days:
            return ExpiryWarning(
                warning=True,
                expired=False,
                days_remaining=days_remaining,
                expiry_date=validation_result.expiry_date,
                warning_threshold=warning_days,
            )

        return ExpiryWarning(
            warning=False,
            expired=False,
            days_remaining=days_remaining,
        )

    async def get_validation_stats(self, validation_result: LicenseValidationResult = None) -> ValidationStats:
        """
        Get validation statistics for monitoring

        Returns:
            ValidationStats: Validation statistics
        """
        if validation_result is None:
            validation_result = await self.validate_license()

        return ValidationStats(
            license_present=bool(self.license_key),
            encryption_key_present=bool(self.encryption_key),
            customer_id_present=bool(self.customer_id),
            license_valid=validation_result.valid,
            customer_id=validation_result.customer_id,
            license_tier=validation_result.license_tier,
            days_remaining=validation_result.days_remaining or 0,
            features_count=len(validation_result.features or []),
            last_validation=datetime.now(TIMEZONE).isoformat(),
            validation_reason=validation_result.reason or "No validation performed",
        )
