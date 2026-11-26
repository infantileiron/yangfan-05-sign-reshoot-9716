from datetime import datetime

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, new_id, utcnow


class Night(Base):
    """A single evening show with a fixed number of reshoots the crew can run."""

    __tablename__ = "nights"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    key: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    capacity: Mapped[int]
    dispatched: Mapped[int] = mapped_column(default=0)
    revision: Mapped[int] = mapped_column(default=0)
    author: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
