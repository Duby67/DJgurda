from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship

from .base import Base

class Source(Base):
    __tablename__ = 'sources'

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)

    stats = relationship("Stats", back_populates="source_rel")
