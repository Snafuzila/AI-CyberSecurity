from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# research/ sits one level below the lab root (same convention as morpheus_lite/config.py's ROOT)
LAB_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class RunConfig:
    nsl_kdd_dir: Path = field(
        default_factory=lambda: Path(
            os.getenv("MORPHEUS_NSL_KDD_DIR", str(LAB_ROOT / "data" / "datasets" / "nsl_kdd"))
        )
    )
    credit_card_csv: Path = field(
        default_factory=lambda: Path(
            os.getenv(
                "MORPHEUS_CREDIT_CARD_CSV",
                str(LAB_ROOT / "data" / "datasets" / "credit_card_fraud" / "creditcard.csv"),
            )
        )
    )
    output_dir: Path = field(
        default_factory=lambda: Path(
            os.getenv("MORPHEUS_XAI_RAI_OUTPUT_DIR", str(LAB_ROOT / "exports" / "xai_rai_comparison"))
        )
    )
    seed: int = 42
    test_size: float = 0.3
    # Both models are fit on normal-only data, mirroring train_baseline_model() in
    # morpheus_lite_detector.py, which fits IsolationForest on synthetic normal traffic only.
    train_on_normal_only: bool = True
    # None means "derive from the held-out test set's own label prior" (see
    # run_comparison._contamination_for). Hardcoding a rate here would silently drift
    # from reality depending on exactly which NSL-KDD files a student downloads.
    contamination_nsl_kdd: float | None = None
    contamination_credit_card: float | None = None

    ae_hidden_dims: tuple[int, ...] = (64, 32, 16)
    ae_epochs: int = 30
    ae_batch_size: int = 256
    ae_learning_rate: float = 1e-3
    # No GPU/hardware profile is defined for Lab 2A anywhere in config/settings.yaml or
    # docker-compose.yml (compute.backend: auto only selects the ONNX/Triton inference
    # provider, not training). Training therefore stays CPU-only and the architecture
    # above is deliberately small enough to fit both datasets in a couple of minutes on CPU.
    device: str = "cpu"

    noise_std_fraction: float = 0.05  # robustness: perturbation size as a fraction of each feature's std
    shap_background_size: int = 50
    shap_sample_size: int = 200
