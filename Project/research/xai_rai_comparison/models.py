from __future__ import annotations

from typing import Protocol

import numpy as np
from sklearn.ensemble import IsolationForest

try:
    import torch
    from torch import nn
except ImportError as exc:  # pragma: no cover - environment guard
    raise ImportError(
        "PyTorch is required for the Autoencoder comparison. Install the optional "
        "extra from the lab root: pip install -e .[xai-research]"
    ) from exc

from config import RunConfig


class AnomalyModel(Protocol):
    def fit(self, X: np.ndarray) -> None: ...
    def anomaly_scores(self, X: np.ndarray) -> np.ndarray:  # higher = more anomalous
        ...


class IsolationForestModel:
    """Same estimator family and hyperparameter style as train_baseline_model() in
    morpheus_lite_detector.py (n_estimators=100, fixed random_state), generalized to
    arbitrary tabular feature spaces instead of the 5 fixed SOC telemetry features."""

    def __init__(self, contamination: float, seed: int) -> None:
        self.model = IsolationForest(n_estimators=100, contamination=contamination, random_state=seed)

    def fit(self, X: np.ndarray) -> None:
        self.model.fit(X)

    def anomaly_scores(self, X: np.ndarray) -> np.ndarray:
        # sklearn's decision_function is higher for inliers; flip so higher == more anomalous,
        # matching the Autoencoder's reconstruction-error convention.
        return -self.model.decision_function(X)


class _AutoencoderNet(nn.Module):
    def __init__(self, input_dim: int, hidden_dims: tuple[int, ...]) -> None:
        super().__init__()
        encoder_layers: list[nn.Module] = []
        dims = [input_dim, *hidden_dims]
        for in_dim, out_dim in zip(dims[:-1], dims[1:]):
            encoder_layers += [nn.Linear(in_dim, out_dim), nn.ReLU()]
        decoder_layers: list[nn.Module] = []
        rev_dims = [*hidden_dims[::-1], input_dim]
        for in_dim, out_dim in zip(rev_dims[:-1], rev_dims[1:]):
            decoder_layers.append(nn.Linear(in_dim, out_dim))
            if out_dim != input_dim:
                decoder_layers.append(nn.ReLU())
        self.encoder = nn.Sequential(*encoder_layers)
        self.decoder = nn.Sequential(*decoder_layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.decoder(self.encoder(x))


class AutoencoderModel:
    def __init__(self, input_dim: int, cfg: RunConfig) -> None:
        self.cfg = cfg
        self.device = torch.device(cfg.device)
        self.net = _AutoencoderNet(input_dim, cfg.ae_hidden_dims).to(self.device)

    def fit(self, X: np.ndarray) -> None:
        torch.manual_seed(self.cfg.seed)
        tensor_X = torch.tensor(X, dtype=torch.float32, device=self.device)
        dataset = torch.utils.data.TensorDataset(tensor_X)
        loader = torch.utils.data.DataLoader(dataset, batch_size=self.cfg.ae_batch_size, shuffle=True)
        optimizer = torch.optim.Adam(self.net.parameters(), lr=self.cfg.ae_learning_rate)
        loss_fn = nn.MSELoss()

        self.net.train()
        for _ in range(self.cfg.ae_epochs):
            for (batch,) in loader:
                optimizer.zero_grad()
                reconstruction = self.net(batch)
                loss = loss_fn(reconstruction, batch)
                loss.backward()
                optimizer.step()
        self.net.eval()

    def anomaly_scores(self, X: np.ndarray) -> np.ndarray:
        tensor_X = torch.tensor(X, dtype=torch.float32, device=self.device)
        with torch.no_grad():
            reconstruction = self.net(tensor_X)
            per_sample_mse = torch.mean((reconstruction - tensor_X) ** 2, dim=1)
        return per_sample_mse.cpu().numpy()
