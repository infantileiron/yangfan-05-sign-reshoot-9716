"""Quota-aware reshoot dispatch shared by the run and by list activation.

Each queued photo inherits a calibrated risk ``p`` from its training leaf: the
unweighted share of historical reshoots there.  Dispatching it costs one wasted
trip when the photo is fine and saves ``penalty`` units when it is genuinely bad,
so its expected net benefit is ``p * penalty - (1 - p)``, positive exactly above
``1 / (penalty + 1)``.

At night the crew can only reshoot a limited number of photos, so several
policies are compared on the fixed-pruning history under that quota:

``cost_gate``  tree-positive photos above the cost threshold, best first
``tree``       every tree-positive photo, best first, cut by the quota
``top_risk``   the riskiest photos regardless of the tree's call
``none``       no reshoot at all

The winning policy is then applied to tonight's queue under the remaining quota
and, once the plan is final, checked against the independent review history.
"""

from .features import DISPOSITION, vector

POLICIES = ("cost_gate", "tree", "top_risk", "none")
POLICY_LABELS = {
    "cost_gate": "代价阈值前 N",
    "tree": "树判定前 N",
    "top_risk": "风险前 N",
    "none": "本晚不派",
}


def threshold(penalty: float) -> float:
    return 1.0 / (penalty + 1.0)


def leaf_profiles(model, rows, labels) -> dict[int, list[int]]:
    profiles: dict[int, list[int]] = {}
    for leaf, label in zip(model.apply([vector(row) for row in rows]), labels):
        counts = profiles.setdefault(int(leaf), [0, 0])
        counts[int(label)] += 1
    return profiles


def proportion(profiles, leaf) -> float:
    good, bad = profiles[int(leaf)]
    total = good + bad
    return 0.0 if not total else bad / total


def score(model, profiles, rows) -> list[dict]:
    if not rows:
        return []
    vectors = [vector(row) for row in rows]
    leaves = model.apply(vectors)
    predicted = model.predict(vectors)
    return [
        {
            "sample_id": row["sample_id"],
            "row": row,
            "leaf": int(leaf),
            "probability": proportion(profiles, leaf),
            "predicted": int(call),
        }
        for row, leaf, call in zip(rows, leaves, predicted)
    ]


def choose(items, policy: str, penalty: float, quota: int, exclude=frozenset()) -> list[dict]:
    """Pick up to ``quota`` photos, best risk first, never touching ``exclude``."""
    if policy == "none" or quota <= 0:
        return []
    pool = sorted(
        (item for item in items if item["sample_id"] not in exclude),
        key=lambda item: (-item["probability"], item["sample_id"]),
    )
    if policy == "top_risk":
        pass
    elif policy == "tree":
        pool = [item for item in pool if item["predicted"] == DISPOSITION.index("补拍")]
    else:  # cost_gate
        cutoff = threshold(penalty)
        pool = [item for item in pool if item["predicted"] == DISPOSITION.index("补拍")
                and item["probability"] > cutoff]
    return pool[:quota]


def evaluate(items, policy: str, penalty: float, quota: int) -> dict:
    """Score a policy against a labelled cohort and its scaled quota."""
    chosen = choose(items, policy, penalty, quota)
    picked = {item["sample_id"] for item in chosen}
    missed = 0
    unnecessary = 0
    for item in items:
        bad = item["row"].get("history_label") == DISPOSITION[1]
        if bad and item["sample_id"] not in picked:
            missed += 1
        if not bad and item["sample_id"] in picked:
            unnecessary += 1
    return {
        "dispatched": len(chosen),
        "missed": missed,
        "unnecessary": unnecessary,
        "cost": missed * penalty + unnecessary,
    }


def compare(items, penalty: float, quota: int) -> tuple[dict, list[dict]]:
    """Compare every policy on a cohort; return the winner and the full table."""
    ranked = []
    for position, policy in enumerate(POLICIES):
        result = {"key": policy, "label": POLICY_LABELS[policy], **evaluate(items, policy, penalty, quota)}
        ranked.append((result["cost"], result["dispatched"], position, result))
    winner = min(ranked, key=lambda entry: entry[:3])[3]
    return winner, [entry[3] for entry in ranked]


def quota_for(ratio: float, size: int) -> int:
    """Scale the night's dispatch rate onto a historical cohort."""
    return max(0, min(size, int(max(0.0, ratio) * size + 0.5)))


def replay(rows, policy: str, penalty: float, quota: int, exclude=frozenset()) -> list[dict]:
    """Re-select a stored result's rows at activation time.

    Stored rows already carry the calibrated ``probability`` and the tree's
    ``predicted`` call, so the same policy reproduces the plan under the quota
    that is actually left when the new version goes live.
    """
    items = [
        {
            "sample_id": row["sample_id"],
            "row": row,
            "probability": float(row["probability"]),
            "predicted": int(bool(row["predicted"])),
        }
        for row in rows
    ]
    return choose(items, policy, penalty, quota, exclude)
