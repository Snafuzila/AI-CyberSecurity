"""Phase 1: train Isolation Forest + Autoencoder on NSL-KDD and persist everything
Phase 2 needs to score new events without retraining: the fitted models, the fitted
preprocessors (scaler/encoder), and a manifest of global RAI metrics and thresholds."""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import torch

from config import RunConfig
from data_pipeline import load_nsl_kdd
from evaluation import unified_evaluate
from models import AutoencoderModel, IsolationForestModel
from rai_analysis import fairness_report

LAB_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"


def _false_positive_rate(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    negatives = y_true == 0
    return float(np.mean(y_pred[negatives] == 1)) if negatives.sum() > 0 else 0.0


def main() -> None:
    # credit_card_fraud_10k.csv (transaction_id/amount/merchant_category/.../is_fraud) has a
    # different schema than load_credit_card_fraud() expects (Kaggle's Time/V1-V28/Amount/Class),
    # so it isn't wired in here -- NSL-KDD only, per the Phase 1 spec.
    cfg = RunConfig(nsl_kdd_dir=LAB_ROOT / "data")
    dataset = load_nsl_kdd(cfg)
    out_dir = ARTIFACTS_DIR / "nsl_kdd"
    out_dir.mkdir(parents=True, exist_ok=True)

    contamination = min(0.5, float(dataset.y_test.mean()))

    if_model = IsolationForestModel(contamination=contamination, seed=cfg.seed)
    if_model.fit(dataset.X_train)
    if_scores = if_model.anomaly_scores(dataset.X_test)
    if_metrics = unified_evaluate(dataset.y_test, if_scores, contamination)
    if_pred = (if_scores >= if_metrics["threshold"]).astype(int)
    if_fairness = fairness_report(dataset.y_test, if_pred, dataset.group_test)
    joblib.dump(if_model.model, out_dir / "isolation_forest.pkl")

    ae_model = AutoencoderModel(input_dim=dataset.X_train.shape[1], cfg=cfg)
    ae_model.fit(dataset.X_train)
    ae_scores = ae_model.anomaly_scores(dataset.X_test)
    ae_metrics = unified_evaluate(dataset.y_test, ae_scores, contamination)
    ae_pred = (ae_scores >= ae_metrics["threshold"]).astype(int)
    ae_fairness = fairness_report(dataset.y_test, ae_pred, dataset.group_test)
    torch.save(ae_model.net.state_dict(), out_dir / "autoencoder.pt")

    joblib.dump(dataset.scaler, out_dir / "scaler.pkl")
    joblib.dump(dataset.encoder, out_dir / "encoder.pkl")

    manifest = {
        "dataset_name": "nsl_kdd",
        "feature_names": dataset.feature_names,
        "numeric_cols": dataset.numeric_cols,
        "categorical_cols": dataset.categorical_cols,
        "input_dim": dataset.X_train.shape[1],
        "ae_hidden_dims": list(cfg.ae_hidden_dims),
        "thresholds": {
            "Isolation_Forest": if_metrics["threshold"],
            "Autoencoder": ae_metrics["threshold"],
        },
        # "Hardcoded" global test-set evaluation, attached identically to every event's
        # payload for a given model (Phase 2) rather than recomputed per event.
        "rai_metadata": {
            "Isolation_Forest": {
                "precision": if_metrics["precision"],
                "recall": if_metrics["recall"],
                "f1": if_metrics["f1"],
                "false_positive_rate": _false_positive_rate(dataset.y_test, if_pred),
                "fairness_gap": if_fairness["fpr_gap"],
            },
            "Autoencoder": {
                "precision": ae_metrics["precision"],
                "recall": ae_metrics["recall"],
                "f1": ae_metrics["f1"],
                "false_positive_rate": _false_positive_rate(dataset.y_test, ae_pred),
                "fairness_gap": ae_fairness["fpr_gap"],
            },
        },
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, default=float), encoding="utf-8")

    print(f"Isolation Forest -> F1={if_metrics['f1']:.3f}  FPR={manifest['rai_metadata']['Isolation_Forest']['false_positive_rate']:.3f}")
    print(f"Autoencoder      -> F1={ae_metrics['f1']:.3f}  FPR={manifest['rai_metadata']['Autoencoder']['false_positive_rate']:.3f}")
    print(f"Artifacts written to {out_dir}")


if __name__ == "__main__":
    main()
