import re
from datetime import datetime

from fastapi import HTTPException, status

from helpers.audit import AuditHelper
from models.api_audit_log import APIAuditLog
from schemas.response import Page, PaginatedMetadata
from utils.constants import TIMEZONE
from utils.logger.custom_logging import LoggerMixin


class AuditHandler(LoggerMixin):
    """Handler for audit-related operations."""

    def __init__(self) -> None:
        super().__init__()
        self.audit_helper = AuditHelper()

    async def get_api_activities(
        self,
        q: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        status_code: int | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Page:
        """Get API activities with filtering and pagination."""
        # Build query filters
        query_filters = {}

        if q:
            safe_search_term = re.escape(q)
            query_filters["$or"] = [
                {"user_id": {"$regex": safe_search_term, "$options": "i"}},
                {"token_id": {"$regex": safe_search_term, "$options": "i"}},
                {"endpoint": {"$regex": safe_search_term, "$options": "i"}},
                {"ip_address": {"$regex": safe_search_term, "$options": "i"}},
            ]
        if status_code:
            query_filters["status_code"] = status_code
        if start_date or end_date:
            timestamp_filter = {}
            if start_date:
                timestamp_filter["$gte"] = start_date
            if end_date:
                timestamp_filter["$lte"] = end_date
            if timestamp_filter:
                query_filters["timestamp"] = timestamp_filter

        # Calculate pagination
        skip = (page - 1) * page_size

        # Get total count
        total = await APIAuditLog.find(query_filters).count()

        # Get activities
        activities = await APIAuditLog.find(query_filters).sort([("timestamp", -1)]).skip(skip).limit(page_size).to_list()
        activity_data = [activity.model_dump() for activity in activities]
        total_pages = (total + page_size - 1) // page_size or 1
        return Page(
            items=activity_data,
            metadata=PaginatedMetadata(
                page=min(page, total_pages),
                page_size=page_size,
                total=total,
                total_pages=total_pages,
            ),
        )

    async def get_user_activities(self, user_id: str, limit: int = 50) -> list[dict]:
        """Get activities for a specific user."""
        activities = await self.audit_helper.get_user_activities(user_id, limit)
        return [activity.model_dump() for activity in activities]

    async def get_token_usage_details(self, token_id: str, user_id: str, limit: int = 50) -> list[dict]:
        """Get detailed usage statistics for a token."""
        # Verify token ownership
        from models.token import Token

        token = await Token.get(token_id)
        if not token or token.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Token not found",
            )

        activities = await self.audit_helper.get_token_usage_details(token_id, limit)

        # Convert to TokenUsageEntry format for compatibility
        return [
            {
                "endpoint": activity.endpoint,
                "method": activity.method,
                "timestamp": activity.timestamp,
                "status_code": activity.status_code,
                "ip_address": str(activity.ip_address) if activity.ip_address else None,
            }
            for activity in activities
        ]

    async def get_dashboard_statistics(self) -> dict:
        """Get dashboard statistics for system monitoring."""
        return await self.audit_helper.get_dashboard_statistics()

    async def get_suspicious_activities(self, hours: int = 24, limit: int = 100) -> list[dict]:
        """Get suspicious activities for security monitoring."""
        activities = await self.audit_helper.get_suspicious_activities(hours, limit)

        # Convert to response format
        activity_data = []
        for activity in activities:
            activity_dict = activity.model_dump()
            activity_dict["id"] = str(activity.id)
            if activity.ip_address:
                activity_dict["ip_address"] = str(activity.ip_address)
            activity_data.append(activity_dict)

        return activity_data

    async def get_failed_login_attempts(self, hours: int = 24) -> list[dict]:
        """Get failed authentication attempts grouped by IP."""
        return await self.audit_helper.get_failed_login_attempts(hours)

    async def investigate_user_activity(self, investigation_request: dict) -> dict:
        """Deep dive investigation into user activity patterns."""
        # This is a placeholder for complex investigation logic
        # In a real implementation, this would analyze patterns, correlations, etc.

        user_id = investigation_request.get("user_id")

        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="user_id is required for investigation",
            )

        # Get user activities
        activities = await self.audit_helper.get_user_activities(user_id, 1000)

        # Basic analysis
        analysis = {
            "user_id": user_id,
            "investigation_time": datetime.now(TIMEZONE),
            "total_activities": len(activities),
            "unique_endpoints": len({activity.endpoint for activity in activities}),
            "unique_ips": len({str(activity.ip_address) for activity in activities if activity.ip_address}),
            "error_count": len([a for a in activities if a.status_code >= 400]),
            "suspicious_count": len([a for a in activities if a.is_suspicious]),
            "risk_distribution": {},
            "recent_activities": [],
        }

        # Risk level distribution
        risk_levels = ["low", "medium", "high", "critical"]
        for level in risk_levels:
            analysis["risk_distribution"][level] = len([a for a in activities if a.risk_level == level])

        # Recent activities
        analysis["recent_activities"] = [
            {
                "timestamp": activity.timestamp,
                "endpoint": activity.endpoint,
                "method": activity.method,
                "status_code": activity.status_code,
                "risk_level": activity.risk_level,
                "is_suspicious": activity.is_suspicious,
            }
            for activity in activities[:20]  # Last 20 activities
        ]
        return analysis
