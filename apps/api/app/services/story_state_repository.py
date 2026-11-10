from typing import Any
from uuid import UUID

from sqlalchemy import desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import StoryStateSnapshot
from app.schemas.chat import StoryState
from app.services.turn_context import TurnContext


SnapshotState = dict[str, Any]
RelationshipState = dict[str, Any]


class StoryStateRepository:
    """Read-only branch snapshot access with turn-scoped caching."""

    def __init__(self, session: AsyncSession, turn_context: TurnContext) -> None:
        self.session = session
        self.turn_context = turn_context

    async def load_state(
        self,
        story_id: UUID,
        branch_id: UUID,
        exclude_message_id: UUID | None = None,
    ) -> StoryState:
        snapshot_state = await self.load_snapshot_state(
            story_id,
            branch_id,
            exclude_message_id,
        )
        if snapshot_state is None:
            return StoryState()
        return StoryState(
            location=snapshot_state.get("location", "未知地点"),
            time=snapshot_state.get("time", "未知时间"),
            mood=snapshot_state.get("mood", "未定义"),
            objective=snapshot_state.get("objective", "继续推进剧情"),
            inventory=snapshot_state.get("inventory", []),
            open_threads=snapshot_state.get("open_threads", []),
        )

    async def load_snapshot_state(
        self,
        story_id: UUID,
        branch_id: UUID,
        exclude_message_id: UUID | None = None,
    ) -> SnapshotState | None:
        cache_key = (story_id, branch_id, exclude_message_id)
        if cache_key in self.turn_context.snapshot_states:
            return self.turn_context.snapshot_states[cache_key]

        query = select(StoryStateSnapshot).where(
            StoryStateSnapshot.story_id == story_id,
            StoryStateSnapshot.branch_id == branch_id,
        )
        if exclude_message_id is not None:
            query = query.where(
                or_(
                    StoryStateSnapshot.message_id.is_(None),
                    StoryStateSnapshot.message_id != exclude_message_id,
                )
            )
        result = await self.session.execute(
            query.order_by(desc(StoryStateSnapshot.created_at)).limit(1)
        )
        snapshot = result.scalar_one_or_none()
        snapshot_state = dict(snapshot.state) if snapshot is not None else None
        self.turn_context.snapshot_states[cache_key] = snapshot_state
        return snapshot_state

    async def load_relationships(
        self,
        story_id: UUID,
        branch_id: UUID,
        exclude_message_id: UUID | None = None,
    ) -> list[RelationshipState]:
        snapshot_state = await self.load_snapshot_state(
            story_id,
            branch_id,
            exclude_message_id,
        )
        if snapshot_state is None:
            return []
        relationships = snapshot_state.get("relationships", [])
        if not isinstance(relationships, list):
            return []
        return [item for item in relationships if isinstance(item, dict)]
