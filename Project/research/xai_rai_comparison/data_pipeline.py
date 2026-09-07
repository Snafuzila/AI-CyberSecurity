from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from config import RunConfig

NSL_KDD_COLUMNS = [
    "duration", "protocol_type", "service", "flag", "src_bytes", "dst_bytes", "land",
    "wrong_fragment", "urgent", "hot", "num_failed_logins", "logged_in", "num_compromised",
    "root_shell", "su_attempted", "num_root", "num_file_creations", "num_shells",
    "num_access_files", "num_outbound_cmds", "is_host_login", "is_guest_login", "count",
    "srv_count", "serror_rate", "srv_serror_rate", "rerror_rate", "srv_rerror_rate",
    "same_srv_rate", "diff_srv_rate", "srv_diff_host_rate", "dst_host_count",
    "dst_host_srv_count", "dst_host_same_srv_rate", "dst_host_diff_srv_rate",
    "dst_host_same_src_port_rate", "dst_host_srv_diff_host_rate", "dst_host_serror_rate",
    "dst_host_srv_serror_rate", "dst_host_rerror_rate", "dst_host_srv_rerror_rate",
    "label", "difficulty",
]
NSL_KDD_CATEGORICAL = ["protocol_type", "service", "flag"]


@dataclass
class PreparedDataset:
    name: str
    X_train: np.ndarray
    X_test: np.ndarray
    y_test: np.ndarray  # 0 = normal, 1 = anomaly/fraud
    feature_names: list[str]
    group_test: pd.Series  # proxy attribute used for RAI fairness slicing, not a protected class
    # Fitted preprocessors + the column lists used to build them, exposed so a caller can
    # transform a brand-new raw event the same way training data was transformed (e.g. to
    # score a single live event against a persisted model) without refitting or duplicating
    # the encoding logic below.
    scaler: StandardScaler
    encoder: OneHotEncoder | None
    numeric_cols: list[str]
    categorical_cols: list[str]
    # Raw (pre-transform) test rows, row-aligned with X_test/y_test/group_test -- lets a
    # caller build a realistic "new event" payload for a specific test index instead of
    # inverse-transforming the scaled/encoded matrix.
    test_raw: pd.DataFrame


def _missing_dataset_error(kind: str, path: Path, hint: str) -> FileNotFoundError:
    return FileNotFoundError(
        f"{kind} dataset not found at {path}. {hint} "
        f"Path is configurable via env var (see config.py) for other Lab 2A machines."
    )


def load_nsl_kdd(cfg: RunConfig) -> PreparedDataset:
    train_path = cfg.nsl_kdd_dir / "KDDTrain+.txt"
    test_path = cfg.nsl_kdd_dir / "KDDTest+.txt"
    if not train_path.exists() or not test_path.exists():
        raise _missing_dataset_error(
            "NSL-KDD",
            cfg.nsl_kdd_dir,
            "Download KDDTrain+.txt and KDDTest+.txt from the NSL-KDD dataset "
            "(https://www.unb.ca/cic/datasets/nsl.html) and place them in this directory.",
        )

    train_df = pd.read_csv(train_path, names=NSL_KDD_COLUMNS)
    test_df = pd.read_csv(test_path, names=NSL_KDD_COLUMNS)
    full_df = pd.concat([train_df, test_df], ignore_index=True)
    full_df["is_anomaly"] = (full_df["label"] != "normal").astype(int)

    numeric_cols = [
        c for c in NSL_KDD_COLUMNS if c not in NSL_KDD_CATEGORICAL and c not in ("label", "difficulty")
    ]

    train_idx, test_idx = train_test_split(
        full_df.index,
        test_size=cfg.test_size,
        random_state=cfg.seed,
        stratify=full_df["is_anomaly"],
    )
    train_part = full_df.loc[train_idx]
    test_part = full_df.loc[test_idx]

    encoder = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
    encoder.fit(train_part[NSL_KDD_CATEGORICAL])
    scaler = StandardScaler()
    scaler.fit(train_part[numeric_cols])

    def build_matrix(df: pd.DataFrame) -> np.ndarray:
        cat = encoder.transform(df[NSL_KDD_CATEGORICAL])
        num = scaler.transform(df[numeric_cols])
        return np.hstack([num, cat])

    feature_names = numeric_cols + list(encoder.get_feature_names_out(NSL_KDD_CATEGORICAL))

    fit_source = train_part[train_part["is_anomaly"] == 0] if cfg.train_on_normal_only else train_part
    X_train = build_matrix(fit_source)
    X_test = build_matrix(test_part)

    return PreparedDataset(
        name="nsl_kdd",
        X_train=X_train,
        X_test=X_test,
        y_test=test_part["is_anomaly"].to_numpy(),
        feature_names=feature_names,
        group_test=test_part["protocol_type"].reset_index(drop=True),
        scaler=scaler,
        encoder=encoder,
        numeric_cols=numeric_cols,
        categorical_cols=NSL_KDD_CATEGORICAL,
        test_raw=test_part[numeric_cols + NSL_KDD_CATEGORICAL].reset_index(drop=True),
    )


def load_credit_card_fraud(cfg: RunConfig) -> PreparedDataset:
    if not cfg.credit_card_csv.exists():
        raise _missing_dataset_error(
            "Credit Card Fraud",
            cfg.credit_card_csv,
            "Download creditcard.csv from the Kaggle 'Credit Card Fraud Detection' dataset "
            "(https://www.kaggle.com/mlg-ulb/creditcardfraud) and place it at this path.",
        )

    df = pd.read_csv(cfg.credit_card_csv)
    feature_cols = [c for c in df.columns if c not in ("Class",)]

    # Amount has no protected-class meaning; it is used only as a transparent, reproducible
    # proxy grouping variable for the fairness slice, since this dataset carries no
    # demographic attributes at all.
    amount_bucket = pd.qcut(df["Amount"], q=4, labels=["q1_low", "q2", "q3", "q4_high"])

    train_idx, test_idx = train_test_split(
        df.index,
        test_size=cfg.test_size,
        random_state=cfg.seed,
        stratify=df["Class"],
    )
    train_part = df.loc[train_idx]
    test_part = df.loc[test_idx]

    scaler = StandardScaler()
    scaler.fit(train_part[feature_cols])

    fit_source = train_part[train_part["Class"] == 0] if cfg.train_on_normal_only else train_part
    X_train = scaler.transform(fit_source[feature_cols])
    X_test = scaler.transform(test_part[feature_cols])

    return PreparedDataset(
        name="credit_card_fraud",
        X_train=X_train,
        X_test=X_test,
        y_test=test_part["Class"].to_numpy(),
        feature_names=feature_cols,
        group_test=amount_bucket.loc[test_idx].reset_index(drop=True),
        scaler=scaler,
        encoder=None,
        numeric_cols=feature_cols,
        categorical_cols=[],
        test_raw=test_part[feature_cols].reset_index(drop=True),
    )
