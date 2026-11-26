from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from src.config.settings import Session
from src.constants.workflow import ListState
from src.models.dispatch import Dispatch, DispatchList
from src.models.night import Night
from src.schemas.resources import dispatch_list_view, night_view
from src.services.audit import record


def require(db, night_id):
    night = db.get(Night, night_id)
    if night is None:
        raise HTTPException(404, "晚场不存在。")
    return night


def require_locked(db, night_id):
    """Read the night with its row lock so quota checks and activations serialize."""
    night = db.scalar(select(Night).where(Night.id == night_id).with_for_update())
    if night is None:
        raise HTTPException(404, "晚场不存在。")
    return night


def dispatched_ids(db, night_id):
    return set(db.scalars(select(Dispatch.sample_id).where(Dispatch.night_id == night_id)))


def active_list(db, night_id):
    return db.scalar(
        select(DispatchList).where(DispatchList.night_id == night_id, DispatchList.state == ListState.ACTIVE.value)
    )


def _detail(db, night):
    dispatches = db.scalars(
        select(Dispatch).where(Dispatch.night_id == night.id).order_by(Dispatch.created_at, Dispatch.sample_id)
    )
    lists = db.scalars(
        select(DispatchList).where(DispatchList.night_id == night.id).order_by(DispatchList.version.desc())
    )
    registry = [
        {"sample_id": row.sample_id, "reviewer": row.reviewer, "run_id": row.run_id,
         "list_id": row.list_id, "created_at": row.created_at.isoformat()}
        for row in dispatches
    ]
    active = active_list(db, night.id)
    return night_view(
        night, active=dispatch_list_view(active) if active else None,
        lists=[dispatch_list_view(item, include_samples=True) for item in lists],
        dispatch_registry=registry, dispatched=len(registry),
    )


def list_nights():
    with Session() as db:
        nights = db.scalars(select(Night).order_by(Night.created_at.desc(), Night.id.desc()))
        items = []
        for night in nights:
            active = active_list(db, night.id)
            count = db.scalar(select(func.count()).select_from(Dispatch).where(Dispatch.night_id == night.id))
            items.append(night_view(night, active=dispatch_list_view(active) if active else None, dispatched=count))
        return items


def details(night_id):
    with Session() as db:
        return _detail(db, require(db, night_id))


def create(body, actor):
    with Session.begin() as db:
        night = Night(key=body.key, name=body.name, capacity=body.capacity, author=actor)
        db.add(night)
        try:
            db.flush()
        except IntegrityError as exc:
            raise HTTPException(409, f"晚场编号 {body.key} 已存在。") from exc
        record(db, actor, "night_created", night.id)
        return _detail(db, night)


def summary(night, dispatched: int) -> dict:
    return {
        "id": night.id, "key": night.key, "name": night.name, "capacity": night.capacity,
        "dispatched": dispatched, "remaining": max(0, night.capacity - dispatched),
    }
