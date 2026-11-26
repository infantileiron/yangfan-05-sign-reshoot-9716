"""Score today's photos, pick the best quota-limited dispatch and audit it."""

from math import isfinite

from .features import AUDIT, DISPOSITION, FIT, QUEUE, TUNE, partition, vector
from .pruning import confirmed, fit_pruned
from .quota import choose, compare, evaluate, quota_for, score, threshold
from .routing import field_steps


def _profiles(leaf_counts):
    return {int(leaf): [counts[0], counts[1]] for leaf, counts in leaf_counts.items()}


def _policy_rows(table):
    return [
        {"key": row["key"], "label": row["label"], "dispatched": row["dispatched"],
         "missed": row["missed"], "unnecessary": row["unnecessary"], "cost": int(row["cost"])}
        for row in table
    ]


def analyze(rows: list[dict], parameter: float, capacity: int | None = None,
            dispatched: int = 0, exclude=None) -> dict:
    if not isfinite(parameter) or not 1 <= parameter <= 8 or parameter != int(parameter):
        raise ValueError("漏派补拍的相对代价须为 1 到 8 的整数。")
    excluded = set(exclude or ())
    groups = partition(rows)
    model, tune_cost, alpha, original_leaves, leaf_counts = fit_pruned(groups[FIT], groups[TUNE], parameter)
    profiles = _profiles(leaf_counts)

    queue = [row for row in groups[QUEUE] if row["sample_id"] not in excluded]
    if not queue:
        raise ValueError("待处置照片都已签发，没有可再派的照片。")
    queue_scored = score(model, profiles, queue)
    total_queue = len(queue) + max(0, int(dispatched))
    ceiling = total_queue if capacity is None else max(0, int(capacity))
    remaining = max(0, min(len(queue), ceiling - max(0, int(dispatched))))
    planned = max(0, int(dispatched)) + remaining
    ratio = planned / total_queue

    tune_scored = score(model, profiles, groups[TUNE])
    tune_quota = quota_for(ratio, len(tune_scored))
    winner, table = compare(tune_scored, parameter, tune_quota)
    policy = winner["key"]

    audit = groups[AUDIT]
    audit_scored = score(model, profiles, audit)
    audit_quota = quota_for(ratio, len(audit_scored))
    audit_result = evaluate(audit_scored, policy, parameter, audit_quota)
    audit_actual = [confirmed(row) for row in audit]
    audit_baselines = {
        "all": {"dispatched": len(audit), "missed": 0,
                "unnecessary": len(audit) - sum(audit_actual),
                "cost": len(audit) - sum(audit_actual)},
        "none": {"dispatched": 0, "missed": sum(audit_actual), "unnecessary": 0,
                 "cost": int(sum(audit_actual) * parameter)},
        "tree": evaluate(audit_scored, "tree", parameter, len(audit)),
    }

    chosen = choose(queue_scored, policy, parameter, remaining)
    picked = {item["sample_id"] for item in chosen}
    tree_positive = [item for item in queue_scored if item["predicted"] == DISPOSITION.index("补拍")]
    cut = [item for item in tree_positive if item["sample_id"] not in picked]

    decisions = {item["sample_id"]: "补拍" for item in chosen}
    for item in cut:
        decisions[item["sample_id"]] = "候补"
    for item in queue_scored:
        decisions.setdefault(item["sample_id"], "可用")

    vectors = [vector(row) for row in queue]
    positions = model.apply(vectors)
    paths = model.decision_path(vectors)
    items = []
    for index, item in enumerate(queue_scored):
        row = item["row"]
        decision = decisions[row["sample_id"]]
        condition, action = field_steps(model, vectors[index], paths[index].indices.tolist(), decision == "补拍")
        leaf = int(positions[index])
        good, bad = profiles[leaf]
        items.append({
            "sample_id": row["sample_id"],
            "station": row["station"],
            "decision": decision,
            "risk": round(100 * bad / (good + bad), 1) if good + bad else 0.0,
            "path": condition,
            "action": action,
            "probability": round(bad / (good + bad), 6) if good + bad else 0.0,
            "predicted": 1 if item["predicted"] == DISPOSITION.index("补拍") else 0,
        })
    order = {"补拍": 0, "候补": 1, "可用": 2}
    items.sort(key=lambda row: (order[row["decision"]], -row["risk"], row["sample_id"]))
    ready = len(queue) - len(chosen) - len(cut)

    cutoff = threshold(parameter)
    return {
        "summary": f"{len(queue)} 张待处置照片，本晚名额可补拍 {len(chosen)} 张，"
                   f"{len(cut)} 张候补，{ready} 张可进入编辑复核。",
        "metrics": [
            {"label": "本晚名额", "value": len(queue) if capacity is None else capacity},
            {"label": "已签发", "value": dispatched},
            {"label": "还可派出", "value": remaining},
            {"label": "入选补拍", "value": len(chosen)},
            {"label": "候补", "value": len(cut)},
            {"label": "复盘漏派", "value": audit_result["missed"]},
            {"label": "复盘白跑", "value": audit_result["unnecessary"]},
            {"label": "复盘总误派代价", "value": int(audit_result["cost"])},
        ],
        "rows": items,
        "quota": {
            "capacity": len(queue) if capacity is None else capacity,
            "dispatched": dispatched,
            "remaining": remaining,
            "queue_size": len(queue),
            "ratio": round(ratio, 4),
            "penalty": parameter,
            "threshold": round(cutoff, 4),
            "policy": policy,
            "policy_label": winner["label"],
            "policies": _policy_rows(table),
            "tune_quota": tune_quota,
            "tune_cost": int(tune_cost),
            "audit": {
                "quota": audit_quota,
                "dispatched": audit_result["dispatched"],
                "missed": audit_result["missed"],
                "unnecessary": audit_result["unnecessary"],
                "cost": int(audit_result["cost"]),
            },
            "baselines": audit_baselines,
            "selected": [item["sample_id"] for item in chosen],
            "cut": [item["sample_id"] for item in cut],
        },
        "notes": [
            f"建树 {len(groups[FIT])} / 定剪枝 {len(groups[TUNE])} / 独立复盘 {len(audit)} 条。",
            f"叶节点 {original_leaves} → {model.get_n_leaves()}，剪枝系数 {alpha:.4g}，定剪枝代价 {tune_cost:g}。",
            f"今晚可派 {remaining} 张，按「{winner['label']}」在定剪枝历史上取得该限额下最低总误派代价 "
            f"（名额换算 {tune_quota} 张，代价 {winner['cost']:g}）。",
            f"独立复盘按同一限额 {audit_quota} 张验收：漏派 {audit_result['missed']}，白跑 "
            f"{audit_result['unnecessary']}，总代价 {audit_result['cost']:g}；全部留用代价 "
            f"{audit_baselines['none']['cost']}，全部补拍代价 {audit_baselines['all']['cost']}。",
            f"代价阈值约为 {cutoff:.3f}：同叶历史补拍占比高于它才值得多跑一趟。"
            "占比用同叶的训练历史计数，派发依据模型中的代价加权结果。条件边界仅在显示时四舍五入。",
        ],
    }
