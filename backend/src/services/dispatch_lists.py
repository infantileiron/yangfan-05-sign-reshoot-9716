"""Activating a succeeded run as the night's dispatch list.

Activation is the only place a run's plan becomes a list the crew may run.  It
locks the night row, re-checks the remaining quota against photos already signed
out, trims the new plan to that quota and supersedes the previous version in the
same transaction, so the night never exceeds its capacity and never shows two
active lists at once.
"""

import logging

from fastapi import HTTPException
from sqlalchemy import func, select

from src.business.quota import replay
from src.config.settings import Session
from src.constants.workflow import ListState, Stage
from src.models.dispatch import Dispatch, DispatchList
from src.models.run import Run
from src.schemas.resources import dispatch_list_view
from src.services import nights
from src.services.audit import record

logger = logging.getLogger(__name__)


def current(night_id):
    with Session.begin() as db:
        night = nights.require(db, night_id)
        active = nights.active_list(db, night_id)
        count = db.scalar(select(func.count()).select_from(Dispatch).where(Dispatch.night_id == night_id))
        return {
            "night": nights.summary(night, count),
            "active": dispatch_list_view(active, include_samples=True) if active else None,
        }


def current_active(db, night_id):
    nights.require(db, night_id)
    return nights.active_list(db, night_id)


def activate(night_id, run_id, actor):
    with Session.begin() as db:
        night = nights.require_locked(db, night_id)
        run = db.get(Run, run_id)
        if run is None:
            raise HTTPException(404, "计算单不存在。")
        if run.night_id != night_id:
            raise HTTPException(422, "此计算单不属于该晚场。")
        if run.status != Stage.SUCCEEDED.value or not run.result:
            raise HTTPException(409, "只有计算成功的计算单才能启用为新版清单。")
        already = db.scalar(select(DispatchList).where(DispatchList.run_id == run_id))
        if already is not None:
            raise HTTPException(409, "该计算单已用于一版清单，请重新计算后再启用。")

        dispatched = db.scalar(select(func.count()).select_from(Dispatch).where(Dispatch.night_id == night_id))
        sent = nights.dispatched_ids(db, night_id)
        remaining = max(0, night.capacity - dispatched)
        plan = run.result["quota"]
        rows = [row for row in run.result["rows"] if row["sample_id"] not in sent]
        selected = replay(rows, plan["policy"], plan["penalty"], remaining)
        chosen = {item["sample_id"] for item in selected}
        trimmed = [row["sample_id"] for row in rows if row["decision"] != "可用" and row["sample_id"] not in chosen]

        active = nights.active_list(db, night_id)
        if active is not None:
            active.state = ListState.SUPERSEDED.value
            db.flush()
        version = (db.scalar(select(func.max(DispatchList.version)).where(DispatchList.night_id == night_id)) or 0) + 1
        listing = DispatchList(
            night_id=night_id, run_id=run_id, version=version, state=ListState.ACTIVE.value,
            samples=[item["sample_id"] for item in selected], trimmed=trimmed,
            capacity=night.capacity, dispatched=dispatched, actor=actor,
        )
        db.add(listing)
        db.flush()
        night.revision += 1
        record(db, actor, "dispatch_list_activated", listing.id)
        return dispatch_list_view(listing, include_samples=True)
