from datetime import datetime, timedelta

from models.api_audit_log import APIAuditLog
from models.token import Token
from schemas.audit import APIAuditLogCreate, APIAuditLogInDB
from utils.constants import TIMEZONE
from utils.logger.custom_logging import LoggerMixin


class AuditHelper(LoggerMixin):
    """Helper for handling audit log operations."""

    async def log_api_call(self, audit_data: APIAuditLogCreate) -> bool:
        """Log API call to audit database."""
        try:
            # Convert to DB schema
            audit_log_db = APIAuditLogInDB(**audit_data.model_dump())

            # Create model instance
            audit_log = APIAuditLog(**audit_log_db.model_dump())

            # Save to database
            await audit_log.insert()

            # Update token last_used_at if token auth
            if audit_data.token_id:
                await self._update_token_last_used(audit_data.token_id)

        except Exception:
            self.logger.exception(
                'event=audit-log-save-failed message="Failed to save audit log"',
            )
            return False
        return True

    async def _update_token_last_used(self, token_id: str) -> None:
        """Update token's last_used_at timestamp."""
        try:
            token = await Token.get(token_id)
            if token:
                token.last_used_at = datetime.now(TIMEZONE)
                await token.save()
        except Exception:
            self.logger.exception(
                "event=token-last-used-update-failed token_id=%s",
                token_id,
            )

    async def get_user_activities(self, user_id: str, limit: int = 50) -> list[APIAuditLog]:
        """Get recent activities for a user."""
        try:
            return (
                await APIAuditLog.find(
                    APIAuditLog.user_id == user_id,
                )
                .sort([("timestamp", -1)])
                .limit(limit)
                .to_list()
            )
        except Exception:
            self.logger.exception(
                'event=get-user-activities-failed user_id=%s message="Failed to get user activities"',
                user_id,
            )
            return []

    async def get_token_usage_details(self, token_id: str, limit: int = 50) -> list[APIAuditLog]:
        """Get detailed usage statistics for a token."""
        try:
            return (
                await APIAuditLog.find(
                    APIAuditLog.token_id == token_id,
                )
                .sort([("timestamp", -1)])
                .limit(limit)
                .to_list()
            )
        except Exception:
            self.logger.exception(
                'event=get-token-usage-failed token_id=%s message="Failed to get token usage"',
                token_id,
            )
            return []

    async def get_suspicious_activities(self, hours: int = 24, limit: int = 100) -> list[APIAuditLog]:
        """Get suspicious activities within time window."""
        try:
            since = datetime.now(TIMEZONE) - timedelta(hours=hours)

            return (
                await APIAuditLog.find(
                    APIAuditLog.is_suspicious == True,  # noqa: E712
                    APIAuditLog.timestamp >= since,
                )
                .sort([("timestamp", -1)])
                .limit(limit)
                .to_list()
            )
        except Exception:
            self.logger.exception(
                'event=get-suspicious-activities-failed message="Failed to get suspicious activities"',
            )
            return []

    async def get_failed_login_attempts(self, hours: int = 24) -> list[dict]:
        """Get failed authentication attempts grouped by IP."""
        try:
            since = datetime.now(TIMEZONE) - timedelta(hours=hours)

            pipeline = [
                {
                    "$match": {
                        "auth_type": "INVALID",
                        "timestamp": {"$gte": since},
                    },
                },
                {
                    "$group": {
                        "_id": "$ip_address",
                        "count": {"$sum": 1},
                        "latest": {"$max": "$timestamp"},
                        "endpoints": {"$addToSet": "$endpoint"},
                    },
                },
                {"$sort": {"count": -1}},
                {"$limit": 50},
            ]

            return await APIAuditLog.aggregate(pipeline).to_list()
        except Exception:
            self.logger.exception(
                'event=get-failed-attempts-failed message="Failed to get failed login attempts"',
            )
            return []

    async def get_dashboard_statistics(self) -> dict:
        """Get dashboard statistics for system monitoring."""
        try:
            now = datetime.now(TIMEZONE)
            today = now - timedelta(hours=24)

            # Total requests today
            total_requests = await APIAuditLog.find(
                APIAuditLog.timestamp >= today,
            ).count()

            # Unique users today
            unique_users_pipeline = [
                {"$match": {"timestamp": {"$gte": today}, "user_id": {"$ne": None}}},
                {"$group": {"_id": "$user_id"}},
                {"$count": "unique_users"},
            ]
            unique_users_result = await APIAuditLog.aggregate(unique_users_pipeline).to_list()
            unique_users = unique_users_result[0]["unique_users"] if unique_users_result else 0

            # Error rate
            error_requests = await APIAuditLog.find(
                APIAuditLog.timestamp >= today,
                APIAuditLog.status_code >= 400,
            ).count()
            error_rate = error_requests / total_requests if total_requests > 0 else 0

            # Suspicious activities
            suspicious_count = await APIAuditLog.find(
                APIAuditLog.timestamp >= today,
                APIAuditLog.is_suspicious == True,  # noqa: E712
            ).count()

            # Top endpoints
            top_endpoints_pipeline = [
                {"$match": {"timestamp": {"$gte": today}}},
                {
                    "$group": {
                        "_id": {"endpoint": "$endpoint", "method": "$method"},
                        "count": {"$sum": 1},
                    },
                },
                {"$sort": {"count": -1}},
                {"$limit": 10},
                {
                    "$project": {
                        "endpoint": "$_id.endpoint",
                        "method": "$_id.method",
                        "count": 1,
                        "_id": 0,
                    },
                },
            ]
            top_endpoints = await APIAuditLog.aggregate(top_endpoints_pipeline).to_list()

            return {
                "total_requests_today": total_requests,
                "unique_users_today": unique_users,
                "error_rate": round(error_rate, 3),
                "suspicious_activities": suspicious_count,
                "top_endpoints": top_endpoints,
            }

        except Exception:
            self.logger.exception(
                'event=get-dashboard-stats-failed message="Failed to get dashboard statistics"',
            )
            return {
                "total_requests_today": 0,
                "unique_users_today": 0,
                "error_rate": 0,
                "suspicious_activities": 0,
                "top_endpoints": [],
            }
