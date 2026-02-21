from datetime import datetime

from models.runbook import RunBook
from schemas.runbook import RunbookInput, RunbookResponse, RunbookUpdate
from utils.constants import TIMEZONE
from utils.logger.custom_logging import LoggerMixin


class RunbookHandler(LoggerMixin):
    async def create_runbook(self, runbook_input: RunbookInput) -> tuple[str, str] | None:
        """Create a new runbook."""
        runbooks = await RunBook.find_many(RunBook.name == runbook_input.name).to_list()
        version = "1"
        if runbooks:
            versions = [int(rb.version.split(".")[-1]) for rb in runbooks]
            highest_version = max(versions)
            version = str(highest_version + 1)

        runbook = RunBook(
            name=runbook_input.name,
            prompt=runbook_input.prompt,
            version=version,
            created_at=runbook_input.created_at,
            last_updated=runbook_input.created_at,
        )
        await runbook.insert()

        self.logger.info(
            'event=create-runbook-success message="Created runbook successfully" prms="name=%s, version=%s"',
            runbook_input.name,
            version,
        )
        return (runbook.name, runbook.version)

    async def edit_runbook(self, name: str, runbook_update: RunbookUpdate) -> bool:
        """Edit a runbook's content."""
        runbook = await RunBook.find_one(RunBook.name == name, RunBook.version == runbook_update.version)
        if runbook:
            runbook.prompt = runbook_update.content
            runbook.last_updated = datetime.now(TIMEZONE)
            await runbook.save()

            self.logger.info(
                'event=edit-runbook-success message="Edited runbook successfully" prms="name=%s"',
                name,
            )
            return True

        self.logger.warning(
            'event=edit-runbook-warning message="No runbook found to edit" prms="name=%s"',
            name,
        )
        return False

    async def get_runbook(self, name: str, version: str) -> RunbookResponse | None:
        """Get a runbook by name and version."""
        runbook = await RunBook.find_one(RunBook.name == name, RunBook.version == version)
        if runbook:
            runbook_response = RunbookResponse(**runbook.model_dump())

            self.logger.info(
                'event=get-runbook-success message="Retrieved runbook successfully" prms="name=%s, version=%s"',
                name,
                version,
            )
            return runbook_response

        self.logger.warning(
            'event=get-runbook-warning message="No runbook found" prms="name=%s, version=%s"',
            name,
            version,
        )
        return None

    async def delete_all_runbooks(self, name: str) -> bool:
        """Delete all versions of a runbook."""
        result = await RunBook.find(RunBook.name == name).delete()
        success = result.deleted_count > 0

        if success:
            self.logger.info(
                'event=delete-all-runbooks-success message="Deleted all runbooks successfully" prms="name=%s"',
                name,
            )
            return True
        self.logger.warning(
            'event=delete-all-runbooks-warning message="No runbooks found to delete" prms="name=%s"',
            name,
        )
        return False

    async def delete_runbook_by_version(self, name: str, version: str) -> bool:
        """Delete a specific version of a runbook."""
        result = await RunBook.find_one(
            RunBook.name == name,
            RunBook.version == version,
        ).delete()
        success = result.deleted_count > 0

        if success:
            self.logger.info(
                'event=delete-runbook-version-success message="Deleted runbook version successfully" prms="name=%s, version=%s"',
                name,
                version,
            )
            return True
        self.logger.warning(
            'event=delete-runbook-version-warning message="No runbook version found to delete" prms="name=%s, version=%s"',
            name,
            version,
        )
        return False

    async def get_all_runbook_template(self) -> list[RunbookResponse]:
        """Get all runbooks where labels contain 'template'."""
        runbooks = await RunBook.find(RunBook.labels == "template").to_list()
        responses = [RunbookResponse(**rb.model_dump()) for rb in runbooks]

        self.logger.info(
            'event=get-all-runbook-template-success message="Retrieved all runbook templates successfully" count=%d',
            len(responses),
        )
        return responses
