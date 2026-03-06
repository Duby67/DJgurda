"""
Модель источников контента.

Содержит информацию о поддерживаемых платформах (YouTube, TikTok и т.д.).
"""

from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship

from .base import Base

class Source(Base):
    """Класс `Source`."""
    __tablename__ = 'sources'

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)

    # Связь с статистикой
    stats = relationship("Stats", back_populates="source_rel")
