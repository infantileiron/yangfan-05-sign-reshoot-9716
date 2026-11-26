"""Score today's photos and report the frozen tree's independent audit."""

from math import isfinite

from .features import AUDIT, DISPOSITION, FIT, QUEUE, TUNE, partition, vector
from .pruning import confirmed, fit_pruned, misrouting
from .routing import field_steps


def analyze(rows: list[dict], parameter: float) -> dict:
    if not isfinite(parameter) or not 1 <= parameter <= 8 or parameter != int(parameter):
        raise ValueError("漏派补拍的相对代价须为 1 到 8 的整数。")
    groups = partition(rows)
    model, tune_cost, alpha, original_leaves, leaf_counts = fit_pruned(groups[FIT], groups[TUNE], parameter)

    audit = groups[AUDIT]
    audit_actual = [confirmed(row) for row in audit]
    audit_predicted = model.predict([vector(row) for row in audit])
    missed, unnecessary = misrouting(audit_actual, audit_predicted)
    audit_cost = missed * parameter + unnecessary
    missed_only = sum(audit_actual) * parameter
    reshoot_all = len(audit_actual) - sum(audit_actual)

    queue = groups[QUEUE]
    queue_x = [vector(row) for row in queue]
    decisions = model.predict(queue_x)
    positions = model.apply(queue_x)
    paths = model.decision_path(queue_x)
    items = []
    for i, (row, decision, leaf) in enumerate(zip(queue, decisions, positions)):
        confirmed_counts = leaf_counts[int(leaf)]
        risk = round(100 * confirmed_counts[1] / confirmed_counts.total(), 1)
        condition, action = field_steps(model, queue_x[i], paths[i].indices.tolist(), bool(decision))
        items.append({
            "sample_id": row["sample_id"],
            "station": row["station"],
            "decision": DISPOSITION[decision],
            "risk": risk,
            "path": condition,
            "action": action,
        })
    items.sort(key=lambda row: (row["decision"] == "可用", -row["risk"], row["sample_id"]))
    to_reshoot = sum(row["decision"] == "补拍" for row in items)
    return {
        "summary": f"{len(items)} 张待处置照片，建议补拍 {to_reshoot} 张，{len(items) - to_reshoot} 张可进入编辑复核。",
        "metrics": [
            {"label": "补拍点位数", "value": to_reshoot},
            {"label": "复盘漏派", "value": missed},
            {"label": "复盘误派", "value": unnecessary},
            {"label": "复盘总误派代价", "value": int(audit_cost)},
        ],
        "rows": items,
        "notes": [
            f"建树 {len(groups[FIT])} / 定剪枝 {len(groups[TUNE])} / 独立复盘 {len(audit)} 条。",
            f"叶节点 {original_leaves} → {model.get_n_leaves()}，剪枝系数 {alpha:.4g}，定剪枝代价 {tune_cost:g}。",
            f"同一复盘组全部留用代价 {missed_only:g}，全部补拍代价 {reshoot_all:g}。",
            "占比用同叶的训练历史计数，派发依据模型中的代价加权结果。条件边界仅在显示时四舍五入。",
        ],
    }
