from sqlalchemy import Column, Integer, DateTime, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from datetime import datetime

from src.middlewares.db.core import Base

class Stats(Base):
    __tablename__ = 'stats'

    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, nullable=False)
    user_id = Column(Integer, nullable=False)
    source_id = Column(Integer, ForeignKey('sources.id'), nullable=False)
    count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    source_rel = relationship("Source", back_populates="stats")

    __table_args__ = (
        UniqueConstraint('chat_id', 'user_id', 'source_id', name='uq_stats_chat_user_source'),
        Index('ix_stats_chat_id', chat_id),
    )