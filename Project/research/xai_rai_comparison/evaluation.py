from __future__ import annotations

import numpy as np
from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score


def unified_evaluate(y_true: np.ndarray, scores: np.ndarray, contamination: float) -> dict:
    """Metrics are computed identically for every (dataset, model) pair so differences
    are attributable to the model/dataset, not to per-run metric choices.

    The classification threshold is derived from the expected anomaly rate
    (contamination), not by searching for the best F1 on the test set itself, since the
    latter would leak test labels into model selection and inflate both models equally
    but non-comparably across datasets with different anomaly rates.
    """
    threshold = float(np.percentile(scores, 100 * (1 - contamination)))
    y_pred = (scores >= threshold).astype(int)
    return {
        "roc_auc": float(roc_auc_score(y_true, scores)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "threshold": threshold,
        "predicted_anomaly_rate": float(np.mean(y_pred)),
    }
