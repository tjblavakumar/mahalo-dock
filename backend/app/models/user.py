"""User model for authentication and role management."""

import enum
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, Integer, String

from app.core.database import Base


class UserRole(str, enum.Enum):
    """Available user roles in the system."""

    PRODUCT_MANAGER = "product_manager"
    DEVELOPER = "developer"
    EXECUTIVE = "executive"


class User(Base):
    """User model representing a MAHALO3 platform user."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    name = Column(String, nullable=False)
    role = Column(Enum(UserRole), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
