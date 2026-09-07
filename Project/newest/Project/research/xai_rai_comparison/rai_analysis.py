from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

MIN_GROUP_SAMPLES = 20  # below this, per-group recall/FPR is too noisy to report


def robustness_report(
    scorer: Callable[[np.ndarray], np.ndarray],
    X_test: np.ndarray,
    threshold: float,
    noise_std_fraction: float,
    seed: int,
) -> dict:
    """Measures how much anomaly scores and predictions change under small, realistic
    sensor noise (proportional to each feature's own spread, so scale differences
    between NSL-KDD and Credit Card Fraud features don't bias the comparison)."""
    rng = np.random.default_rng(seed)
    feature_std = X_test.std(axis=0)
    feature_std[feature_std == 0] = 1.0
    noise = rng.normal(0, 1, size=X_test.shape) * feature_std * noise_std_fraction
    X_perturbed = X_test + noise

    base_scores = scorer(X_test)
    perturbed_scores = scorer(X_perturbed)
    correlation, _ = spearmanr(base_scores, perturbed_scores)

    base_pred = base_scores >= threshold
    perturbed_pred = perturbed_scores >= threshold
    flip_rate = float(np.mean(base_pred != perturbed_pred))

    return {
        "score_rank_correlation": float(correlation),
        "prediction_flip_rate": flip_rate,
        "noise_std_fraction": noise_std_fraction,
    }


def fairness_report(y_true: np.ndarray, y_pred: np.ndarray, group_labels: pd.Series) -> dict:
    """group_labels is a proxy attribute (protocol_type / transaction-amount quartile),
    not a protected class — neither dataset carries demographic attributes. Reported as
    a subgroup performance-disparity check, not a legal fairness audit."""
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    per_group: dict[str, dict] = {}

    for group in pd.unique(group_labels):
        mask = (group_labels == group).to_numpy()
        count = int(mask.sum())
        if count < MIN_GROUP_SAMPLES:
            per_group[str(group)] = {"count": count, "insufficient_data": True}
            continue

        positives = mask & (y_true == 1)
        negatives = mask & (y_true == 0)
        recall = float(np.mean(y_pred[positives] == 1)) if positives.sum() > 0 else None
        fpr = float(np.mean(y_pred[negatives] == 1)) if negatives.sum() > 0 else None
        per_group[str(group)] = {"count": count, "recall": recall, "false_positive_rate": fpr}

    valid_recalls = [g["recall"] for g in per_group.values() if g.get("recall") is not None]
    valid_fprs = [g["false_positive_rate"] for g in per_group.values() if g.get("false_positive_rate") is not None]

    return {
        "proxy_attribute_note": "group_labels is a non-protected proxy attribute; see docstring",
        "per_group": per_group,
        "recall_gap": float(max(valid_recalls) - min(valid_recalls)) if len(valid_recalls) >= 2 else None,
        "fpr_gap": float(max(valid_fprs) - min(valid_fprs)) if len(valid_fprs) >= 2 else None,
    }


def _gini(values: np.ndarray) -> float:
    x = np.sort(np.asarray(values, dtype=float))
    n = len(x)
    total = x.sum()
    if n == 0 or total == 0:
        return 0.0
    index = np.arange(1, n + 1)
    return float((2 * np.sum(index * x) - (n + 1) * total) / (n * total))


def transparency_report(shap_importance: pd.Series, top_k: int = 5) -> dict:
    """Global-explanation concentration: a low feature count for 80% cumulative
    importance and a high Gini coefficient both indicate the model leans on a small,
    easily-communicable set of features (more transparent to a SOC analyst); the
    opposite indicates a diffuse, harder-to-summarize decision surface."""
    sorted_importance = shap_importance.sort_values(ascending=False)
    total = sorted_importance.sum()
    cumulative_share = sorted_importance.cumsum() / total if total > 0 else sorted_importance.cumsum()
    features_for_80pct = int(np.searchsorted(cumulative_share.to_numpy(), 0.8) + 1)

    return {
        "top_features": list(sorted_importance.head(top_k).items()),
        "features_for_80pct_cumulative_importance": features_for_80pct,
        "total_features": int(len(sorted_importance)),
        "gini_coefficient": _gini(sorted_importance.to_numpy()),
    }
