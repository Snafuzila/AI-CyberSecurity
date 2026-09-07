from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

try:
    import shap
except ImportError as exc:  # pragma: no cover - environment guard
    raise ImportError(
        "shap is required for the XAI layer. Install the optional extra from the lab "
        "root: pip install -e .[xai-research]"
    ) from exc

import torch
from torch import nn

from models import AutoencoderModel, IsolationForestModel


def _importance_series(shap_values: np.ndarray, feature_names: list[str]) -> pd.Series:
    mean_abs = np.mean(np.abs(shap_values), axis=0).reshape(-1)
    return pd.Series(mean_abs, index=feature_names).sort_values(ascending=False)


def explain_isolation_forest(
    model: IsolationForestModel, X_sample: np.ndarray, feature_names: list[str]
) -> pd.Series:
    explainer = shap.TreeExplainer(model.model)
    shap_values = explainer.shap_values(X_sample)
    return _importance_series(np.asarray(shap_values), feature_names)


class _ReconstructionErrorHead(nn.Module):
    """Wraps the Autoencoder so it exposes a single scalar anomaly score per sample,
    which is what SHAP's Gradient/Kernel explainers expect to attribute."""

    def __init__(self, autoencoder: nn.Module) -> None:
        super().__init__()
        self.autoencoder = autoencoder

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        reconstruction = self.autoencoder(x)
        return torch.mean((reconstruction - x) ** 2, dim=1, keepdim=True)


def explain_autoencoder(
    model: AutoencoderModel,
    X_background: np.ndarray,
    X_sample: np.ndarray,
    feature_names: list[str],
) -> pd.Series:
    head = _ReconstructionErrorHead(model.net).to(model.device).eval()
    background_t = torch.tensor(X_background, dtype=torch.float32, device=model.device)
    sample_t = torch.tensor(X_sample, dtype=torch.float32, device=model.device)

    try:
        explainer = shap.GradientExplainer(head, background_t)
        shap_values = explainer.shap_values(sample_t)
        if isinstance(shap_values, list):
            shap_values = shap_values[0]
        shap_values = np.asarray(shap_values)
        if shap_values.ndim == 3:
            shap_values = shap_values[:, :, 0]
        return _importance_series(shap_values, feature_names)
    except Exception as exc:  # noqa: BLE001 - SHAP/PyTorch version drift is common across CPU-only labs
        warnings.warn(
            f"shap.GradientExplainer failed ({exc}); falling back to KernelExplainer "
            "(slower but has no autograd-graph requirements)."
        )

    def score_fn(x_np: np.ndarray) -> np.ndarray:
        with torch.no_grad():
            x_t = torch.tensor(x_np, dtype=torch.float32, device=model.device)
            return head(x_t).cpu().numpy().reshape(-1)

    background_summary = shap.kmeans(X_background, min(10, len(X_background)))
    explainer = shap.KernelExplainer(score_fn, background_summary)
    shap_values = explainer.shap_values(X_sample, nsamples=100, silent=True)
    return _importance_series(np.asarray(shap_values), feature_names)
