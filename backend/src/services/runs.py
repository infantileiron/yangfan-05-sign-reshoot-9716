import logging

from fastapi import HTTPException
from redis.exceptions import RedisError
from sqlalchemy import select

from src.business.profile import PROFILE
from src.config.settings import Session, redis
from src.models.run import Run
from src.schemas.resources import run_view
from src.services import datasets, nights
from src.services.audit import record

WAKE_KEY = "workbench:wake"
logger = logging.getLogger(__name__)


def require(db, run_id):
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(404, "计算单不存在。")
    return run


def list_runs():
    with Session() as db:
        return [run_view(run) for run in db.scalars(select(Run).order_by(Run.created_at.desc(), Run.id.desc()))]


def submit(body, actor):
    control = PROFILE["parameter"]
    if not control["min"] <= body.parameter <= control["max"]:
        raise HTTPException(422, f"「{control['label']}」超出允许范围。")
    with Session.begin() as db:
        datasets.require(db, body.dataset_id)
        night = nights.require_locked(db, body.night_id) if body.night_id else None
        run = Run(dataset_id=body.dataset_id, night_id=night.id if night else None,
                  label=body.label, parameter=body.parameter, actor=actor)
        db.add(run)
        db.flush()
        record(db, actor, "run_queued", run.id)
        response = run_view(run)
    _wake(run.id)
    return response


def recompute(run_id, actor, dataset_id=None, parameter=None):
    """Queue a fresh attempt, optionally with late-arriving data.

    The previous dispatch list is never touched, so a failed recompute leaves the
    crew on the list they already have and the same command can simply be retried.
    """
    with Session.begin() as db:
        source = require(db, run_id)
        if source.night_id:
            nights.require_locked(db, source.night_id)
        target_dataset = dataset_id or source.dataset_id
        target_parameter = source.parameter if parameter is None else parameter
        try:
            datasets.require(db, target_dataset)
        except HTTPException as exc:
            raise HTTPException(409, "补录的数据版本不存在，请重新导入后再提交计算。") from exc
        control = PROFILE["parameter"]
        if not control["min"] <= target_parameter <= control["max"]:
            raise HTTPException(422, f"「{control['label']}」超出允许范围。")
        run = Run(dataset_id=target_dataset, night_id=source.night_id, label=source.label,
                  parameter=target_parameter, actor=actor)
        db.add(run)
        db.flush()
        record(db, actor, "run_requeued", run.id)
        response = run_view(run)
    _wake(run.id)
    return response


def _wake(run_id):
    try:
        with redis.pipeline() as commands:
            commands.lpush(WAKE_KEY, run_id)
            commands.ltrim(WAKE_KEY, 0, 99)
            commands.execute()
    except RedisError:
        logger.warning("Redis wake signal failed for %s. Worker will poll the database.", run_id)
