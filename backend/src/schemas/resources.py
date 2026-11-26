from datetime import datetime, timezone


def utc(value: datetime | None):
    return value.replace(tzinfo=timezone.utc).isoformat() if value else None


def dataset_view(dataset, include_rows=False):
    item = {
        "id": dataset.id, "name": dataset.name, "count": len(dataset.rows),
        "checksum": dataset.checksum, "author": dataset.author, "created_at": utc(dataset.created_at),
    }
    if include_rows:
        item["rows"] = dataset.rows
    return item


def run_view(run, include_result=False):
    item = {
        "id": run.id, "dataset_id": run.dataset_id, "night_id": run.night_id,
        "label": run.label, "parameter": run.parameter,
        "status": run.status, "error": run.error, "actor": run.actor,
        "created_at": utc(run.created_at), "started_at": utc(run.started_at),
        "finished_at": utc(run.finished_at),
    }
    if include_result:
        item["result"] = run.result
    return item


def review_view(review):
    return {
        "id": review.id, "run_id": review.run_id, "decision": review.decision,
        "samples": review.samples, "note": review.note, "reviewer": review.reviewer,
        "created_at": utc(review.created_at),
    }


def dispatch_list_view(listing, include_samples=False):
    item = {
        "id": listing.id, "night_id": listing.night_id, "run_id": listing.run_id,
        "version": listing.version, "state": listing.state,
        "count": len(listing.samples or []), "trimmed_count": len(listing.trimmed or []),
        "capacity": listing.capacity, "dispatched_at_build": listing.dispatched,
        "actor": listing.actor, "created_at": utc(listing.created_at),
    }
    if include_samples:
        item["samples"] = listing.samples or []
        item["trimmed"] = listing.trimmed or []
    return item


def night_view(night, active=None, lists=None, dispatch_registry=None, dispatched=None):
    item = {
        "id": night.id, "key": night.key, "name": night.name, "capacity": night.capacity,
        "dispatched": night.dispatched if dispatched is None else dispatched,
        "revision": night.revision, "author": night.author, "created_at": utc(night.created_at),
    }
    item["remaining"] = max(0, item["capacity"] - item["dispatched"])
    item["active"] = active
    if lists is not None:
        item["lists"] = lists
    if dispatch_registry is not None:
        item["dispatches"] = dispatch_registry
    return item


def audit_view(event):
    return {"actor": event.actor, "action": event.action, "subject": event.subject, "created_at": utc(event.created_at)}
