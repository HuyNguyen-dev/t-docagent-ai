from datetime import datetime

from models.knowledge_base import KnowledgeBase
from models.tag import Tag
from schemas.response import Page
from schemas.tag import TagResponse, TagUpdate
from utils.constants import TIMEZONE
from utils.logger.custom_logging import LoggerMixin


class TagService(LoggerMixin):
    """Service for managing tag operations."""

    async def create_tag(self, name: str) -> Tag | None:
        """Create a new tag."""
        # Check if tag name already exists
        existing_tag = await Tag.find_one({"name": name})
        if existing_tag:
            self.logger.warning(
                'event=tag-create-failed name=%s message="Tag name already exists"',
                name,
            )
            return None

        # Create new tag
        new_tag = Tag(
            name=name,
        )

        await new_tag.create()

        self.logger.info(
            'event=tag-created name=%s id=%s message="Tag created successfully"',
            new_tag.name,
            new_tag.id,
        )

        return new_tag

    async def get_tag_by_id(self, tag_id: str) -> Tag | None:
        """Get a tag by ID."""
        tag = await Tag.get(tag_id)
        if not tag:
            self.logger.warning(
                'event=tag-not-found id=%s message="Tag not found"',
                tag_id,
            )
        return tag

    async def get_tag_by_name(self, name: str) -> Tag | None:
        """Get a tag by name."""
        tag = await Tag.find_one({"name": name})
        if not tag:
            self.logger.warning(
                'event=tag-not-found name=%s message="Tag not found"',
                name,
            )
        return tag

    async def list_tags(
        self,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        active_only: bool = True,
    ) -> Page | None:
        """List tags with pagination and optional search."""
        # Build query filter
        query_filter = {}
        if active_only:
            query_filter["is_active"] = True
        if search:
            query_filter["name"] = {"$regex": search, "$options": "i"}

        # Get total count with filters
        total_items = await Tag.find(query_filter).count()

        # Calculate pagination
        total_pages = (total_items + page_size - 1) // page_size
        start_index = (page - 1) * page_size

        # Get paginated tags with filters
        tags = await Tag.find(query_filter).skip(start_index).limit(page_size).to_list()

        # Convert to response format
        tag_responses = []
        for tag in tags:
            # Count usage in knowledge bases
            usage_count = await KnowledgeBase.find({"tags": tag.name}).count()

            tag_response = TagResponse(
                id=tag.id,
                name=tag.name,
                created_at=tag.created_at,
                created_by=tag.created_by,
                is_active=tag.is_active,
                usage_count=usage_count,
            )
            tag_responses.append(tag_response)

        # Create Page response with tags as items
        page_response = Page(
            items=tag_responses,
            metadata={
                "page": page,
                "page_size": page_size,
                "total_items": total_items,
                "total_pages": total_pages,
            },
        )

        self.logger.info(
            'event=tag-list-success page=%d total=%d message="Tags listed successfully"',
            page,
            total_items,
        )

        return page_response

    async def update_tag(self, tag_id: str, tag_update: TagUpdate) -> Tag | None:
        """Update an existing tag."""
        # Get existing tag
        tag = await Tag.get(tag_id)
        if not tag:
            self.logger.warning(
                'event=tag-update-failed id=%s message="Tag not found"',
                tag_id,
            )
            return None

        # Check if new name conflicts with existing tag
        if tag_update.name and tag_update.name != tag.name:
            existing_tag = await Tag.find_one({"name": tag_update.name})
            if existing_tag:
                self.logger.warning(
                    'event=tag-update-failed id=%s name=%s message="Tag name already exists"',
                    tag_id,
                    tag_update.name,
                )
                return None

        # Build update data
        update_data = {}
        if tag_update.name is not None:
            update_data["name"] = tag_update.name
        if tag_update.is_active is not None:
            update_data["is_active"] = tag_update.is_active

        if not update_data:
            self.logger.warning(
                'event=tag-update-no-changes id=%s message="No changes provided for update"',
                tag_id,
            )
            return tag

        # Update tag
        await tag.update({"$set": update_data})

        # If name was changed, update all knowledge bases using this tag
        if tag_update.name and tag_update.name != tag.name:
            await KnowledgeBase.find({"tag": tag.name}).update({"$set": {"tag": tag_update.name}})

        self.logger.info(
            'event=tag-updated id=%s name=%s message="Tag updated successfully"',
            tag_id,
            tag.name,
        )

        return tag

    async def delete_tag(self, tag_id: str) -> bool:
        """Delete a tag."""
        # Get tag
        tag = await Tag.get(tag_id)
        if not tag:
            self.logger.warning(
                'event=tag-delete-failed id=%s message="Tag not found"',
                tag_id,
            )
            return False

        await KnowledgeBase.find({"tags": tag.name}).update_many(
            {"$pull": {"tags": tag.name}, "$set": {"updated_at": datetime.now(TIMEZONE)}},
        )

        # Delete tag
        await tag.delete()

        self.logger.info(
            'event=tag-deleted id=%s name=%s message="Tag deleted successfully"',
            tag_id,
            tag.name,
        )

        return True

    async def get_all_active_tags(self) -> list[str] | None:
        """Get all active tag names for dropdown selection."""
        tags = await Tag.find({"is_active": True}).to_list()
        tag_names = [tag.name for tag in tags]
        tag_names.sort()  # Sort alphabetically

        self.logger.info(
            'event=get-active-tags found=%d message="Retrieved active tags"',
            len(tag_names),
        )

        return tag_names

    async def get_all_tags_from_kb(self) -> list[str] | None:
        """Get all unique tags from knowledge bases (legacy method for backward compatibility)."""
        # Get all knowledge bases from MongoDB
        kbs_in_db = await KnowledgeBase.find_all().to_list()

        # Collect unique tags from knowledge bases
        tags = set()
        for kb in kbs_in_db:
            if kb.tags:
                for tag in kb.tags:
                    if tag and tag.strip():
                        tags.add(tag.strip())

        # Sort tags alphabetically
        sorted_tags = sorted(tags)

        self.logger.info(
            'event=get-all-tags-from-kb found=%d message="Retrieved all unique tags from KB"',
            len(sorted_tags),
        )
        return sorted_tags
