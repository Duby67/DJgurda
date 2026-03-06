"""
Базовый класс для моделей SQLAlchemy.

Все модели должны наследоваться от этого класса.
"""

from sqlalchemy.orm import declarative_base

Base = declarative_base()
