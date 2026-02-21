import re
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException, status
from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType, errors
from pymongo import ASCENDING, DESCENDING

from config import APP_HOME, settings
from models.role import Role
from models.user import User
from schemas.response import Page, PaginatedMetadata
from schemas.user import (
    PasswordResetResponse,
    RoleCreateRequest,
    RoleCreateResponse,
    RoleListResponse,
    UserCreateRequest,
    UserCreateResponse,
    UserPasswordUpdateRequest,
    UserResponse,
    UserStatisticsResponse,
    UserStatus,
    UserUpdateRequest,
)
from schemas.user import (
    Role as RoleSchema,
)
from utils.auth import hash_password, verify_password
from utils.common import generate_short_password
from utils.constants import TIMEZONE
from utils.enums import EmailType, UserRole
from utils.functions import encrypt_secure
from utils.logger.custom_logging import LoggerMixin


class UserHandler(LoggerMixin):
    """Handler for user management operations."""

    def __init__(self) -> None:
        super().__init__()
        self.mail_config = None

    def _init_mail_config(self) -> None:
        if settings.MAIL_USERNAME is None and settings.MAIL_PASSWORD is None and settings.MAIL_FROM is None:
            self.logger.error(
                "event=init-mail-config-failed "
                'message="Miss some values config: MAIL_USERNAME, MAIL_PASSWORD, MAIL_FROM in environment."',
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Miss some values config: MAIL_USERNAME, MAIL_PASSWORD, MAIL_FROM in environment.",
            )

        self.mail_config = ConnectionConfig(
            MAIL_USERNAME=settings.MAIL_USERNAME,
            MAIL_PASSWORD=settings.MAIL_PASSWORD.get_secret_value(),
            MAIL_FROM=settings.MAIL_FROM,
            MAIL_FROM_NAME="DocAgent Service",
            MAIL_PORT=587,
            MAIL_SERVER="smtp.gmail.com",
            MAIL_STARTTLS=True,
            MAIL_SSL_TLS=False,
            USE_CREDENTIALS=True,
            VALIDATE_CERTS=True,
            TEMPLATE_FOLDER=Path(APP_HOME).joinpath("src", "static"),
            TIMEOUT=60,
        )

    async def send_invitation_email(
        self,
        email_to: str,
        password: str,
        email_type: EmailType = EmailType.RESET_PASSWORD,
    ) -> bool:
        try:
            if self.mail_config is None:
                self._init_mail_config()

            template_data = {
                "email": email_to,
                "password": password,
            }
            fm = FastMail(self.mail_config)
            if email_type == EmailType.INVITATION:
                template_name = "invitation_email_tml.html"
                subject = "🎉 You're Invited to Join DocAgent!"
            elif email_type == EmailType.RESET_PASSWORD:
                template_name = "reset_password_email_tml.html"
                subject = "🎉 Reset password account in DocAgent service"
            else:
                return False

            message = MessageSchema(
                subject=subject,
                recipients=[email_to],
                template_body=template_data,
                subtype=MessageType.html,
            )
            await fm.send_message(message, template_name=template_name)
        except errors.ConnectionErrors:
            self.logger.exception(
                'event=send-invitation-email-failed message="Connect to smtp.gmail.com Failed"',
            )
            return False
        except Exception:
            self.logger.exception(
                'event=send-invitation-email-failed message="Got exception error"',
            )
            return False
        return True

    async def send_hitl_reason_email(
        self,
        email_to: str,
        reason: str,
        conv_id: str,
        agent_name: str,
        action_url: str | None = None,
    ) -> bool:
        try:
            if self.mail_config is None:
                self._init_mail_config()

            template_data = {
                "email": email_to,
                "reason": reason,
                "conv_id": conv_id,
                "agent_name": agent_name,
                "created_at": datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S %Z"),
                "action_url": action_url or "",
            }

            fm = FastMail(self.mail_config)
            message = MessageSchema(
                subject="👀 Human input needed in your DocAgent conversation",
                recipients=[email_to],
                template_body=template_data,
                subtype=MessageType.html,
            )
            await fm.send_message(message, template_name="hitl_reason_email_tml.html")
        except errors.ConnectionErrors:
            self.logger.exception(
                'event=send-hitl-email-failed message="Connect to smtp.gmail.com Failed"',
            )
            return False
        except Exception:
            self.logger.exception(
                'event=send-hitl-email-failed message="Got exception error"',
            )
            return False
        return True

    async def send_success_email(
        self,
        email_to: str,
        conv_id: str,
        agent_name: str,
    ) -> bool:
        """Send success notification email when task is completed without human intervention."""
        try:
            if self.mail_config is None:
                self._init_mail_config()

            template_data = {
                "email": email_to,
                "conv_id": conv_id,
                "agent_name": agent_name,
                "created_at": datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S %Z"),
            }

            fm = FastMail(self.mail_config)
            message = MessageSchema(
                subject="✅ Task Completed Successfully - DocAgent",
                recipients=[email_to],
                template_body=template_data,
                subtype=MessageType.html,
            )
            await fm.send_message(message, template_name="success_email_tml.html")
        except errors.ConnectionErrors:
            self.logger.exception(
                'event=send-success-email-failed message="Connect to smtp.gmail.com Failed"',
            )
            return False
        except Exception:
            self.logger.exception(
                'event=send-success-email-failed message="Got exception error"',
            )
            return False
        return True

    async def create_user(
        self,
        user_request: UserCreateRequest,
        created_by_user_id: str,
    ) -> UserCreateResponse | None:
        """
        Create a new user (invite).
        """
        # Check if user already exists
        existing_user = await User.find_one(User.email == user_request.email)
        if existing_user:
            self.logger.error(
                'event=create-new-user-failed message="User with this email already exists"',
            )
            msg = "User with this email already exists"
            raise ValueError(msg)

        existing_role = await Role.find_one(Role.name == user_request.role)
        if not existing_role:
            self.logger.error(
                'event=create-new-user-failed message="The role %s not found"',
                user_request.role,
            )
            msg = f"The role {user_request.role} not found"
            raise ValueError(msg)

        password = generate_short_password(10)
        # Create user
        user = User(
            email=user_request.email,
            name=user_request.name,
            role=user_request.role,
            status=UserStatus.PENDING,
            password_hash=hash_password(password),
        )
        await user.insert()
        self.logger.info(
            "event=user-created user_id=%s email=%s role=%s created_by=%s",
            user.id,
            user.email,
            user.role,
            created_by_user_id,
        )
        is_invite = await self.send_invitation_email(user_request.email, password, EmailType.INVITATION)
        if not is_invite:
            await user.delete()
            return None

        return UserCreateResponse(
            id=str(user.id),
            email=user.email,
            name=user.name,
            role=user.role,
            status=user.status,
            created_at=user.created_at,
            is_active=user.is_active,
            password=encrypt_secure(password),
        )

    async def get_users(
        self,
        page: int = 1,
        page_size: int = 20,
        role_filter: list[str] | None = None,
        status_filter: list[str] | None = None,
        q: str = "",
    ) -> Page:
        """
        Get list of users with filtering and pagination.
        """
        n_skip = (page - 1) * page_size
        pipeline = []
        match_conditions = {}

        if role_filter:
            match_conditions["role"] = {"$in": role_filter}

        if status_filter:
            match_conditions["status"] = {"$in": status_filter}

        if q:
            safe_search_term = re.escape(q)
            match_conditions["$or"] = [
                {"name": {"$regex": safe_search_term, "$options": "i"}},
                {"email": {"$regex": safe_search_term, "$options": "i"}},
                {"_id": {"$regex": safe_search_term, "$options": "i"}},
            ]

        if match_conditions:
            pipeline.append({"$match": match_conditions})

        pipeline.extend(
            [
                {
                    "$lookup": {
                        "from": Role.get_collection_name(),
                        "localField": "role",
                        "foreignField": "name",
                        "as": "role_info",
                    },
                },
                {
                    "$unwind": "$role_info",
                },
                {"$sort": {"created_at": DESCENDING}},
                {
                    "$facet": {
                        "metadata": [{"$count": "total"}],
                        "data": [
                            {"$skip": n_skip},
                            {"$limit": page_size},
                            {
                                "$project": {
                                    "id": {"$toString": "$_id"},
                                    "email": "$email",
                                    "name": "$name",
                                    "role": "$role",
                                    "status": "$status",
                                    "scopes": "$role_info.scopes",
                                    "created_at": "$created_at",
                                    "last_seen_at": "$last_seen_at",
                                    "is_active": "$is_active",
                                },
                            },
                        ],
                    },
                },
            ],
        )

        result = await User.aggregate(pipeline).to_list()

        if not result or not result[0]["data"]:
            return Page(
                items=[],
                metadata=PaginatedMetadata(
                    page=1,
                    page_size=page_size,
                    total_items=0,
                    total_pages=1,
                ),
            )

        total_items = result[0]["metadata"][0]["total"]
        user_responses = []
        for item in result[0]["data"]:
            user_resp = UserResponse(**item).model_dump()
            user_resp["is_owner"] = user_resp["role"] == UserRole.OWNER
            user_responses.append(user_resp)

        total_pages = (total_items + page_size - 1) // page_size or 1
        return Page(
            items=user_responses,
            metadata=PaginatedMetadata(
                page=min(page, total_pages),
                page_size=page_size,
                total_items=total_items,
                total_pages=total_pages,
            ),
        )

    async def update_user(
        self,
        user_id: str,
        user_update: UserUpdateRequest,
        updated_by_user_id: str,
    ) -> UserResponse:
        """
        Update user information.
        """
        user = await User.get(user_id)
        if not user:
            self.logger.error(
                'event=update-user-failed user_id=%s message="User not found"',
                user_id,
            )
            msg = "User not found"
            raise ValueError(msg)

        # Prevent editing owner users
        if user.role == UserRole.OWNER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot modify owner users",
            )

        # Update fields
        update_data = {"updated_at": datetime.now(TIMEZONE)}

        if user_update.name is not None:
            update_data["name"] = user_update.name

        if user_update.role is not None:
            update_data["role"] = user_update.role

        if user_update.status is not None:
            update_data["status"] = user_update.status

        await user.set(update_data)
        self.logger.info(
            "event=user-updated user_id=%s updated_by=%s fields=%s",
            user_id,
            updated_by_user_id,
            list(update_data.keys()),
        )

        # Reload user to get updated data
        updated_user = await User.get(user_id)

        return UserResponse(**updated_user.model_dump())

    async def update_password(
        self,
        password_update: UserPasswordUpdateRequest,
        updated_by_user: UserResponse,
    ) -> bool:
        """
        Update a user's password.
        """
        user = await User.get(updated_by_user.id)
        if not user:
            self.logger.error(
                'event=update-password-failed user_id=%s message="User not found"',
                updated_by_user.id,
            )
            return False

        if not verify_password(password_update.old_password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect old password.",
            )

        # Update password
        await user.set(
            {
                "password_hash": hash_password(password_update.new_password),
                "updated_at": datetime.now(TIMEZONE),
            },
        )
        self.logger.info(
            "event=user-password-updated user_id=%s updated_by=%s",
            user.id,
            updated_by_user.id,
        )
        return True

    async def delete_user(
        self,
        user_id: str,
        deleted_by_user_id: str,
    ) -> bool:
        """
        Delete a user.
        """
        user = await User.get(user_id)
        if not user:
            self.logger.error(
                'event=update-user-failed user_id=%s message="User not found"',
                user_id,
            )
            return False

        # Prevent deleting owner users
        if user.role == UserRole.OWNER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot delete owner users",
            )

        await user.delete()

        self.logger.info(
            "event=user-deleted user_id=%s deleted_by=%s",
            user_id,
            deleted_by_user_id,
        )
        return True

    async def get_user_statistics(self) -> UserStatisticsResponse:
        """
        Get user statistics for dashboard.
        """
        # TODO: Optimize query
        total_users = await User.find().count()
        active_users = await User.find(User.status == UserStatus.ACTIVE).count()
        pending_users = await User.find(User.status == UserStatus.PENDING).count()
        suspended_users = await User.find(User.status == UserStatus.SUSPENDED).count()

        return UserStatisticsResponse(
            total_users=total_users,
            active_users=active_users,
            pending_users=pending_users,
            suspended_users=suspended_users,
        )

    async def reset_password(
        self,
        user_id: str,
        updated_by_user_id: str,
    ) -> PasswordResetResponse:
        """
        Reset user password and send a new password via email.
        """
        user = await User.get(user_id)
        if not user:
            self.logger.error(
                'event=reset-password-failed user_id=%s message="User not found"',
                user_id,
            )
            msg = "User not found"
            raise ValueError(msg)

        new_password = generate_short_password(10)
        hashed_new_password = hash_password(new_password)

        await user.set({"password_hash": hashed_new_password, "updated_at": datetime.now(TIMEZONE)})

        self.logger.info(
            "event=user-password-reset user_id=%s updated_by=%s",
            user_id,
            updated_by_user_id,
        )

        await self.send_invitation_email(user.email, new_password)

        return PasswordResetResponse(success=True)


class RoleHandler(LoggerMixin):
    """Handler for custom role management."""

    async def create_role(
        self,
        role_request: RoleCreateRequest,
        created_by_user_id: str,
    ) -> RoleCreateResponse:
        """
        Create a new custom role.
        """
        # Check if role name already exists
        existing_role = await Role.find_one(Role.name == role_request.name)
        if existing_role:
            msg = "Role with this name already exists"
            raise ValueError(msg)

        # Create custom role
        role = await Role(
            name=role_request.name,
            description=role_request.description,
            icon=role_request.icon,
            scopes=role_request.scopes,
            created_at=datetime.now(TIMEZONE),
            created_by=created_by_user_id,
            is_system_role=False,
        ).create()
        self.logger.info(
            "event=role-created role_id=%s name=%s scopes=%s created_by=%s",
            role.id,
            role_request.name,
            len(role_request.scopes),
            created_by_user_id,
        )
        return RoleCreateResponse(
            id=str(role.id),
            name=role.name,
            description=role.description,
            icon=role.icon,
            scopes=role.scopes,
            created_at=role.created_at,
            is_system_role=role.is_system_role,
        )

    async def get_roles(self) -> RoleListResponse:
        """
        Get all custom roles.
        """
        roles = await Role.find().sort([("created_at", ASCENDING)]).to_list()
        list_roles = [RoleSchema(**role.model_dump()) for role in roles]
        return RoleListResponse(roles=list_roles)

    async def get_all_role_names(self, include_owner: bool = False) -> list[str]:
        """
        Get all role names in the database, excluding the 'owner' role.
        Returns:
            List of role names (str) except 'owner'.
        """
        if include_owner:
            roles = await Role.find().to_list()
        else:
            roles = await Role.find(Role.name != UserRole.OWNER).to_list()
        return {role.name: role.name for role in roles}

    async def delete_role(
        self,
        role_id: str,
        deleted_by_user_id: str,
    ) -> bool:
        """
        Delete a custom role.
        """
        role = await Role.get(role_id)
        if not role:
            self.logger.error(
                'event=delete-custom-role-failed role_id=%s message="Custom role not found"',
                role_id,
            )
            return False

        # Check if role is in use by any users
        users_with_role = await User.find(User.role == role.name).count()
        if users_with_role > 0:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Cannot delete role. {users_with_role} users are assigned this role.",
            )

        await role.delete()
        self.logger.info(
            "event=custom-role-deleted role_id=%s deleted_by=%s",
            role_id,
            deleted_by_user_id,
        )
        return True

    async def update_role_scopes(
        self,
        role_id: str,
        scopes: list[str],
        updated_by_user_id: str,
    ) -> RoleCreateResponse:
        """
        Update the scopes of a custom role by its ID.
        Args:
            role_id: The ID of the role to update.
            scopes: The new list of scopes.
            updated_by_user_id: The user performing the update.
        Returns:
            Updated role data.
        """
        role = await Role.get(role_id)
        if not role:
            self.logger.error('event=update-role-failed role_id=%s message="Role not found"', role_id)
            msg = "Role not found"
            raise ValueError(msg)
        # Only update scopes
        await role.set({"scopes": scopes})
        self.logger.info(
            "event=role-updated role_id=%s updated_by=%s scopes=%s",
            role_id,
            updated_by_user_id,
            scopes,
        )
        updated_role = await Role.get(role_id)
        return RoleCreateResponse(
            id=str(updated_role.id),
            name=updated_role.name,
            description=updated_role.description,
            icon=updated_role.icon,
            scopes=updated_role.scopes,
            created_at=updated_role.created_at,
            is_system_role=updated_role.is_system_role,
        )
