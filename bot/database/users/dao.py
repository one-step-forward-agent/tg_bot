from bot.database.dao.base import BaseDAO
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, or_, select

from bot.database.database import async_session_maker
from bot.database.users.models import ConversationMessage, Event, User

class UserDAO(BaseDAO):
    model = User


class ConversationDAO(BaseDAO):
    model = ConversationMessage

    @classmethod
    async def recent_context(cls, user_id: int, limit: int = 12) -> list[ConversationMessage]:
        async with async_session_maker() as session:
            result = await session.execute(
                select(cls.model)
                .where(cls.model.user_id == user_id)
                .order_by(cls.model.created_at.desc(), cls.model.id.desc())
                .limit(limit)
            )
            return list(reversed(result.scalars().all()))

    @classmethod
    async def prune(cls, user_id: int, days: int = 30) -> None:
        async with async_session_maker() as session:
            await session.execute(
                delete(cls.model).where(
                    cls.model.user_id == user_id,
                    cls.model.created_at < datetime.now(timezone.utc) - timedelta(days=days),
                )
            )
            await session.commit()


class EventDAO(BaseDAO):
    model = Event

    @classmethod
    async def searchable_for_user(
        cls,
        user_id: int,
        since: datetime,
        until: datetime | None = None,
        keywords: list[str] | None = None,
        limit: int = 100,
    ):
        async with async_session_maker() as session:
            conditions = [cls.model.user_id == user_id, cls.model.starts_at >= since]
            if until is not None:
                conditions.append(cls.model.starts_at < until)
            if keywords:
                conditions.extend(
                    or_(
                        *[
                            column.ilike(f"%{keyword}%")
                            for column in (cls.model.title, cls.model.description, cls.model.location)
                        ]
                    )
                    for keyword in keywords
                )
            result = await session.execute(
                select(cls.model)
                .where(*conditions)
                .order_by(cls.model.starts_at)
                .limit(limit)
            )
            return result.scalars().all()

    @classmethod
    async def due_for_reminder(cls, now: datetime):
        async with async_session_maker() as session:
            result = await session.execute(
                select(Event).where(
                    Event.starts_at >= now,
                    Event.reminder_minutes.is_not(None),
                    Event.reminder_sent.is_(False),
                )
            )
            return [
                event
                for event in result.scalars().all()
                if event.starts_at - timedelta(minutes=event.reminder_minutes) <= now
            ]
