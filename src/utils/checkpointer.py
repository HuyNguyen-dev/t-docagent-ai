from langgraph.checkpoint.mongodb.aio import AsyncMongoDBSaver

from config import settings


async def delete_thread_from_checkpoint(thread_id: str) -> None:
    """
    Delete a thread from the MongoDB checkpointer.

    Args:
        thread_id: The thread ID to delete
    """
    async with get_mongodb_checkpointer() as checkpointer:
        await checkpointer.adelete_thread(thread_id=thread_id)


def get_mongodb_checkpointer() -> AsyncMongoDBSaver:
    """
    Create and return a MongoDB checkpointer instance.

    Returns:
        AsyncMongoDBSaver instance configured with the application settings
    """
    return AsyncMongoDBSaver.from_conn_string(
        conn_string=str(settings.MONGODB_DSN),
        db_name=str(settings.MONGODB_DATABASE_NAME),
    )
