from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import RunConfig
from data_pipeline import PreparedDataset, load_credit_card_fraud, load_nsl_kdd
from evaluation import unified_evaluate
from models import AutoencoderModel, IsolationForestModel
from rai_analysis import fairness_report, robustness_report, transparency_report
from xai_analysis import explain_autoencoder, explain_isolation_forest

DATASET_LOADERS = {
    "nsl_kdd": load_nsl_kdd,
    "credit_card_fraud": load_credit_card_fraud,
}


def _contamination_for(dataset_name: str, dataset: PreparedDataset, cfg: RunConfig) -> float:
    configured = cfg.contamination_nsl_kdd if dataset_name == "nsl_kdd" else cfg.contamination_credit_card
    if configured is not None:
        return configured
    # Estimated from the held-out label prior for reproducibility; a real deployment
    # would use a historical incident-rate estimate instead of the eval set itself.
    return float(np.mean(dataset.y_test))


def _run_model(model_name: str, dataset: PreparedDataset, cfg: RunConfig) -> dict:
    rng = np.random.default_rng(cfg.seed)
    contamination = _contamination_for(dataset.name, dataset, cfg)

    start = time.perf_counter()
    if model_name == "isolation_forest":
        model = IsolationForestModel(contamination=contamination, seed=cfg.seed)
    else:
        model = AutoencoderModel(input_dim=dataset.X_train.shape[1], cfg=cfg)
    model.fit(dataset.X_train)
    train_seconds = time.perf_counter() - start

    scores = model.anomaly_scores(dataset.X_test)
    metrics = unified_evaluate(dataset.y_test, scores, contamination)
    y_pred = (scores >= metrics["threshold"]).astype(int)

    sample_idx = rng.choice(len(dataset.X_test), size=min(cfg.shap_sample_size, len(dataset.X_test)), replace=False)
    background_idx = rng.choice(
        len(dataset.X_train), size=min(cfg.shap_background_size, len(dataset.X_train)), replace=False
    )
    X_sample = dataset.X_test[sample_idx]
    X_background = dataset.X_train[background_idx]

    if model_name == "isolation_forest":
        importance = explain_isolation_forest(model, X_sample, dataset.feature_names)
    else:
        importance = explain_autoencoder(model, X_background, X_sample, dataset.feature_names)

    robustness = robustness_report(
        model.anomaly_scores, dataset.X_test, metrics["threshold"], cfg.noise_std_fraction, cfg.seed
    )
    fairness = fairness_report(dataset.y_test, y_pred, dataset.group_test)
    transparency = transparency_report(importance)

    return {
        "train_seconds": train_seconds,
        "metrics": metrics,
        "xai_importance": importance.to_dict(),
        "rai": {"robustness": robustness, "fairness": fairness, "transparency": transparency},
    }


def _cross_model_deltas(dataset_result: dict) -> dict:
    if "isolation_forest" not in dataset_result or "autoencoder" not in dataset_result:
        return {}
    if_r, ae_r = dataset_result["isolation_forest"], dataset_result["autoencoder"]
    if_top = set(k for k, _ in if_r["rai"]["transparency"]["top_features"])
    ae_top = set(k for k, _ in ae_r["rai"]["transparency"]["top_features"])
    return {
        "roc_auc_delta_ae_minus_if": ae_r["metrics"]["roc_auc"] - if_r["metrics"]["roc_auc"],
        "f1_delta_ae_minus_if": ae_r["metrics"]["f1"] - if_r["metrics"]["f1"],
        "robustness_correlation_delta_ae_minus_if": (
            ae_r["rai"]["robustness"]["score_rank_correlation"] - if_r["rai"]["robustness"]["score_rank_correlation"]
        ),
        "transparency_feature_count_delta_ae_minus_if": (
            ae_r["rai"]["transparency"]["features_for_80pct_cumulative_importance"]
            - if_r["rai"]["transparency"]["features_for_80pct_cumulative_importance"]
        ),
        "top5_feature_overlap": sorted(if_top & ae_top),
        "top5_feature_disagreement": {"isolation_forest_only": sorted(if_top - ae_top), "autoencoder_only": sorted(ae_top - if_top)},
    }


def _write_markdown_summary(results: dict, output_dir: Path) -> None:
    lines = ["# XAI/RAI Model x Dataset Comparison", ""]
    for dataset_name, dataset_result in results.items():
        lines.append(f"## {dataset_name}")
        lines.append("")
        lines.append("| Model | ROC-AUC | F1 | Precision | Recall | Robustness (rank corr) | Flip rate | Fairness recall gap | Transparency (features for 80%) |")
        lines.append("|---|---|---|---|---|---|---|---|---|")
        for model_name in ("isolation_forest", "autoencoder"):
            if model_name not in dataset_result:
                continue
            r = dataset_result[model_name]
            m, rai = r["metrics"], r["rai"]
            lines.append(
                f"| {model_name} | {m['roc_auc']:.3f} | {m['f1']:.3f} | {m['precision']:.3f} | {m['recall']:.3f} "
                f"| {rai['robustness']['score_rank_correlation']:.3f} | {rai['robustness']['prediction_flip_rate']:.3f} "
                f"| {rai['fairness']['recall_gap'] if rai['fairness']['recall_gap'] is not None else 'n/a'} "
                f"| {rai['transparency']['features_for_80pct_cumulative_importance']}/{rai['transparency']['total_features']} |"
            )
        lines.append("")
        deltas = dataset_result.get("_cross_model_deltas", {})
        if deltas:
            lines.append("**Autoencoder vs Isolation Forest deltas:**")
            lines.append(f"- ROC-AUC: {deltas['roc_auc_delta_ae_minus_if']:+.3f}")
            lines.append(f"- F1: {deltas['f1_delta_ae_minus_if']:+.3f}")
            lines.append(f"- Robustness (score rank correlation): {deltas['robustness_correlation_delta_ae_minus_if']:+.3f}")
            lines.append(f"- Transparency (features needed for 80% importance): {deltas['transparency_feature_count_delta_ae_minus_if']:+d}")
            lines.append(f"- Top-5 SHAP features both models agree on: {deltas['top5_feature_overlap'] or 'none'}")
            lines.append("")
    (output_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def run(cfg: RunConfig, datasets: list[str]) -> dict:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = cfg.output_dir / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    results: dict = {}
    for dataset_name in datasets:
        loader = DATASET_LOADERS[dataset_name]
        try:
            dataset = loader(cfg)
        except FileNotFoundError as exc:
            print(f"[skip] {exc}")
            continue

        dataset_result: dict = {}
        for model_name in ("isolation_forest", "autoencoder"):
            print(f"[run] dataset={dataset_name} model={model_name}")
            dataset_result[model_name] = _run_model(model_name, dataset, cfg)

            importance_df = pd.Series(dataset_result[model_name]["xai_importance"]).sort_values(ascending=False)
            importance_df.to_csv(output_dir / f"{dataset_name}__{model_name}__shap_importance.csv", header=["mean_abs_shap"])

        dataset_result["_cross_model_deltas"] = _cross_model_deltas(dataset_result)
        results[dataset_name] = dataset_result

    (output_dir / "report.json").write_text(json.dumps(results, indent=2, default=float), encoding="utf-8")
    _write_markdown_summary(results, output_dir)
    print(f"\nReport written to {output_dir}")
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Isolation Forest vs Autoencoder XAI/RAI comparison (offline, Lab 2A)")
    parser.add_argument("--datasets", nargs="+", choices=list(DATASET_LOADERS), default=list(DATASET_LOADERS))
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--epochs", type=int, default=None)
    args = parser.parse_args()

    cfg = RunConfig()
    overrides = {}
    if args.output_dir:
        overrides["output_dir"] = args.output_dir
    if args.epochs:
        overrides["ae_epochs"] = args.epochs
    if overrides:
        cfg = replace(cfg, **overrides)

    run(cfg, args.datasets)


if __name__ == "__main__":
    main()
