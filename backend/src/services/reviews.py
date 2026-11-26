from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from src.config.settings import Session
from src.constants.workflow import Decision, Stage
from src.models.dispatch import Dispatch
from src.models.review import Review
from src.schemas.resources import review_view
from src.services import nights, runs
from src.services.audit import record


def lookup(db, run_id):
    return db.scalar(select(Review).where(Review.run_id == run_id))


def list_reviews():
    with Session() as db:
        return [review_view(review) for review in db.scalars(select(Review).order_by(Review.created_at.desc()))]


def _sign_out(db, run, samples, review, reviewer):
    """Claim the night's quota for each signed photo, never twice and never over."""
    if run.night_id is None:
        return
    night = nights.require_locked(db, run.night_id)
    sent = nights.dispatched_ids(db, run.night_id)
    repeated = sorted(set(samples) & sent)
    if repeated:
        raise HTTPException(409, f"这些照片本晚已经派过：{'、'.join(repeated)}。同一张照片不能重复派。")
    already = db.scalar(select(func.count()).select_from(Dispatch).where(Dispatch.night_id == night.id))
    if already + len(samples) > night.capacity:
        raise HTTPException(
            409,
            f"本晚还剩 {max(0, night.capacity - already)} 个补拍名额，签发 {len(samples)} 张会超额。请少选几张或改用其他版本。",
        )
    active = nights.active_list(db, run.night_id)
    for sample in samples:
        db.add(Dispatch(
            night_id=night.id, sample_id=sample, run_id=run.id, review_id=review.id,
            list_id=active.id if active else None, reviewer=reviewer,
        ))
    night.dispatched = already + len(samples)
    db.flush()


def sign(run_id, body, reviewer):
    with Session.begin() as db:
        run = runs.require(db, run_id)
        if run.status != Stage.SUCCEEDED.value:
            raise HTTPException(409, "计算成功后才能签审。")
        if lookup(db, run_id) is not None:
            raise HTTPException(409, "此计算单已有交接决定。")
        valid = {row["sample_id"] for row in run.result["rows"]}
        samples = list(dict.fromkeys(body.samples))
        if set(samples) - valid:
            raise HTTPException(422, "签审样本不属于这次计算。")
        if body.decision == Decision.APPROVE and not samples:
            raise HTTPException(422, "签发至少需要勾选一条结果。")
        if body.decision == Decision.APPROVE and run.night_id:
            nights.require_locked(db, run.night_id)  # lock order: night then review row
        review = Review(run_id=run_id, decision=body.decision.value, samples=samples, note=body.note, reviewer=reviewer)
        db.add(review)
        record(db, reviewer, f"review_{body.decision.value}", run_id)
        try:
            db.flush()
        except IntegrityError as exc:
            raise HTTPException(409, "此计算单已有交接决定。") from exc
        if body.decision == Decision.APPROVE:
            _sign_out(db, run, samples, review, reviewer)
        return review_view(review)
