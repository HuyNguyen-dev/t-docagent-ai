import time
from collections.abc import Callable

from fastapi import Request, Response, status
from fastapi.responses import ORJSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from config import settings
from schemas.license import LicenseValidationResult
from services.license_validator import LicenseValidator
from utils.logger.custom_logging import LoggerMixin


class LicenseValidationMiddleware(BaseHTTPMiddleware, LoggerMixin):
    """
    Middleware for validating license on each API request

    This middleware:
    1. Intercepts all API requests
    2. Validates the license before processing
    3. Allows or blocks requests based on license status
    4. Logs validation events
    5. Provides grace period handling
    """

    def __init__(self, app: Callable, excluded_paths: list[str] | None = None) -> None:
        super().__init__(app)
        LoggerMixin.__init__(self)

        # Initialize license validator
        self.license_validator = LicenseValidator()

        # Default excluded paths (no license check needed)
        self.excluded_paths = excluded_paths or [
            "/docs",
            "/openapi.json",
            "/redoc",
            "/health",
            "/api/v1/health",
            "/favicon.ico",
        ]

        # Use configuration settings (following existing pattern)
        self.grace_period_days = getattr(settings, "LICENSE_GRACE_PERIOD_DAYS", 30)

        # Rate limiting for failed validations
        self.failed_validation_count = 0
        self.last_failed_validation = 0
        self.rate_limit_window = 300  # 5 minutes
        self.max_failed_attempts = 5

        self.logger.debug(
            'event=middleware-initialized message="LicenseValidationMiddleware initialized successfully"',
        )

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Main middleware dispatch method

        Args:
            request: FastAPI request object
            call_next: Next middleware/route handler

        Returns:
            Response: FastAPI response object
        """

        # Skip license validation for excluded paths
        if self._is_excluded_path(request.url.path):
            return await call_next(request)

        # Start timing for performance monitoring
        start_time = time.time()

        try:
            # Validate license
            validation_result = await self.license_validator.validate_license()

            # Log validation attempt
            await self._log_validation_attempt(request, validation_result)

            # Handle validation result
            if validation_result.valid:
                # License is valid - proceed with request
                return await self._handle_valid_license(request, call_next, validation_result, start_time)

            # License is invalid - handle based on reason
            return await self._handle_invalid_license(request, call_next, validation_result, start_time)

        except Exception as e:
            # Unexpected error during validation
            self.logger.exception(
                'event=middleware-error message="Unexpected error in license validation middleware"',
            )
            return await self._handle_validation_error(request, str(e), start_time)

    def _is_excluded_path(self, path: str) -> bool:
        """Check if the path should be excluded from license validation"""
        return any(excluded in path for excluded in self.excluded_paths)

    async def _handle_valid_license(
        self,
        request: Request,
        call_next: Callable,
        validation_result: LicenseValidationResult,
        start_time: float,
    ) -> Response:
        """Handle valid license - proceed with request"""

        # Check for expiry warning
        expiry_warning = await self.license_validator.check_expiry_warning(validation_result=validation_result)

        # Add license info to request state for downstream handlers
        request.state.license_info = validation_result
        request.state.expiry_warning = expiry_warning

        # Proceed with the request
        response = await call_next(request)

        # Add license headers to response
        response.headers["X-License-Valid"] = "true"
        response.headers["X-License-Tier"] = validation_result.license_tier or "unknown"
        response.headers["X-License-Days-Remaining"] = str(validation_result.days_remaining or 0)

        # Add expiry warning header if needed
        if expiry_warning.warning:
            response.headers["X-License-Expiry-Warning"] = f"{expiry_warning.days_remaining or 0} days remaining"

        # Log successful request
        processing_time = time.time() - start_time
        self.logger.debug(
            'event=request-processed message="Request processed successfully" '
            "path=%s method=%s customer_id=%s processing_time=%.3fs",
            request.url.path,
            request.method,
            validation_result.customer_id,
            processing_time,
        )

        return response

    async def _handle_invalid_license(
        self,
        request: Request,
        validation_result: LicenseValidationResult,
    ) -> Response:
        """Handle invalid license"""

        reason = validation_result.reason or "Unknown"
        customer_id = validation_result.customer_id or "unknown"

        # License is invalid and no grace period
        self.logger.warning(
            'event=license-blocked message="Request blocked due to invalid license" path=%s method=%s customer_id=%s reason=%s',
            request.url.path,
            request.method,
            customer_id,
            reason,
        )

        # Check rate limiting for failed validations
        if self._is_rate_limited():
            return ORJSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": "Too many requests failed license validations",
                    "message": "Please contact support to check the license",
                    "retry_after": self.rate_limit_window,
                },
            )

        # Return license error response
        return ORJSONResponse(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            content={
                "error": "License validation failed",
                "detail": reason,
                "customer_id": customer_id,
                "days_remaining": validation_result.days_remaining or 0,
                "contact_support": True,
            },
        )

    async def _handle_grace_period(
        self,
        request: Request,
        call_next: Callable,
        validation_result: LicenseValidationResult,
        start_time: float,
    ) -> Response:
        """Handle grace period for expired licenses"""

        self.logger.warning(
            'event=grace-period-used message="Grace period used for expired license" '
            "path=%s method=%s customer_id=%s days_overdue=%s",
            request.url.path,
            request.method,
            validation_result.customer_id,
            abs(validation_result.days_remaining or 0),
        )

        # Add grace period info to request state
        request.state.grace_period = True
        request.state.license_info = validation_result

        # Proceed with request but add warning headers
        response = await call_next(request)

        response.headers["X-License-Grace-Period"] = "true"
        response.headers["X-License-Expired"] = "true"
        response.headers["X-License-Days-Overdue"] = str(abs(validation_result.days_remaining or 0))
        response.headers["X-License-Renew-Required"] = "true"

        # Log grace period usage with processing time
        processing_time = time.time() - start_time
        self.logger.debug(
            'event=grace-period-processed message="Grace period request processed" '
            "path=%s method=%s customer_id=%s days_overdue=%s processing_time=%.3fs",
            request.url.path,
            request.method,
            validation_result.customer_id,
            abs(validation_result.days_remaining or 0),
            processing_time,
        )

        return response

    async def _handle_validation_error(
        self,
        request: Request,
        error: str,
        start_time: float,
    ) -> Response:
        """Handle unexpected validation errors"""

        self.logger.error(
            'event=validation-error message="Validation error occurred during request processing" '
            'path=%s method=%s error="%s" processing_time=%.3fs',
            request.url.path,
            request.method,
            error,
            time.time() - start_time,
        )

        return ORJSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "License validation error",
                "message": "An unexpected error occurred during license validation",
                "contact_support": True,
            },
        )

    def _is_grace_period_applicable(self, validation_result: LicenseValidationResult) -> bool:
        """Check if grace period should be applied"""

        if validation_result.valid:
            return False

        reason = validation_result.reason or ""
        if "expired" not in reason.lower():
            return False

        # Check days overdue
        days_remaining = validation_result.days_remaining or 0
        days_overdue = abs(days_remaining) if days_remaining < 0 else 0

        return days_overdue <= self.grace_period_days

    def _is_rate_limited(self) -> bool:
        """Check if we're being rate limited for failed validations"""

        current_time = time.time()

        # Reset counter if window has passed
        if current_time - self.last_failed_validation > self.rate_limit_window:
            self.failed_validation_count = 0

        # Increment counter
        self.failed_validation_count += 1
        self.last_failed_validation = current_time

        return self.failed_validation_count > self.max_failed_attempts

    async def _log_validation_attempt(self, request: Request, validation_result: LicenseValidationResult) -> None:
        """Log license validation attempts"""

        customer_id = validation_result.customer_id or "unknown"
        is_valid = validation_result.valid
        reason = validation_result.reason or "success"

        if is_valid:
            self.logger.debug(
                'event=license-validated message="License validation successful" '
                "customer_id=%s path=%s method=%s days_remaining=%s",
                customer_id,
                request.url.path,
                request.method,
                validation_result.days_remaining or 0,
            )
        else:
            self.logger.warning(
                'event=license-validation-failed message="License validation failed" customer_id=%s path=%s method=%s reason=%s',
                customer_id,
                request.url.path,
                request.method,
                reason,
            )


# Global middleware instance for easy access
license_middleware = LicenseValidationMiddleware(None)
