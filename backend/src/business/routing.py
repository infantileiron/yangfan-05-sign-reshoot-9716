"""Turn actual tree paths into photo-specific field instructions."""

from .features import FEATURES


def field_steps(model, values: list[float], path: list[int], should_reshoot: bool) -> tuple[str, str]:
    conditions = []
    cues = []
    tree = model.tree_
    for node, child in zip(path, path[1:]):
        feature = int(tree.feature[node])
        key, label, _, advice = FEATURES[feature]
        threshold = float(tree.threshold[node])
        goes_left = child == tree.children_left[node]
        entered = "≤" if goes_left else ">"
        conditions.append(f"{label} {values[feature]:.3g} {entered} {threshold:.4g}")
        on_defect_side = not goes_left if key == "glare" else goes_left
        if on_defect_side and advice not in cues:
            cues.append(advice)
    action = "核对箭头与点位后留用"
    if should_reshoot:
        action = "；".join(cues[:2]) if cues else "回点位核对字边、亮斑和完整边框后重拍"
    return " → ".join(conditions) or "根节点规则", action
