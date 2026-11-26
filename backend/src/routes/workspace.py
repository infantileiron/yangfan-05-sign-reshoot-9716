from fastapi import APIRouter, Depends

from src.business.profile import PROFILE
from src.controllers import workspace
from src.routes.dependencies import analyst, current_account, reviewer
from src.schemas.requests import (
    ActivateRequest, Import, NightRequest, RecomputeRequest, ReviewRequest, RunRequest,
)
from src.services import audit, datasets, dispatch_lists, exports, nights, reviews, runs

router = APIRouter(dependencies=[Depends(current_account)])


@router.get("/profile")
def profile():
    return PROFILE


@router.get("/nights")
def list_nights():
    return nights.list_nights()


@router.post("/nights", status_code=201)
def create_night(body: NightRequest, account=Depends(analyst)):
    return nights.create(body, account.email)


router.add_api_route("/nights/{night_id}", nights.details, methods=["GET"])
router.add_api_route("/nights/{night_id}/dispatch-list", dispatch_lists.current, methods=["GET"])
router.add_api_route("/nights/{night_id}/dispatch.csv", exports.dispatch_list_download, methods=["GET"])


@router.post("/nights/{night_id}/dispatch-list", status_code=201)
def activate_list(night_id: str, body: ActivateRequest, account=Depends(reviewer)):
    return dispatch_lists.activate(night_id, body.run_id, account.email)


@router.get("/datasets")
def list_datasets():
    return datasets.list_datasets()


@router.post("/datasets")
def import_dataset(body: Import, account=Depends(analyst)):
    return datasets.ingest(body.name, body.csv, account.email)


router.add_api_route("/datasets/{dataset_id}", workspace.dataset_details, methods=["GET"])
router.add_api_route("/datasets/{dataset_id}/csv", workspace.dataset_csv, methods=["GET"])


@router.get("/runs")
def list_runs():
    return runs.list_runs()


@router.post("/runs", status_code=202)
def queue_run(body: RunRequest, account=Depends(analyst)):
    return runs.submit(body, account.email)


router.add_api_route("/runs/{run_id}", workspace.run_details, methods=["GET"])


@router.post("/runs/{run_id}/recompute", status_code=202)
def recompute_run(run_id: str, body: RecomputeRequest | None = None, account=Depends(analyst)):
    body = body or RecomputeRequest()
    return runs.recompute(run_id, account.email, body.dataset_id, body.parameter)


router.add_api_route("/runs/{run_id}/csv", exports.download, methods=["GET"])
router.add_api_route("/runs/{run_id}/handoff.csv", exports.signed_download, methods=["GET"])


@router.post("/runs/{run_id}/review", status_code=201)
def review_run(run_id: str, body: ReviewRequest, account=Depends(reviewer)):
    return reviews.sign(run_id, body, account.email)


router.add_api_route("/reviews", reviews.list_reviews, methods=["GET"])
router.add_api_route("/audit", audit.recent, methods=["GET"])
