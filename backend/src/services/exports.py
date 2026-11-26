from fastapi import HTTPException
from fastapi.responses import FileResponse, Response
from src.business.profile import PROFILE
from src.config.settings import ARTIFACTS, Session
from src.constants.workflow import Decision
from src.services import dispatch_lists, reviews, runs
from src.utils.csv_data import render_csv


def result_keys():
    return [column["key"] for column in PROFILE["result_columns"]]


def download(run_id):
    with Session() as db:
        run = runs.require(db, run_id)
        if not run.artifact:
            raise HTTPException(409, "计算完成后才能导出。")
        path = ARTIFACTS / run.artifact
        if not path.is_file():
            raise HTTPException(409, "找不到导出产物，请创建新的计算单。")
        return FileResponse(path, media_type="text/csv; charset=utf-8", filename=f"{run_id}-analysis.csv")


def signed_download(run_id):
    with Session() as db:
        run = runs.require(db, run_id)
        review = reviews.lookup(db, run_id)
        if review is None or review.decision != Decision.APPROVE.value:
            raise HTTPException(409, "复核员签发后才能下载交接单。")
        selected = set(review.samples)
        rows = [
            {**row, "reviewer": review.reviewer, "review_note": review.note}
            for row in run.result["rows"] if row["sample_id"] in selected
        ]
        contents = render_csv(rows, result_keys() + ["reviewer", "review_note"], protect=True)
        return Response(
            "\ufeff" + contents,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{run_id}-handoff.csv"'},
        )


LIST_KEYS = ["sample_id", "station", "decision", "risk", "path", "action"]


def dispatch_list_download(night_id):
    with Session() as db:
        listing = dispatch_lists.current_active(db, night_id)
        if listing is None:
            raise HTTPException(409, "本晚还没有启用的补拍清单。")
        run = runs.require(db, listing.run_id)
        rows = {row["sample_id"]: row for row in run.result["rows"]}
        picked = [rows[sample] for sample in listing.samples if sample in rows]
        contents = render_csv(picked, LIST_KEYS, protect=True)
        return Response(
            "﻿" + contents,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{night_id}-v{listing.version}-dispatch.csv"'},
        )
