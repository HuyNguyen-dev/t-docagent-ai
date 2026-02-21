import google.auth.exceptions
import openai

from helpers.llm.chat import LLMService, LLMTypes
from models import LLMConfiguration, User
from schemas.llm_configuration import LLMConfigurationInput, LLMConfigurationResponse, LLMConfigurationTest
from utils.enums import LLMProvider, ModelType, UserRole
from utils.logger.custom_logging import LoggerMixin

# Define a constant for the test prompt to avoid magic strings
TEST_PROMPT = "Hi Guys"


class LLMConfigurationHandler(LoggerMixin):
    @staticmethod
    async def get_owner_llm_config() -> LLMConfiguration | None:
        """
        Fetches the LLM configuration for the OWNER user.
        Refactored for clarity and simplicity over a complex aggregation pipeline.
        """
        # Find the owner user first
        owner_user = await User.find_one({"role": UserRole.OWNER.value})
        if not owner_user:
            return None
        # Then find their configuration
        return await LLMConfiguration.find_one({"user_id": owner_user.id})

    async def _test_llm_invocation(
        self,
        llm: LLMTypes | None,
        context: str,
    ) -> bool:
        """
        Invokes an LLM instance and handles all potential exceptions.

        Args:
            llm: The language model instance to test.
            context: A string describing the configuration being tested for logging.

        Returns:
            True if the invocation is successful, False otherwise.
        """
        if not llm:
            self.logger.error("LLM object is None for test context: %s", context)
            return False
        try:
            response = await llm.ainvoke(TEST_PROMPT)
            self.logger.debug(
                "event=test_llm_configuration_success context='%s' message='LLM response: %s'",
                context,
                response.content,
            )
        except openai.APIConnectionError:
            self.logger.exception(
                "event=test_llm_configuration_failed context='%s' message='API Connection Error'",
                context,
            )
            return False
        except (
            openai.AuthenticationError,
            google.auth.exceptions.DefaultCredentialsError,
            openai.OpenAIError,
            openai.PermissionDeniedError,
        ):
            self.logger.exception(
                "event=test_llm_configuration_failed context='%s' message='Authentication Error'",
                context,
            )
            return False
        return True

    def get_llm_config_by_key(self, owner_config: LLMConfiguration, key: str) -> dict[str, any] | None:
        """
        Retrieves a specific sub-configuration (e.g., 'schema_discovery') and resolves its parameters.

        Args:
            owner_config: The owner's full LLM configuration.
            key: The key for the sub-config to retrieve (e.g., 'schema_discovery', 'extraction').

        Returns:
            A dictionary of parameters for LLMService.create_llm, or None if the key is invalid.
        """
        sub_config = getattr(owner_config, key, None)
        if not sub_config:
            self.logger.error("Invalid LLM configuration key provided: %s", key)
            return None

        params = {"provider": sub_config.provider, "llm_name": sub_config.name}

        if sub_config.provider == LLMProvider.AZURE_OPENAI:
            # Check if the sub-config itself has a key, or if we need to find it in the owner's list
            if sub_config.api_key and sub_config.api_key.get_secret_value():
                params.update(
                    {
                        "api_key": sub_config.api_key.get_secret_value(),
                        "deployment_name": sub_config.deployment_name,
                        "endpoint": sub_config.base_url,
                        "api_version": sub_config.api_version,
                    },
                )
            elif owner_config.azure_openai:
                found_config = False
                for az_config in owner_config.azure_openai:
                    if az_config.name == sub_config.name:
                        params.update(
                            {
                                "api_key": az_config.api_key.get_secret_value() or "",
                                "deployment_name": az_config.deployment_name,
                                "endpoint": az_config.base_url,
                                "api_version": az_config.api_version,
                            },
                        )
                        found_config = True
                        break
                if not found_config:
                    self.logger.warning("Azure config '%s' not found, returning empty credentials.", sub_config.name)
                    params.update({"api_key": "", "deployment_name": "", "endpoint": "", "api_version": ""})
            else:
                params.update({"api_key": "", "deployment_name": "", "endpoint": "", "api_version": ""})

        else:  # OpenAI or Google
            api_key_secret = sub_config.api_key
            if api_key_secret and api_key_secret.get_secret_value():
                params["api_key"] = api_key_secret.get_secret_value()
            elif sub_config.provider == LLMProvider.OPENAI and owner_config.openai_api_key:
                params["api_key"] = owner_config.openai_api_key.get_secret_value()
            elif sub_config.provider == LLMProvider.GOOGLE_AI and owner_config.google_api_key:
                params["api_key"] = owner_config.google_api_key.get_secret_value()
            else:
                self.logger.warning(
                    'No API key found for %s provider in sub-config "%s" or owner defaults.',
                    sub_config.provider,
                    key,
                )
                params["api_key"] = ""

        return params

    def prepare_llm_params(
        self,
        owner_config: LLMConfiguration | None,
        test_config: dict[str, any],
    ) -> dict[str, any] | None:
        """
        Prepares the parameter dictionary for LLMService.create_llm based on a test config.

        This helper centralizes the logic for determining the correct API key and other
        parameters, whether they come from the test payload or the owner's saved config.

        Args:
            owner_config: The fallback configuration from the owner.
            test_config: The specific configuration section to test (e.g., for 'extraction').

        Returns:
            A dictionary of parameters for `create_llm` or None if params can't be resolved.
        """
        provider = test_config.get("provider")
        params = {"provider": provider, "llm_name": test_config.get("name")}

        if provider == LLMProvider.AZURE_OPENAI:
            if "api_key" in test_config and test_config.get("api_key"):  # Full details are in the test config
                params.update(
                    {
                        "api_key": test_config["api_key"].get_secret_value(),
                        "deployment_name": test_config["deployment_name"],
                        "endpoint": test_config["base_url"],
                        "api_version": test_config["api_version"],
                    },
                )
            else:  # Fallback to owner's named Azure config
                if not owner_config or not owner_config.azure_openai:
                    self.logger.error("Cannot find Azure config: Owner config is missing.")
                    return None
                for az_config in owner_config.azure_openai:
                    if az_config.name == test_config.get("name"):
                        params.update(
                            {
                                "api_key": az_config.api_key.get_secret_value(),
                                "deployment_name": az_config.deployment_name,
                                "endpoint": az_config.base_url,
                                "api_version": az_config.api_version,
                            },
                        )
                        return params
                self.logger.error('Azure config named "%s" not found.', test_config.get("name"))
                return None
        else:  # OpenAI or Google
            api_key_secret = test_config.get("api_key")
            if api_key_secret:
                params["api_key"] = api_key_secret.get_secret_value()
            elif owner_config:
                if provider == LLMProvider.OPENAI and owner_config.openai_api_key:
                    params["api_key"] = owner_config.openai_api_key.get_secret_value()
                elif provider == LLMProvider.GOOGLE_AI and owner_config.google_api_key:
                    params["api_key"] = owner_config.google_api_key.get_secret_value()

            if "api_key" not in params:
                self.logger.error('API key for provider "%s" could not be resolved.', provider)
                return None

        return params

    async def test_llm_configuration(self, config_test: LLMConfigurationTest) -> bool:
        """
        Tests one or more LLM configurations provided in the payload.

        This method now correctly tests all provided configurations sequentially
        and fails immediately if any single test does not pass.

        Args:
            config_test: The Pydantic model containing configurations to test.

        Returns:
            True if all provided configurations are valid, False otherwise.
        """
        try:
            config_data = config_test.model_dump(exclude_none=True)
            owner_config = await self.get_owner_llm_config()

            tests_to_run = []
            # Test 1: Direct OpenAI API Key
            if "openai_api_key" in config_data:
                tests_to_run.append(
                    (
                        LLMService(llm=ModelType.OPENAI_GPT_4_1_MINI).create_llm(
                            is_default=False,
                            provider=LLMProvider.OPENAI,
                            api_key=config_data["openai_api_key"].get_secret_value() or "",
                        ),
                        "Direct OpenAI Key Test",
                    ),
                )
            # Test 2: Direct Google API Key
            if "google_api_key" in config_data:
                tests_to_run.append(
                    (
                        LLMService(llm=ModelType.GEMINI_2_0_FLASH).create_llm(
                            is_default=False,
                            provider=LLMProvider.GOOGLE_AI,
                            api_key=config_data["google_api_key"].get_secret_value() or "",
                        ),
                        "Direct Google Key Test",
                    ),
                )
            # Test 3: Direct Azure Config
            if "azure_openai" in config_data:
                azure_config = config_data["azure_openai"]
                tests_to_run.append(
                    (
                        LLMService().create_llm(
                            is_default=False,
                            provider=LLMProvider.AZURE_OPENAI,
                            api_key=azure_config["api_key"].get_secret_value(),
                            deployment_name=azure_config["deployment_name"],
                            endpoint=azure_config["base_url"],
                            api_version=azure_config["api_version"],
                        ),
                        "Direct Azure Config Test",
                    ),
                )
            # Tests 4 & 5: Schema Discovery, Extraction, Embedding, Rerank configs
            for key in ["schema_discovery", "extraction", "embedding", "rerank"]:
                if key in config_data:
                    params = self.prepare_llm_params(owner_config, config_data[key])
                    if params:
                        llm_name = params.pop("llm_name", None)
                        llm = LLMService(llm=llm_name).create_llm(is_default=False, **params)
                        tests_to_run.append((llm, f"'{key}' Configuration Test"))
                    else:
                        self.logger.error('Could not prepare params for "%s", skipping test.', key)
                        return False
            if not tests_to_run:
                self.logger.info("No new LLM configurations were provided to test.")
                return True
            for llm_instance, context in tests_to_run:
                if not await self._test_llm_invocation(llm_instance, context):
                    return False  # Fail fast
        except openai.APIConnectionError:
            self.logger.exception(
                'event=test-api-key-for-llm-configuration-failed message="API Connection Error"',
            )
            return False
        except (
            openai.AuthenticationError,
            google.auth.exceptions.DefaultCredentialsError,
            openai.OpenAIError,
            openai.PermissionDeniedError,
        ) as e:
            self.logger.exception(
                'event=test-api-key-for-llm-configuration-failed message="Authentication/Configuration error: %s"',
                type(e).__name__,
            )
            return False
        return True

    async def get_llm_configuration(self) -> LLMConfigurationResponse | None:
        """
        Retrieves the owner's LLM configuration.
        """
        self.logger.info("event=get-llm-config-start message='Attempting to retrieve owner LLM configuration.'")
        owner_config = await self.get_owner_llm_config()
        if not owner_config:
            self.logger.warning(
                "event=get-llm-config-not-found message='No LLM configuration found for the owner.'",
            )
            return None
        self.logger.info("event=get-llm-config-success message='Owner LLM configuration retrieved successfully.'")
        return LLMConfigurationResponse.from_db_model(owner_config)

    async def get_azure_config_names(self) -> list[str] | None:
        """
        Returns a list of names for all Azure OpenAI configurations for the owner.

        Returns an empty list if the owner has no Azure configs, or None on unexpected error.
        """
        owner_config = await self.get_owner_llm_config()
        if not owner_config or not owner_config.azure_openai:
            self.logger.info("event=get-azure-names-empty message='No Azure OpenAI configurations found for owner.'")
            return []
        names: list[str] = []
        for az in owner_config.azure_openai:
            # az is a Pydantic model; safely get name
            name = getattr(az, "name", None)
            if name:
                names.append(name)
        self.logger.debug("event=get-azure-names-success message='Retrieved %d Azure config names.'", len(names))
        return names

    async def update_llm_configuration(
        self,
        config_input: LLMConfigurationInput,
    ) -> LLMConfigurationResponse | None:
        """
        Updates the owner's LLM configuration with only the provided fields.

        This function performs a partial update. It fetches the existing configuration,
        applies the changes from the input, encrypts any secrets, and saves
        the document back to the database.

        Args:
            config_input: A Pydantic model containing the fields to update.
                          Fields not present in the input will not be changed.

        Returns:
            The updated LLMConfiguration object if successful, otherwise None.
        """
        self.logger.info("event=update-llm-config-start message='Attempting to update owner LLM configuration.'")
        # Step 1: Fetch the existing configuration document for the owner.
        owner_config = await self.get_owner_llm_config()
        if not owner_config:
            self.logger.error(
                "event=update-llm-config-failed message='Cannot update because no existing owner LLM configuration was found.'",
            )
            # Depending on business logic, you might want to create one here instead.
            # For an update operation, failing is generally safer.
            return None

        # Step 2: Get a dictionary of only the fields that were explicitly set in the input.
        # This is the core of the partial update logic.
        update_data = config_input.model_dump(exclude_none=True)

        if not update_data:
            self.logger.warning(
                "event=update-llm-config-skipped message='No fields were provided to update.'",
            )
            return LLMConfigurationResponse.from_db_model(owner_config)  # Return the original config as no changes were made.
        await owner_config.update({"$set": update_data})
        self.logger.info(
            "event=update-llm-config-success message='LLM configuration updated successfully. Fields changed: %s'",
            list(update_data.keys()),
        )
        return LLMConfigurationResponse.from_db_model(owner_config)
