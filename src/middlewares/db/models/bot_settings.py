from sqlalchemy import Column, Integer, Boolean, Index

from .base import Base

class BotSettings(Base):
    __tablename__ = 'bot_settings'

    chat_id = Column(Integer, primary_key=True)
    bot_enabled = Column(Boolean, nullable=False, default=True)
    errors_enabled = Column(Boolean, nullable=False, default=False)
    notifications_enabled = Column(Boolean, nullable=False, default=False)

    __table_args__ = (
        Index('ix_bot_settings_notifications_enabled', notifications_enabled),
    )