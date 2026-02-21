from datetime import datetime
from typing import AnyStr, ClassVar

from beanie import Document, Indexed
from pydantic import field_serializer
from pymongo import IndexModel

from schemas.audit import APIAuditLogInDB
from settings.mongodb.db_collections import CollectionName


class APIAuditLog(APIAuditLogInDB, Document):
    """
    API audit log model for MongoDB with Pydantic v2 validation.

    Features:
    - Automatic IP address validation with IPvAnyAddress
    - MongoDB schema validation via validators
    - Comprehensive indexing for query performance
    - Pydantic v2 field validators and model validators
    """

    # Indexed fields for efficient queries
    user_id: Indexed(str, sparse=True)
    timestamp: Indexed(datetime)
    endpoint: Indexed(str)
    status_code: Indexed(int)
    auth_type: Indexed(str)
    risk_level: Indexed(str)
    ip_address: Indexed(str, sparse=True)  # Stored as string, validated as IP

    @field_serializer("ip_address")
    def serialize_ip(self, value: AnyStr) -> str | None:
        """Serialize IP address to string for MongoDB."""
        return str(value) if value is not None else None

    class Settings:
        name = CollectionName.API_AUDIT_LOG.value
        indexes: ClassVar[list[IndexModel]] = [
            # User activity tracking
            IndexModel([("user_id", 1), ("timestamp", -1)], sparse=True, name="user_activity_idx"),
            # Endpoint usage statistics
            IndexModel([("endpoint", 1), ("method", 1), ("timestamp", -1)], name="endpoint_stats_idx"),
            # Security monitoring
            IndexModel(
                [("risk_level", 1), ("is_suspicious", 1), ("timestamp", -1)],
                name="security_monitoring_idx",
            ),
            IndexModel([("auth_type", 1), ("status_code", 1)], name="auth_status_idx"),
            # Performance monitoring
            IndexModel([("status_code", 1), ("processing_time_ms", 1)], name="performance_idx"),
            IndexModel([("endpoint", 1), ("processing_time_ms", 1)], name="endpoint_performance_idx"),
            # Time-based queries and cleanup
            IndexModel([("timestamp", -1)], name="time_series_idx"),
            # Request tracking (unique constraint)
            IndexModel([("request_id", 1)], unique=True, name="request_tracking_idx"),
            # IP-based security analysis
            IndexModel([("ip_address", 1), ("timestamp", -1)], sparse=True, name="ip_analysis_idx"),
            # Compound security analysis
            IndexModel(
                [("ip_address", 1), ("user_id", 1), ("timestamp", -1)],
                sparse=True,
                name="ip_user_analysis_idx",
            ),
            # Error analysis
            IndexModel(
                [("status_code", 1), ("error_code", 1), ("timestamp", -1)],
                sparse=True,
                name="error_analysis_idx",
            ),
        ]

    # Helper methods
    async def get_user_activity_summary(self) -> dict:
        """Get activity summary for the user of this audit log."""
        if not self.user_id:
            return {}

        pipeline = [
            {"$match": {"user_id": self.user_id}},
            {
                "$group": {
                    "_id": None,
                    "total_requests": {"$sum": 1},
                    "unique_endpoints": {"$addToSet": "$endpoint"},
                    "latest_activity": {"$max": "$timestamp"},
                    "error_count": {"$sum": {"$cond": [{"$gte": ["$status_code", 400]}, 1, 0]}},
                },
            },
        ]

        result = await APIAuditLog.aggregate(pipeline).to_list()
        if result:
            summary = result[0]
            summary["unique_endpoints_count"] = len(summary["unique_endpoints"])
            del summary["unique_endpoints"]
            return summary
        return {}

    async def get_similar_requests(self, limit: int = 10) -> list["APIAuditLog"]:
        """Find similar requests based on endpoint and user."""
        query = {
            "endpoint": self.endpoint,
            "method": self.method,
            "_id": {"$ne": self.id},
        }

        if self.user_id:
            query["user_id"] = self.user_id
        elif self.ip_address:
            query["ip_address"] = str(self.ip_address)

        return await APIAuditLog.find(query).sort([("timestamp", -1)]).limit(limit).to_list()
