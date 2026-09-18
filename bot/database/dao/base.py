from sqlalchemy import insert, select

from bot.database.database import async_session_maker


class BaseDAO:
    model = None

    @classmethod
    async def find_by_id(cls, model_id: int):
        async with async_session_maker() as session:
            query = select(cls.model).filter_by(id=model_id)
            result = await session.execute(query)
            return result.scalar_one_or_none()

    @classmethod
    async def find_one_or_none(cls, **filter_by):
        async with async_session_maker() as session:
            query = select(cls.model).filter_by(**filter_by)
            result = await session.execute(query)
            return result.scalar_one_or_none()

    @classmethod
    async def find_all(cls, **filter_by):
        async with async_session_maker() as session:
            query = select(cls.model).filter_by(**filter_by)
            result = await session.execute(query)
            return result.scalars().all()

    @classmethod
    async def add(cls, **data):
        try:
            query = insert(cls.model).values(**data).returning(cls.model.id)
            async with async_session_maker() as session:
                result = await session.execute(query)
                await session.commit()
                return result.mappings().first()

        except Exception as error:
            return None

    @classmethod
    async def delete(cls, **data):
        async with async_session_maker() as session:
            query = await session.execute(select(cls.model).filter_by(**data))
            result = query.scalars().first()
            if result:
                await session.delete(result)
                await session.commit()
                return result
            return None

    @classmethod
    async def update(cls, model_id: int, **data):
        async with async_session_maker() as session:
            query = await session.execute(select(cls.model).filter_by(id=model_id))
            result = query.scalars().first()
            if result:
                for key, value in data.items():
                    setattr(result, key, value)
                await session.commit()
                return result
            return None
