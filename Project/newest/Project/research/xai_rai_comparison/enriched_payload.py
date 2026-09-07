"""Phase 2: turn one raw NSL-KDD event into the enriched JSON payloads the LLM
orchestrator consumes -- mathematical evidence (xai_evidence) plus the model's global
track record (rai_metadata), no rule-based decision logic here."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import shap
import torch

from models import _AutoencoderNet

ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts" / "nsl_kdd"


@dataclass
class LoadedArtifacts:
    manifest: dict
    if_model: object
    ae_net: _AutoencoderNet
    scaler: object
    encoder: object
    shap_explainer: shap.TreeExplainer


_ARTIFACTS: LoadedArtifacts | None = None


def load_artifacts() -> LoadedArtifacts:
    """Loads once per process; Phase 4 scores many events without re-reading disk."""
    global _ARTIFACTS
    if _ARTIFACTS is not None:
        return _ARTIFACTS

    manifest = json.loads((ARTIFACTS_DIR / "manifest.json").read_text(encoding="utf-8"))
    if_model = joblib.load(ARTIFACTS_DIR / "isolation_forest.pkl")
    scaler = joblib.load(ARTIFACTS_DIR / "scaler.pkl")
    encoder = joblib.load(ARTIFACTS_DIR / "encoder.pkl")

    ae_net = _AutoencoderNet(manifest["input_dim"], tuple(manifest["ae_hidden_dims"]))
    ae_net.load_state_dict(torch.load(ARTIFACTS_DIR / "autoencoder.pt"))
    ae_net.eval()

    _ARTIFACTS = LoadedArtifacts(
        manifest=manifest,
        if_model=if_model,
        ae_net=ae_net,
        scaler=scaler,
        encoder=encoder,
        shap_explainer=shap.TreeExplainer(if_model),
    )
    return _ARTIFACTS


def _build_feature_vector(raw_event: pd.Series, artifacts: LoadedArtifacts) -> np.ndarray:
    """Same transform as data_pipeline.load_nsl_kdd()'s build_matrix(), applied to a
    single new raw event via the persisted (already-fitted) scaler/encoder."""
    frame = raw_event.to_frame().T
    numeric = artifacts.scaler.transform(frame[artifacts.manifest["numeric_cols"]])
    categorical = artifacts.encoder.transform(frame[artifacts.manifest["categorical_cols"]])
    return np.hstack([numeric, categorical])[0]


def _top3_if(x: np.ndarray, artifacts: LoadedArtifacts) -> dict[str, float]:
    # SHAP TreeExplainer: exact per-event feature attribution for a tree ensemble --
    # signed contribution of each feature to this event's anomaly score.
    shap_values = artifacts.shap_explainer.shap_values(x.reshape(1, -1))[0]
    order = np.argsort(-np.abs(shap_values))[:3]
    return {artifacts.manifest["feature_names"][i]: float(shap_values[i]) for i in order}


def _top3_ae(x: np.ndarray, artifacts: LoadedArtifacts) -> dict[str, float]:
    # Feature-level reconstruction error: squared distance between input and the
    # autoencoder's reconstruction, per feature -- large values are the features the
    # model found least "normal-looking" for this event.
    with torch.no_grad():
        x_t = torch.tensor(x, dtype=torch.float32).unsqueeze(0)
        reconstruction = artifacts.ae_net(x_t).squeeze(0).numpy()
    per_feature_error = (x - reconstruction) ** 2
    order = np.argsort(-per_feature_error)[:3]
    return {artifacts.manifest["feature_names"][i]: float(per_feature_error[i]) for i in order}


def generate_enriched_payload(event: pd.Series, event_id: str) -> tuple[dict, dict]:
    """Returns (isolation_forest_payload, autoencoder_payload) for one raw event."""
    artifacts = load_artifacts()
    x = _build_feature_vector(event, artifacts)

    if_score = float(-artifacts.if_model.decision_function(x.reshape(1, -1))[0])
    with torch.no_grad():
        x_t = torch.tensor(x, dtype=torch.float32).unsqueeze(0)
        ae_score = float(torch.mean((artifacts.ae_net(x_t) - x_t) ** 2).item())

    thresholds = artifacts.manifest["thresholds"]
    rai = artifacts.manifest["rai_metadata"]

    if_predicted_class = "anomaly" if if_score >= thresholds["Isolation_Forest"] else "normal"
    ae_predicted_class = "anomaly" if ae_score >= thresholds["Autoencoder"] else "normal"

    # Cross-model signal: each model's own output (score + predicted class) attached to
    # BOTH payloads, so an alert triggered by one model still carries what the other model
    # itself produced for the same event -- lets XAI/RAI comparison and the LLM reason
    # about IF-vs-AE agreement/disagreement, not just the triggering model in isolation.
    cross_model_signal = {
        "isolation_forest_anomaly_score": if_score,
        "isolation_forest_predicted_class": if_predicted_class,
        "autoencoder_reconstruction_error": ae_score,
        "autoencoder_predicted_class": ae_predicted_class,
    }

    if_payload = {
        "alert_id": f"{event_id}-if",
        "dataset_name": artifacts.manifest["dataset_name"],
        "triggering_model": "Isolation_Forest",
        "anomaly_score": if_score,
        "predicted_class": if_predicted_class,
        "xai_evidence": _top3_if(x, artifacts),
        "rai_metadata": rai["Isolation_Forest"],
        "cross_model_signal": cross_model_signal,
    }
    ae_payload = {
        "alert_id": f"{event_id}-ae",
        "dataset_name": artifacts.manifest["dataset_name"],
        "triggering_model": "Autoencoder",
        "anomaly_score": ae_score,
        "predicted_class": ae_predicted_class,
        "xai_evidence": _top3_ae(x, artifacts),
        "rai_metadata": rai["Autoencoder"],
        "cross_model_signal": cross_model_signal,
    }
    return if_payload, ae_payload
