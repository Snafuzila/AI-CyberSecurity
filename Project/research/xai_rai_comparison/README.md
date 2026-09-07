# XAI/RAI Model x Dataset Comparison

Offline research script for Lab 2A. Trains Isolation Forest and an Autoencoder on two
datasets (NSL-KDD, Credit Card Fraud) and compares them with the same evaluation, XAI
(SHAP), and RAI (robustness/fairness/transparency) methodology, so differences in the
results are attributable to model/dataset choice rather than inconsistent metrics.

This does **not** touch the real-time streaming pipeline (`morpheus_lite_detector.py`,
`agent_orchestrator.py`, Kafka topics, etc.). It only reuses the same estimator family
and hyperparameter style (`IsolationForest(n_estimators=100, random_state=...)`,
train-on-normal-only) that `train_baseline_model()` in `morpheus_lite_detector.py`
already establishes, generalized from the 5 fixed SOC telemetry features to arbitrary
tabular datasets. The 5-feature SOC extraction logic itself doesn't transfer to NSL-KDD
or Credit Card Fraud, since those have their own native feature schemas.

## Setup

No GPU/hardware profile is defined for Lab 2A anywhere in `config/settings.yaml` or
`docker-compose.yml` — `compute.backend: auto` only selects the ONNX/Triton *inference*
provider used by the live pipeline, not training. This script is therefore CPU-only by
default (`RunConfig.device = "cpu"`) with a small Autoencoder architecture chosen to
train in a couple of minutes on a laptop CPU per dataset.

```bash
cd labs/lab2a-morpheus-lite
pip install -e .[xai-research]   # adds torch, shap, scipy on top of the base pipeline deps
```

## Datasets

Neither dataset ships with the repo (licensing) — both are gitignored (`data/*.txt`,
`data/*.csv`). Download them and place them at:

- **NSL-KDD**: `KDDTrain+.txt` and `KDDTest+.txt` from https://www.unb.ca/cic/datasets/nsl.html
  into `data/` (the Phase 1-4 scripts — `train_and_persist.py`, `run_scenarios.py` —
  hardcode `nsl_kdd_dir=<lab root>/data`, not the env-var path below; `run_comparison.py`
  still honors the env var).
- **Credit Card Fraud**: `creditcard.csv` from https://www.kaggle.com/mlg-ulb/creditcardfraud
  into `data/datasets/credit_card_fraud/` (only used by `run_comparison.py` — not wired
  into the Phase 1-4 pipeline; see `README_handover.md`).

The NSL-KDD path above is overridable via env var for `run_comparison.py` only:

```bash
export MORPHEUS_NSL_KDD_DIR=/path/to/nsl_kdd
export MORPHEUS_CREDIT_CARD_CSV=/path/to/creditcard.csv
```

## Run: exploratory comparison (`run_comparison.py`)

```bash
cd research/xai_rai_comparison
python run_comparison.py                 # both datasets, both models
python run_comparison.py --datasets nsl_kdd
python run_comparison.py --epochs 10      # faster Autoencoder run for a smoke test
```

## Run: Phase 1-4 LLM-orchestrated SOC comparison

The Phase 1-4 pipeline (`train_and_persist.py` -> `enriched_payload.py` ->
`llm_orchestrator.py` -> `run_scenarios.py`) trains IF/AE, persists them to
`artifacts/nsl_kdd/` (already committed, so this step is optional unless you want a
fresh retrain), then scores 4 IF/AE agreement scenarios and sends each resulting prompt
to a local Ollama model for a real SOC triage response.

```bash
# One-time: local LLM (defaults to llama3.1:8b; override with --llm-model / env vars
# below if you're using a different local model)
ollama pull llama3.1:8b

cd research/xai_rai_comparison
python train_and_persist.py   # optional -- artifacts/nsl_kdd/ is already populated
python run_scenarios.py       # prints + saves IF vs AE prompts and LLM responses
```

`run_scenarios.py` writes the full run (prompts + LLM responses for all 4 scenarios) to
`exports/xai_rai_comparison/<timestamp>/scenario_comparison.json` (gitignored —
regenerate anytime by rerunning the script). Useful flags:

```bash
python run_scenarios.py --no-llm                     # print prompts only, skip the LLM call
python run_scenarios.py --llm-model deepseek-r1       # use a different local Ollama model
python run_scenarios.py --ollama-url http://host:11434/api/generate
```

Env var equivalents: `MORPHEUS_XAI_RAI_LLM_MODEL`, `MORPHEUS_XAI_RAI_OLLAMA_URL`.

Output goes to `exports/xai_rai_comparison/<run_id>/` (matches the existing
`exports/` "research-ready export files" convention from
`docs/RESEARCH_DATA_GUIDE.md`):

- `report.json` — full nested results: metrics, SHAP importances, RAI report per (dataset, model)
- `summary.md` — comparison table + Autoencoder-vs-Isolation-Forest deltas per dataset
- `<dataset>__<model>__shap_importance.csv` — per-feature mean |SHAP value|

## Methodology notes for the write-up

- **Training data**: both models are fit on normal-only samples from the training
  split (`RunConfig.train_on_normal_only`), mirroring the existing detector's
  synthetic-normal-only training. Evaluation uses the held-out, fully labeled test split.
- **Threshold**: derived from the test set's own anomaly-rate prior
  (`unified_evaluate`), applied identically to both models — not a per-model
  best-F1 search, which would leak test labels into model selection.
- **Fairness**: neither dataset carries protected-class/demographic attributes.
  `protocol_type` (NSL-KDD) and transaction-amount quartile (Credit Card Fraud) are
  used as explicit **proxy** grouping attributes for a subgroup performance-disparity
  check — not a legal/demographic fairness audit. State this caveat in the report.
- **Transparency**: measured structurally from the SHAP importances (features needed
  for 80% cumulative importance, Gini concentration), not by human judgment.
