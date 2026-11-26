from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, new_id, utcnow


class DispatchList(Base):
    """An activated version of the night's reshoot list, produced by a succeeded run."""

    __tablename__ = "dispatch_lists"
    __table_args__ = (
        UniqueConstraint("night_id", "version", name="one_list_version_per_night"),
        UniqueConstraint("run_id", name="one_list_per_run"),
        Index(
            "one_active_dispatch_list_per_night", "night_id", unique=True,
            sqlite_where=text("state = 'active'"), postgresql_where=text("state = 'active'"),
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    night_id: Mapped[str] = mapped_column(ForeignKey("nights.id"), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"))
    version: Mapped[int]
    state: Mapped[str] = mapped_column(String(20), default="active")
    samples: Mapped[list] = mapped_column(JSON)
    trimmed: Mapped[list] = mapped_column(JSON, default=list)
    capacity: Mapped[int]
    dispatched: Mapped[int]
    actor: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Dispatch(Base):
    """One photo signed out for a reshoot on a given night. One row per photo per night."""

    __tablename__ = "dispatches"
    __table_args__ = (UniqueConstraint("night_id", "sample_id", name="one_dispatch_per_photo_per_night"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    night_id: Mapped[str] = mapped_column(ForeignKey("nights.id"), index=True)
    sample_id: Mapped[str] = mapped_column(String(120))
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"))
    review_id: Mapped[str] = mapped_column(ForeignKey("reviews.id"))
    list_id: Mapped[str | None] = mapped_column(ForeignKey("dispatch_lists.id"), nullable=True)
    reviewer: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
