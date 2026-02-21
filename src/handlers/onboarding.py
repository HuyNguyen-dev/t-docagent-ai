"""
Owner Onboarding and Authentication Handler

This module handles the initial system setup and user authentication processes.
"""

from datetime import datetime

from fastapi import HTTPException, status

from models import LLMConfiguration
from models.role import Role
from models.user import User
from schemas.user import (
    OwnerOnboardingRequest,
    SystemStatusResponse,
    UserResponse,
    UserStatus,
)
from utils.auth import (
    hash_password,
)
from utils.constants import DEFAULT_ROLES, TIMEZONE
from utils.enums import UserRole
from utils.logger.custom_logging import LoggerMixin


class OnboardingHandler(LoggerMixin):
    """Handler for system onboarding and authentication operations."""

    async def get_system_status(self) -> SystemStatusResponse | None:
        """
        Get the current system initialization status.

        Returns:
            SystemStatusResponse: Current system status
        """
        self.logger.info('event=checking-system-status message="Checking system initialization status"')

        try:
            # Initialize default roles first (safe operation)
            await self.initialize_default_roles()

            status_data = await self.check_system_initialization()

            response = SystemStatusResponse(
                is_initialized=status_data["is_initialized"],
                has_owner=status_data["has_owner"],
                requires_onboarding=status_data["requires_onboarding"],
                version=status_data["version"],
                status=status_data["status"],
            )
            self.logger.info(
                'event=system-status-check-completed status=%s message="System status check completed"',
                response.status,
            )
        except Exception:
            self.logger.exception('event=system-status-check-failed message="Failed to check system status"')
            # Return safe defaults in case of error
            return SystemStatusResponse(
                is_initialized=False,
                has_owner=False,
                requires_onboarding=True,
                version="1.0.0",
                status="error",
            )
        return response

    async def onboard_owner(
        self,
        onboarding_request: OwnerOnboardingRequest,
    ) -> UserResponse:
        """
        Create the first owner account for system initialization.

        Args:
            onboarding_request: Owner account details

        Returns:
            UserResponse: Created owner user details

        Raises:
            HTTPException: If system already initialized or creation fails
        """
        self.logger.info('event=owner-onboarding-start email=%s message="Starting owner onboarding"', onboarding_request.email)

        # Initialize default roles before checking system status
        await self.initialize_default_roles()

        # Check if system is already initialized
        system_status = await self.check_system_initialization()
        if system_status["has_owner"]:
            self.logger.warning(
                'event=owner-already-exists message="Attempted to create owner when system already initialized"',
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="System already has an owner account. Use login instead.",
            )

        # Check if user with this email already exists
        existing_user = await User.find_one({"email": onboarding_request.email})
        if existing_user:
            self.logger.warning(
                'event=email-already-exists email=%s message="Attempted to create owner with existing email"',
                onboarding_request.email,
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with this email already exists.",
            )

        # Hash the password
        password_hash = hash_password(onboarding_request.password)

        # Create the owner user
        owner_user = User(
            email=onboarding_request.email,
            name=onboarding_request.name,
            role=UserRole.OWNER,
            status=UserStatus.ACTIVE,
            password_hash=password_hash,
            created_at=datetime.now(TIMEZONE),
            updated_at=datetime.now(TIMEZONE),
            is_active=True,
        )

        # Save the owner user
        await owner_user.save()
        self.logger.info('event=owner-user-created user_id=%s message="Owner user created successfully"', owner_user.id)

        owner_config = await LLMConfiguration.find_one(LLMConfiguration.user_id == owner_user.id)
        if owner_config is None:
            owner_config = await LLMConfiguration(
                user_id=owner_user.id,
            ).create()
        self.logger.info(
            'event=default-llm-schema-model model_name=%s message="Default LLM Schema Discovery Model"',
            owner_config.schema_discovery.name,
        )
        self.logger.info(
            'event=default-llm-extraction-model model_name=%s message="Default LLM Extraction Model"',
            owner_config.extraction.name,
        )

        # Create response
        user_response = UserResponse(**owner_user.model_dump())

        self.logger.info(
            'event=owner-onboarding-completed email=%s message="Owner onboarding completed successfully"',
            onboarding_request.email,
        )
        return user_response

    async def validate_onboarding_request(self, request: OwnerOnboardingRequest) -> None:
        """
        Validate the owner onboarding request.

        Args:
            request: The onboarding request to validate

        Raises:
            HTTPException: If validation fails
        """
        # Email format is already validated by Pydantic EmailStr

        # Validate name
        if not request.name.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Name cannot be empty.",
            )

        # Validate password strength
        password = request.password
        errors = []

        if len(password) < 8:
            errors.append("Password must be at least 8 characters long")

        if not any(c.isupper() for c in password):
            errors.append("Password must contain at least one uppercase letter")

        if not any(c.islower() for c in password):
            errors.append("Password must contain at least one lowercase letter")

        if not any(c.isdigit() for c in password):
            errors.append("Password must contain at least one number")

        if not any(c in '!@#$%^&*(),.?":{}|<>' for c in password):
            errors.append("Password must contain at least one special character")

        if errors:
            self.logger.warning(
                "Password validation failed for %s: %s",
                request.email,
                "; ".join(errors),
            )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Password validation failed: {'; '.join(errors)}",
            )

    async def initialize_default_roles(self) -> None:
        """
        Initialize default system roles if they don't exist.
        """
        self.logger.info('event=initializing-default-roles message="Initializing default system roles"')

        # Quick test to ensure database is accessible
        await Role.find().limit(1).to_list()

        created_roles = []
        for role_data in DEFAULT_ROLES:
            # Check if role already exists
            existing_role = await Role.find_one({"name": role_data["name"]})
            if not existing_role:
                # Create new role with system user as creator
                role = Role(**role_data, created_by="system")
                await role.insert()
                created_roles.append(role_data["name"])
                self.logger.info('event=role-created role_name=%s message="Created default role"', role_data["name"])
            else:
                self.logger.debug(
                    'event=role-already-exists role_name=%s message="Role already exists"',
                    role_data["name"],
                )

        if created_roles:
            self.logger.info(
                'event=roles-initialized count=%s roles=%s message="Successfully initialized default roles"',
                len(created_roles),
                ", ".join(created_roles),
            )
        else:
            self.logger.info('event=all-roles-exist message="All default roles already exist"')

    async def check_system_initialization(self) -> dict:
        """
        Check if the system has been initialized with an owner account.

        Returns:
            Dictionary with system status information
        """
        self.logger.info('event=checking-system-init-status message="Checking system initialization status"')

        try:
            # Check database connectivity first
            await User.find().limit(1).to_list()

            # Check if any owner account exists
            owner_count = await User.find({"role": UserRole.OWNER, "is_active": True}).count()
            has_owner = owner_count > 0

            result = {
                "is_initialized": has_owner,
                "has_owner": has_owner,
                "requires_onboarding": not has_owner,
                "version": "1.0.0",
                "status": "ready" if has_owner else "needs_initialization",
            }

            self.logger.info(
                'event=system-init-check-completed status=%s message="System initialization check completed"',
                result["status"],
            )
        except Exception:
            self.logger.exception('event=system-init-check-error message="Error checking system initialization"')
            return {
                "is_initialized": False,
                "has_owner": False,
                "requires_onboarding": True,
                "version": "1.0.0",
                "status": "error",
            }
        return result
