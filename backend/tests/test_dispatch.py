"""Integration tests for quota-limited reshoot dispatch.

Run from ``backend/`` with a reachable PostgreSQL:

    TEST_DATABASE_URL=postgresql+psycopg://studio:pw@127.0.0.1:55432/workbench pytest
"""

import json
import os
import threading

import fakeredis
import pytest

os.environ.setdefault("DATABASE_URL", os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://studio:pw@127.0.0.1:55432/workbench"))
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6379/0")
os.environ.setdefault("JWT_SECRET", "test-secret-value-that-is-long-enough-0123456789")
os.environ.setdefault("ARTIFACTS_DIR", "/tmp/sign-artifacts")
os.environ.setdefault("SEED_DEMO", "false")

import src.config.settings as settings  # noqa: E402

settings.redis = fakeredis.FakeRedis(decode_responses=True)
for module in ("src.services.runs", "src.services.dispatch_lists", "src.main", "src.services.executor"):
    imported = __import__(module, fromlist=["x"])
    if hasattr(imported, "redis"):
        imported.redis = settings.redis
    if hasattr(imported, "WAKE_KEY"):
        pass

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from migrations.bootstrap import migrate  # noqa: E402
from src.business.demo import demo_rows  # noqa: E402
from src.business.profile import PROFILE  # noqa: E402
from src.constants.workflow import Role  # noqa: E402
from src.main import app  # noqa: E402
from src.models.account import Account  # noqa: E402
from src.services import executor  # noqa: E402
from src.services.exports import LIST_KEYS  # noqa: E402
from src.utils.csv_data import render_csv  # noqa: E402
from src.utils.passwords import hash_password  # noqa: E402

PASSWORD = "Yangfan-demo-2026"
PASSWORD_HASH = hash_password(PASSWORD)


@pytest.fixture(scope="session")
def client():
    os.makedirs("/tmp/sign-artifacts", exist_ok=True)
    with settings.engine.begin() as connection:
        connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;"))
    migrate(settings.engine)
    with settings.Session.begin() as db:
        for role in Role:
            db.add(Account(email=f"{role.value}@test.local", role=role.value, password_hash=PASSWORD_HASH))
    with TestClient(app) as test_client:
        yield test_client


_tokens = {}


def token(client, role):
    if role not in _tokens:
        response = client.post("/api/auth/login", json={"email": f"{role}@test.local", "password": PASSWORD})
        assert response.status_code == 200, response.text
        _tokens[role] = {"Authorization": "Bearer " + response.json()["token"]}
    return _tokens[role]


def seed_dataset(client):
    keys = [column["key"] for column in PROFILE["columns"]]
    csv = render_csv(demo_rows(), keys)
    response = client.post("/api/datasets", json={"name": "demo", "csv": csv}, headers=token(client, "analyst"))
    assert response.status_code == 200, response.text
    return response.json()["id"]


def make_night(client, capacity, key):
    response = client.post("/api/nights", json={"key": key, "name": key, "capacity": capacity},
                           headers=token(client, "analyst"))
    assert response.status_code == 201, response.text
    return response.json()["id"]


def submit_and_drain(client, dataset_id, night_id, parameter=3, label="try"):
    response = client.post("/api/runs", json={
        "dataset_id": dataset_id, "night_id": night_id, "label": label, "parameter": parameter,
    }, headers=token(client, "analyst"))
    assert response.status_code == 202, response.text
    run_id = response.json()["id"]
    job = executor.claim()
    while job is not None and job[0] != run_id:
        executor.execute(job)
        job = executor.claim()
    assert job is not None, "run never became claimable"
    assert executor.execute(job)
    detail = client.get(f"/api/runs/{run_id}", headers=token(client, "analyst")).json()
    return detail


def test_analysis_respects_quota_and_reports_policies():
    from src.business.algorithm import analyze
    result = analyze(demo_rows(), 3, capacity=3, dispatched=0)
    assert len(result["quota"]["selected"]) == 3
    assert result["quota"]["audit"]["cost"] >= 0
    assert {row["key"] for row in result["quota"]["policies"]} == {"cost_gate", "tree", "top_risk", "none"}
    assert all(row["decision"] in {"补拍", "候补", "可用"} for row in result["rows"])
    text(json.dumps(result))


def test_signed_photos_hold_quota_and_activate_trims(client):
    dataset_id = seed_dataset(client)
    night_id = make_night(client, 4, "night-cap4")
    run = submit_and_drain(client, dataset_id, night_id)
    quota = run["result"]["quota"]
    assert quota["remaining"] == 4 and len(quota["selected"]) == 4

    listing = client.post(f"/api/nights/{night_id}/dispatch-list", json={"run_id": run["id"]},
                          headers=token(client, "reviewer"))
    assert listing.status_code == 201, listing.text
    assert len(listing.json()["samples"]) == 4

    first_two = listing.json()["samples"][:2]
    signed = client.post(f"/api/runs/{run['id']}/review", json={
        "decision": "approve", "samples": first_two, "note": "先派两张",
    }, headers=token(client, "reviewer"))
    assert signed.status_code == 201, signed.text

    night = client.get(f"/api/nights/{night_id}", headers=token(client, "viewer")).json()
    assert night["dispatched"] == 2 and night["remaining"] == 2

    rerun = submit_and_drain(client, dataset_id, night_id, label="rerun")
    assert rerun["result"]["quota"]["dispatched"] == 2
    assert rerun["result"]["quota"]["remaining"] == 2
    assert not set(first_two) & {row["sample_id"] for row in rerun["result"]["rows"]}
    assert len(rerun["result"]["quota"]["selected"]) == 2


def test_signing_never_exceeds_capacity(client):
    dataset_id = seed_dataset(client)
    night_id = make_night(client, 3, "night-cap3")
    run = submit_and_drain(client, dataset_id, night_id)
    ids = [row["sample_id"] for row in run["result"]["rows"] if row["decision"] == "补拍"]
    assert len(ids) == 3
    response = client.post(f"/api/runs/{run['id']}/review", json={
        "decision": "approve", "samples": ids, "note": "刚好用完",
    }, headers=token(client, "reviewer"))
    assert response.status_code == 201, response.text
    overdue = submit_and_drain(client, dataset_id, night_id, label="after")
    assert overdue["result"]["quota"]["remaining"] == 0
    assert overdue["result"]["quota"]["selected"] == []
    assert all(row["decision"] != "补拍" for row in overdue["result"]["rows"])


def test_activation_supersedes_and_rejects_duplicate_run(client):
    dataset_id = seed_dataset(client)
    night_id = make_night(client, 3, "night-version")
    first = submit_and_drain(client, dataset_id, night_id, label="v1")
    second = submit_and_drain(client, dataset_id, night_id, label="v2")
    one = client.post(f"/api/nights/{night_id}/dispatch-list", json={"run_id": first["id"]},
                      headers=token(client, "reviewer"))
    assert one.status_code == 201
    two = client.post(f"/api/nights/{night_id}/dispatch-list", json={"run_id": second["id"]},
                      headers=token(client, "reviewer"))
    assert two.status_code == 201, two.text
    assert two.json()["version"] == 2
    current = client.get(f"/api/nights/{night_id}/dispatch-list", headers=token(client, "viewer")).json()
    assert current["active"]["id"] == two.json()["id"]
    again = client.post(f"/api/nights/{night_id}/dispatch-list", json={"run_id": first["id"]},
                        headers=token(client, "reviewer"))
    assert again.status_code == 409


def test_failed_recompute_keeps_previous_list(client):
    dataset_id = seed_dataset(client)
    night_id = make_night(client, 2, "night-fail")
    good = submit_and_drain(client, dataset_id, night_id, label="good")
    active = client.post(f"/api/nights/{night_id}/dispatch-list", json={"run_id": good["id"]},
                         headers=token(client, "reviewer")).json()

    broken = demo_rows()
    for row in broken:
        if row["stage"] == "待处置":
            row["history_label"] = "可用"
    keys = [column["key"] for column in PROFILE["columns"]]
    imported = client.post("/api/datasets", json={"name": "broken", "csv": render_csv(broken, keys)},
                           headers=token(client, "analyst")).json()
    submitted = client.post("/api/runs", json={
        "dataset_id": imported["id"], "night_id": night_id, "label": "bad", "parameter": 3,
    }, headers=token(client, "analyst")).json()
    job = executor.claim()
    while job is not None and job[0] != submitted["id"]:
        executor.execute(job)
        job = executor.claim()
    executor.execute(job)
    failed = client.get(f"/api/runs/{submitted['id']}", headers=token(client, "analyst")).json()
    assert failed["status"] == "failed"

    still = client.get(f"/api/nights/{night_id}/dispatch-list", headers=token(client, "viewer")).json()
    assert still["active"]["id"] == active["id"]
    retry = submit_and_drain(client, dataset_id, night_id, label="retry")
    promoted = client.post(f"/api/nights/{night_id}/dispatch-list", json={"run_id": retry["id"]},
                           headers=token(client, "reviewer"))
    assert promoted.status_code == 201


def test_concurrent_sign_and_activation_never_overflow(client):
    dataset_id = seed_dataset(client)
    night_id = make_night(client, 4, "night-race")
    first = submit_and_drain(client, dataset_id, night_id, label="base")
    second = submit_and_drain(client, dataset_id, night_id, label="alt")
    pool = [row["sample_id"] for row in first["result"]["rows"] if row["decision"] == "补拍"]
    assert len(pool) == 4

    errors = []

    def sign():
        try:
            response = client.post(f"/api/runs/{first['id']}/review", json={
                "decision": "approve", "samples": pool[:3], "note": "并发签发",
            }, headers=token(client, "reviewer"))
            if response.status_code >= 500:
                errors.append(response.text)
        except Exception as exc:  # pragma: no cover - surfaced below
            errors.append(repr(exc))

    def activate():
        for run_id in (second["id"], first["id"]):
            try:
                response = client.post(f"/api/nights/{night_id}/dispatch-list", json={"run_id": run_id},
                                       headers=token(client, "reviewer"))
                if response.status_code >= 500:
                    errors.append(response.text)
            except Exception as exc:  # pragma: no cover - surfaced below
                errors.append(repr(exc))

    threads = [threading.Thread(target=sign), threading.Thread(target=activate)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors, errors

    night = client.get(f"/api/nights/{night_id}", headers=token(client, "viewer")).json()
    assert night["dispatched"] == 3
    assert night["dispatched"] <= night["capacity"]
    ids = [row["sample_id"] for row in night["dispatches"]]
    assert len(ids) == len(set(ids))


def test_second_signature_cannot_duplicate_photo(client):
    dataset_id = seed_dataset(client)
    night_id = make_night(client, 6, "night-dupe")
    first = submit_and_drain(client, dataset_id, night_id, label="a")
    second = submit_and_drain(client, dataset_id, night_id, label="b")
    target = [row["sample_id"] for row in first["result"]["rows"] if row["decision"] == "补拍"][:1]
    one = client.post(f"/api/runs/{first['id']}/review", json={
        "decision": "approve", "samples": target, "note": "第一单",
    }, headers=token(client, "reviewer"))
    assert one.status_code == 201, one.text
    two = client.post(f"/api/runs/{second['id']}/review", json={
        "decision": "approve", "samples": target, "note": "重复派同一张",
    }, headers=token(client, "reviewer"))
    assert two.status_code == 409, two.text
    night = client.get(f"/api/nights/{night_id}", headers=token(client, "viewer")).json()
    assert night["dispatched"] == 1
    assert [row["sample_id"] for row in night["dispatches"]] == target
    retry = client.post(f"/api/runs/{second['id']}/review", json={
        "decision": "hold", "samples": [], "note": "改暂缓",
    }, headers=token(client, "reviewer"))
    assert retry.status_code == 201, retry.text


def test_over_capacity_signature_rejected(client):
    dataset_id = seed_dataset(client)
    night_id = make_night(client, 1, "night-tight")
    run = submit_and_drain(client, dataset_id, night_id)
    ids = [row["sample_id"] for row in run["result"]["rows"]][:2]
    response = client.post(f"/api/runs/{run['id']}/review", json={
        "decision": "approve", "samples": ids, "note": "超名额",
    }, headers=token(client, "reviewer"))
    assert response.status_code == 409
    night = client.get(f"/api/nights/{night_id}", headers=token(client, "viewer")).json()
    assert night["dispatched"] == 0
    assert night["active"] is None
    retry = client.post(f"/api/runs/{run['id']}/review", json={
        "decision": "approve", "samples": ids[:1], "note": "只派一张",
    }, headers=token(client, "reviewer"))
    assert retry.status_code == 201, retry.text
    night = client.get(f"/api/nights/{night_id}", headers=token(client, "viewer")).json()
    assert night["dispatched"] == 1


def test_recompute_requeues_same_inputs(client):
    dataset_id = seed_dataset(client)
    night_id = make_night(client, 3, "night-recompute")
    run = submit_and_drain(client, dataset_id, night_id, label="recalc")
    response = client.post(f"/api/runs/{run['id']}/recompute", headers=token(client, "analyst"))
    assert response.status_code == 202, response.text
    clone = response.json()
    assert clone["id"] != run["id"]
    assert (clone["dataset_id"], clone["night_id"], clone["parameter"]) == (
        run["dataset_id"], run["night_id"], run["parameter"])
    job = executor.claim()
    while job is not None and job[0] != clone["id"]:
        executor.execute(job)
        job = executor.claim()
    assert job is not None and executor.execute(job)
    detail = client.get(f"/api/runs/{clone['id']}", headers=token(client, "analyst")).json()
    assert detail["status"] == "succeeded"
    alias = client.post("/api/runs", json={
        "dataset_id": dataset_id, "night_id": night_id, "label": "克隆名称", "parameter": 3,
    }, headers=token(client, "analyst"))
    assert alias.status_code == 202


def test_dispatch_list_download_matches_version(client):
    dataset_id = seed_dataset(client)
    night_id = make_night(client, 2, "night-export")
    run = submit_and_drain(client, dataset_id, night_id)
    activated = client.post(f"/api/nights/{night_id}/dispatch-list", json={"run_id": run["id"]},
                            headers=token(client, "reviewer"))
    assert activated.status_code == 201
    missing = client.get(f"/api/nights/{night_id}/dispatch.csv", headers=token(client, "viewer"))
    assert missing.status_code in (200, 409)
    other = make_night(client, 2, "night-export-empty")
    empty = client.get(f"/api/nights/{other}/dispatch.csv", headers=token(client, "viewer"))
    assert empty.status_code == 409
    export = client.get(f"/api/nights/{night_id}/dispatch.csv", headers=token(client, "viewer"))
    assert export.status_code == 200, export.text
    body = export.content.decode("utf-8-sig")
    header, *lines = body.strip().splitlines()
    assert header.split(",") == LIST_KEYS
    assert len(lines) == len(activated.json()["samples"])


def test_quota_scales_with_remaining_and_never_negative():
    from src.business.algorithm import analyze
    full = analyze(demo_rows(), 3, capacity=8, dispatched=0)
    assert full["quota"]["remaining"] == 8
    drained = analyze(demo_rows(), 3, capacity=8, dispatched=8)
    assert drained["quota"]["remaining"] == 0
    assert drained["quota"]["selected"] == []
    assert all(row["decision"] != "补拍" for row in drained["rows"])
    over = analyze(demo_rows(), 3, capacity=2, dispatched=5)
    assert over["quota"]["remaining"] == 0


def test_excluded_samples_are_not_reselected():
    from src.business.algorithm import analyze
    base = analyze(demo_rows(), 3, capacity=4, dispatched=0)
    sent = base["quota"]["selected"][:2]
    again = analyze(demo_rows(), 3, capacity=4, dispatched=2, exclude=sent)
    assert not set(sent) & set(again["quota"]["selected"])
    assert not set(sent) & {row["sample_id"] for row in again["rows"]}


def test_penalty_changes_threshold_and_selection():
    from src.business.algorithm import analyze
    low = analyze(demo_rows(), 1, capacity=4, dispatched=0)
    high = analyze(demo_rows(), 8, capacity=4, dispatched=0)
    assert low["quota"]["threshold"] > high["quota"]["threshold"]
    assert len(low["quota"]["selected"]) <= 4 and len(high["quota"]["selected"]) <= 4
