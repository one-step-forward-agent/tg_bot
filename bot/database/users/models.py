from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, Text

from bot.database.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    tg_id = Column(BigInteger, nullable=False, unique=True)
    name = Column(Text, nullable=True)
    timezone = Column(Text, nullable=True)
    is_admin = Column(Boolean, default=False)


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    title = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    starts_at = Column(DateTime(timezone=True), nullable=False, index=True)
    ends_at = Column(DateTime(timezone=True), nullable=True)
    location = Column(Text, nullable=True)
    recurrence_rule = Column(Text, nullable=True)
    reminder_minutes = Column(Integer, nullable=True)
    reminder_sent = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    role = Column(Text, nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False, index=True)
