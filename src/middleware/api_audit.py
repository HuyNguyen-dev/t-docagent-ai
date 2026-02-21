import asyncio
import contextlib
import time
from collections.abc import Callable
from uuid import uuid4

from fastapi import HTTPException, Request, Response
from fastapi.responses import ORJSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from config import settings
from helpers.audit import AuditHelper
from initializer import logger_instance
from schemas.audit import APIAuditLogCreate
from utils.constants import SKIP_EXTENSIONS, SKIP_PATHS


class APIAuditMiddleware(BaseHTTPMiddleware):
    """
    Middleware to capture and log all API requests for audit purposes.

    Features:
    - Captures all HTTP requests/responses
    - Extracts authentication context (user/token) and caches it
    - Measures processing time
    - Logs to audit database asynchronously
    - Risk assessment and suspicious activity detection
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self.audit_helper = AuditHelper()
        self.logger = logger_instance.get_logger(__name__)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Main middleware logic."""

        # Capture request details
        request_details = self._capture_request_details(request)
        client_ip = request_details.get("ip_address")

        if client_ip in set(settings.BANNED_IPS):
            # If the IP is banned, return a 403 Forbidden response immediately.
            return ORJSONResponse(
                status_code=403,
                content={"detail": "Forbidden: Access from your IP is not allowed."},
            )

        # Skip audit for excluded paths
        if self._should_skip_audit(request):
            return await call_next(request)

        # Optionally skip audit for GET requests based on config
        if settings.AUDIT_IGNORE_GET_METHODS and request.method.upper() == "GET":
            return await call_next(request)

        # Generate unique request ID
        request_id = str(uuid4())
        request.state.request_id = request_id

        # Capture start time
        start_time = time.time()

        # Extract authentication context and cache in request.state
        auth_context = await self._extract_and_cache_auth_context(request)

        response = None
        error_info = None

        try:
            # Process the request
            response = await call_next(request)

        except HTTPException:
            raise

        except Exception as e:
            # Capture error information
            error_info = {
                "error_code": type(e).__name__,
                "error_message": str(e)[:1000],  # Limit length
            }

            response = ORJSONResponse(
                status_code=500,
                content={
                    "detail": "Internal server error",
                    "request_id": request_id,
                },
            )

            # Log the exception with full context
            self.logger.exception(
                'event=api-request-error request_id=%s method=%s path=%s error_type=%s message="API request failed"',
                request_id,
                request.method,
                request.url.path,
                type(e).__name__,
            )

        finally:
            # Calculate processing time
            processing_time = int((time.time() - start_time) * 1000)

            # Log the audit entry asynchronously (non-blocking)
            background_tasks = set()
            task = asyncio.create_task(
                self._log_audit_entry_async(
                    auth_context=auth_context,
                    request_details=request_details,
                    request_id=request_id,
                    processing_time=processing_time,
                    response=response,
                    error_info=error_info,
                ),
            )
            background_tasks.add(task)
            task.add_done_callback(background_tasks.discard)

        return response

    def _should_skip_audit(self, request: Request) -> bool:
        """Determine if request should be skipped from audit."""
        path = request.url.path.lower()

        # Skip specific paths
        if any(path.startswith(skip_path) for skip_path in SKIP_PATHS):
            return True

        # Skip static files
        if any(path.endswith(ext) for ext in SKIP_EXTENSIONS):
            return True

        # Skip health checks and internal endpoints
        return path in ["/", "/ping", "/status"]

    async def _extract_and_cache_auth_context(self, request: Request) -> dict:
        """Extract authentication context and cache in request.state."""
        try:
            # Import here to avoid circular imports
            from fastapi.security import HTTPAuthorizationCredentials

            from helpers.jwt_auth import _is_jwt_format, get_current_user_from_jwt_or_token
            from utils.auth import expand_scopes, get_user_permissions, validate_access_token

            # Check Authorization header (Bearer token)
            auth_header = request.headers.get("authorization")
            if auth_header and auth_header.startswith("Bearer "):
                token_value = auth_header.split(" ")[1]

                try:
                    credentials = HTTPAuthorizationCredentials(
                        scheme="Bearer",
                        credentials=token_value,
                    )

                    # Database query: Get user and token info
                    user, token_scopes = await get_current_user_from_jwt_or_token(credentials)

                    # Cache user object in request state
                    request.state.cached_user = user
                    request.state.cached_token_info = token_scopes
                    request.state.auth_validated = True

                    # Determine auth type by token format
                    if _is_jwt_format(token_value):
                        # SESSION-based authentication (JWT)
                        user_permissions = await get_user_permissions(user.role)
                        user_scopes = {scope.value for scope in expand_scopes(user_permissions)}
                        request.state.cached_user_scopes = user_scopes
                        return {
                            "auth_type": "SESSION",
                            "user_id": str(user.id),
                            "scopes": list(user_scopes),
                            "user_cached": True,
                        }
                    # TOKEN-based authentication (stored access token)
                    # token_scopes is a set of APIScope, convert to list[str]
                    scopes_list = [s.value if hasattr(s, "value") else str(s) for s in token_scopes]
                    request.state.cached_user_scopes = set(scopes_list)

                    # Get token_id via validate_access_token (trusted path)
                    token_id = None
                    token_data = await validate_access_token(token_value)
                    if token_data:
                        token_id = token_data.get("token_id")

                    return {
                        "auth_type": "TOKEN",
                        "user_id": str(user.id),
                        "token_id": token_id,
                        "scopes": scopes_list,
                        "user_cached": True,
                    }

                except Exception:
                    # Invalid token
                    self.logger.debug(
                        'event=auth-extraction-failed message="Failed to extract auth"',
                    )
                    request.state.auth_validated = False
                    request.state.auth_error = "auth_extraction_failed"
                    return {"auth_type": "INVALID"}

            # No authentication
            request.state.auth_validated = False

        except Exception:
            self.logger.exception(
                'event=auth-context-extraction-error message="Error extracting auth context"',
            )
            request.state.auth_validated = False
            return {"auth_type": "ERROR"}
        return {"auth_type": "NONE"}

    def _capture_request_details(self, request: Request) -> dict:
        """Capture detailed request information."""
        return {
            "endpoint": request.url.path,
            "method": request.method,
            "path_params": dict(request.path_params) if request.path_params else None,
            "query_params": dict(request.query_params) if request.query_params else None,
            "ip_address": self._get_client_ip(request),
            "user_agent": request.headers.get("user-agent"),
            "referer": request.headers.get("referer"),
            "content_type": request.headers.get("content-type"),
            "content_length": request.headers.get("content-length"),
        }

    def _get_client_ip(self, request: Request) -> str | None:
        """Extract real client IP address."""
        # Check X-Forwarded-For header (proxy/load balancer)
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            # Get first IP (original client)
            return forwarded_for.split(",")[0].strip()

        # Check X-Real-IP header
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip.strip()

        # Fall back to direct connection IP
        if hasattr(request, "client") and request.client:
            return request.client.host

        return None

    def _assess_risk_level(self, request_details: dict, auth_context: dict, response: Response) -> str:
        """Assess risk level of the request."""
        risk_score = 0

        # Auth-based risk
        if auth_context["auth_type"] == "NONE":
            risk_score += 1
        elif auth_context["auth_type"] in ["INVALID", "ERROR"]:
            risk_score += 3

        # Status code based risk
        if response and response.status_code >= 400:
            if response.status_code == 401:
                risk_score += 2  # Authentication failure
            elif response.status_code == 403:
                risk_score += 2  # Authorization failure
            elif response.status_code >= 500:
                risk_score += 1  # Server error

        # Endpoint-based risk
        endpoint = request_details["endpoint"]
        high_risk_endpoints = ["/auth/", "/users/", "/tokens/", "/admin/"]
        if any(endpoint.startswith(ep) for ep in high_risk_endpoints):
            risk_score += 1

        # Method-based risk
        if request_details["method"] in ["DELETE", "PUT"]:
            risk_score += 1

        # Map score to level
        if risk_score >= 4:
            return "critical"
        if risk_score >= 3:
            return "high"
        if risk_score >= 2:
            return "medium"
        return "low"

    def _detect_suspicious_activity(self, request_details: dict, auth_context: dict) -> bool:
        """Detect potentially suspicious activity."""
        # Multiple failed auth attempts
        if auth_context["auth_type"] == "INVALID":
            return True

        # Suspicious user agents
        user_agent = request_details.get("user_agent", "")
        if user_agent:
            suspicious_agents = ["curl", "wget", "python", "bot", "crawler", "scanner"]
            if any(agent in user_agent.lower() for agent in suspicious_agents):
                return True

        # Suspicious endpoints
        endpoint = request_details["endpoint"]
        admin_endpoints = ["/admin", "/.env", "/config", "/debug"]
        return bool(any(endpoint.startswith(ep) for ep in admin_endpoints))

    async def _log_audit_entry_async(
        self,
        auth_context: dict,
        request_details: dict,
        request_id: str,
        processing_time: int,
        response: Response | None,
        error_info: dict | None,
    ) -> None:
        """Log the audit entry to database asynchronously."""
        # Only log audit entries for authenticated requests (TOKEN or SESSION)
        auth_type = auth_context.get("auth_type")
        if auth_type not in ["TOKEN", "SESSION"]:
            self.logger.debug(
                'event=audit-log-skipped auth_type=%s request_id=%s message="Skipping audit log for unauthenticated request"',
                auth_type,
                request_id,
            )
            return

        try:
            # Prepare audit data
            audit_data = {
                "request_id": request_id,
                "user_id": auth_context.get("user_id"),
                "token_id": auth_context.get("token_id"),
                "auth_type": auth_context["auth_type"],
                "endpoint": request_details["endpoint"],
                "method": request_details["method"],
                "path_params": request_details["path_params"],
                "query_params": request_details["query_params"],
                "status_code": response.status_code if response else 500,
                "processing_time_ms": processing_time,
                "ip_address": str(request_details["ip_address"]) if request_details["ip_address"] else None,
                "user_agent": request_details["user_agent"],
                "referer": request_details["referer"],
                "scopes_used": auth_context.get("scopes", []),
            }

            # Add response size if available
            if response and hasattr(response, "headers"):
                content_length = response.headers.get("content-length")
                if content_length:
                    with contextlib.suppress(ValueError):
                        audit_data["response_size"] = int(content_length)

            # Add error information
            if error_info:
                audit_data.update(error_info)

            # Assess risk and suspicious activity
            audit_data["risk_level"] = self._assess_risk_level(request_details, auth_context, response)
            audit_data["is_suspicious"] = self._detect_suspicious_activity(request_details, auth_context)

            # Validate and save
            # Note: user_id and token_id can be None/null as per validator

            audit_log = APIAuditLogCreate(**audit_data)
            await self.audit_helper.log_api_call(audit_log)

        except Exception:
            # Don't let audit logging break the main request
            self.logger.exception(
                'event=audit-logging-failed request_id=%s message="Failed to log audit entry"',
                request_id,
            )
