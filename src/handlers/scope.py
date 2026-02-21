from settings.scopes.default_scopes import DEFAULT_SCOPES
from utils.logger.custom_logging import LoggerMixin


class ScopeHandler(LoggerMixin):
    def get_all_scopes(self) -> dict:
        """
        Returns all defined scopes in the system.
        """
        self.logger.info("event=getting-all-scopes")
        return DEFAULT_SCOPES
