"""Feature definitions and independent cohorts for sign photo inspection."""

from math import isfinite

FEATURES = (
    ("contrast", "文字对比度", 1, "关/移近处溢光或调整站位，提高字底对比"),
    ("glare", "亮斑覆盖", 100, "离开正对灯膜的机位，侧移后避开亮斑"),
    ("sharpness", "边缘锐度", 100, "固定手机并锁焦到箭头尖再拍"),
    ("margin", "最小边距", 50, "退半步纳入完整牌面四边后重拍"),
)

FIT = "建树历史"
TUNE = "定剪枝历史"
AUDIT = "复盘历史"
QUEUE = "待处置"
DISPOSITION = ("可用", "补拍")


def vector(row: dict) -> list[float]:
    values = [row[key] for key, _, _, _ in FEATURES]
    for value, (_, label, high, _) in zip(values, FEATURES):
        if not isfinite(value) or not 0 <= value <= high:
            raise ValueError(f"{row['sample_id']} 的{label}须介于 0 和 {high}。")
    return values


def partition(rows: list[dict]) -> dict[str, list[dict]]:
    groups = {stage: [] for stage in (FIT, TUNE, AUDIT, QUEUE)}
    identifiers = set()
    for row in rows:
        identifier = row["sample_id"]
        if identifier in identifiers:
            raise ValueError(f"照片号 {identifier} 重复。")
        identifiers.add(identifier)
        stage = row["stage"]
        label = row.get("history_label")
        if stage == QUEUE and label is not None:
            raise ValueError(f"{identifier} 属于待处置组，编辑定案须留空。")
        if stage != QUEUE and label not in DISPOSITION:
            raise ValueError(f"{identifier} 尚缺历史编辑定案。")
        groups[stage].append(row)

    for stage in (FIT, TUNE, AUDIT):
        cohort = groups[stage]
        if len(cohort) < 8 or {row["history_label"] for row in cohort} != set(DISPOSITION):
            raise ValueError(f"{stage}至少需要 8 条记录，且同时包含可用和补拍。")
        cohort.sort(key=lambda row: row["sample_id"])
    if not groups[QUEUE]:
        raise ValueError("需要至少一张待处置照片。")
    return groups
