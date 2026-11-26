"""Train cost-weighted CART and select its size using a separate cohort."""

from collections import Counter, defaultdict

from sklearn.tree import DecisionTreeClassifier

from .features import DISPOSITION, vector


def confirmed(row: dict) -> int:
    return DISPOSITION.index(row["history_label"])


def misrouting(actual, predicted) -> tuple[int, int]:
    missed = 0
    unnecessary = 0
    for expected, decision in zip(actual, predicted):
        missed += int(expected == 1 and decision == 0)
        unnecessary += int(expected == 0 and decision == 1)
    return missed, unnecessary


def fit_pruned(fit: list[dict], tune: list[dict], penalty: float):
    x_fit, y_fit = [vector(row) for row in fit], [confirmed(row) for row in fit]
    x_tune, y_tune = [vector(row) for row in tune], [confirmed(row) for row in tune]
    weights = [penalty if label else 1 for label in y_fit]
    settings = {"random_state": 2505, "min_samples_leaf": 5, "max_depth": 5}
    base = DecisionTreeClassifier(**settings)
    alphas = base.cost_complexity_pruning_path(x_fit, y_fit, sample_weight=weights).ccp_alphas
    candidates = []
    for alpha in sorted(set(map(float, alphas))):
        model = DecisionTreeClassifier(**settings, ccp_alpha=alpha)
        model.fit(x_fit, y_fit, sample_weight=weights)
        missed, unnecessary = misrouting(y_tune, model.predict(x_tune))
        tune_cost = missed * penalty + unnecessary
        candidates.append((tune_cost, model.get_n_leaves(), alpha, model))

    tune_cost, _, alpha, selected = min(candidates, key=lambda item: item[:3])
    leaf_counts = defaultdict(Counter)
    for leaf, label in zip(selected.apply(x_fit), y_fit):
        leaf_counts[int(leaf)][label] += 1
    return selected, tune_cost, alpha, candidates[0][1], leaf_counts
