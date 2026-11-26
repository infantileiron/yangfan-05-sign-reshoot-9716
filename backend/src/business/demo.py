"""Create archived inspection outcomes and unreviewed field photos."""

from random import Random

from .features import AUDIT, FIT, QUEUE, TUNE

STATIONS = ("东遮廊", "南桥楼梯", "纸灯广场", "二号检票列", "小舞台", "绸檐入口", "铜灯引桥", "旧瓷市集")
CUTS = (0.42, 26, 47, 3.3)


def make_row(identifier: str, station: str, stage: str, values: tuple, label: str | None = None) -> dict:
    contrast, glare, sharpness, margin = values
    return {
        "sample_id": identifier,
        "station": station,
        "stage": stage,
        "contrast": contrast,
        "glare": glare,
        "sharpness": sharpness,
        "margin": margin,
        "history_label": label,
    }


def demo_rows() -> list[dict]:
    rng = Random(2026112505)
    rows = []
    for stage, prefix, count in ((FIT, "H", 96), (TUNE, "V", 32), (AUDIT, "A", 32)):
        for number in range(1, count + 1):
            contrast = round(rng.uniform(0.22, 0.94), 2)
            glare = round(rng.triangular(0, 67, 6), 1)
            sharpness = round(rng.uniform(32, 99), 1)
            margin = round(rng.uniform(1, 21), 1)
            cutoff_contrast, cutoff_glare, cutoff_sharpness, cutoff_margin = CUTS
            action = (
                (contrast < cutoff_contrast + rng.uniform(-0.06, 0.06) and glare > 10)
                or glare > cutoff_glare + rng.uniform(-6, 6)
                or sharpness < cutoff_sharpness + rng.uniform(-3, 3)
                or (margin < cutoff_margin + rng.uniform(-0.5, 0.5) and contrast < 0.65)
            )
            rows.append(make_row(
                f"HP-{prefix}-{number:03}", rng.choice(STATIONS), stage,
                (contrast, glare, sharpness, margin), "补拍" if action else "可用",
            ))

    queue = (
        (0.33, 67.0, 79.0, 12.0),
        (0.82, 2.0, 93.0, 12.0),
        (0.79, 8.4, 33.0, 10.1),
        (0.83, 5.8, 88.2, 9.4),
        (0.28, 29.1, 46.8, 2.3),
        (0.71, 15.2, 81.0, 14.1),
        (0.54, 13.0, 56.0, 1.6),
        (0.46, 34.7, 68.9, 10.2),
    )
    rows.extend(
        make_row(f"HP-Q-{i:02}", station, QUEUE, values)
        for i, (station, values) in enumerate(zip(STATIONS, queue), 1)
    )
    return rows
