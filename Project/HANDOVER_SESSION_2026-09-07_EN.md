# Session Handover — 2026-09-07 (EN, technical detail)

Companion to `HANDOVER_SESSION_2026-09-07.md` (Hebrew, same session). This version goes
deeper on the technical/architecture side per a direct request for maximum detail.
Last commit at time of writing: `55931eb`.

## 1. Context & Objective

The parent project is **Morpheus Lite Laboratory**: an educational, governance-aware,
AI-native SOC (Security Operations Center) pipeline. Inside it,
`research/xai_rai_comparison/` is a standalone offline research suite (zero imports
from the live Kafka pipeline) whose goal is:

> Systematically compare **Isolation Forest (IF)** vs. **Autoencoder (AE)** anomaly
> detectors on NSL-KDD, layer **XAI** (explainability) and **RAI** (responsible-AI
> governance) on top of each, and feed the result to an LLM (**local Llama via Ollama**)
> to produce a SOC analyst triage narrative — then compare what IF-triggered vs.
> AE-triggered alerts look like side by side.

This session's specific mandate (three explicit constraints from the user):
1. **Do not change the existing XAI/RAI logic** (SHAP top-3 for IF, reconstruction-error
   top-3 for AE, the RAI policy's FPR/fairness-gap thresholds).
2. **Add features derived from the models themselves** (IF's own anomaly score, AE's
   own reconstruction error) — resolved via clarifying question to mean: **cross-reference
   both models' own scores into both payloads**, so an IF-triggered alert still shows
   what AE produced for the same event, and vice versa.
3. **Feed the result through a local Llama model** (Ollama, already installed) to get
   real SOC-analyst responses instead of just printing prompt text.

Then, separately, the user asked to get this project pushed to their existing GitHub
repo (`Snafuzila/AI-CyberSecurity`), which turned into a repo-restructuring exercise
(see §5).

## 2. Current Implementation & Architecture

Directory (as of the current commit, everything under `Project/` in the repo):

```
Project/research/xai_rai_comparison/
├── config.py              # RunConfig dataclass: paths, seed=42, AE hyperparams, device="cpu"
├── data_pipeline.py        # load_nsl_kdd(): reads KDDTrain+.txt/KDDTest+.txt, builds
│                           #   StandardScaler + OneHotEncoder(protocol_type/service/flag),
│                           #   stratified 70/30 split, returns PreparedDataset
├── models.py                # IsolationForestModel, AutoencoderModel (_AutoencoderNet: plain
│                           #   PyTorch, hidden dims (64,32,16), NOT Keras)
├── evaluation.py            # unified_evaluate(): threshold derived from test-set anomaly-rate prior
├── rai_analysis.py          # fairness_report() (used), robustness_report()/transparency_report()
│                           #   (NOT wired into the Phase 1-4 payloads — available but unused)
├── train_and_persist.py     # PHASE 1: trains IF+AE on NSL-KDD (train-on-normal-only), persists
│                           #   artifacts/nsl_kdd/{isolation_forest.pkl, autoencoder.pt (state_dict),
│                           #   scaler.pkl, encoder.pkl, manifest.json}
├── enriched_payload.py      # PHASE 2: generate_enriched_payload(event, event_id) -> (if_payload, ae_payload)
├── llm_orchestrator.py      # PHASE 3: rai_policy_evaluator() + build_llm_prompt()
├── llm_client.py            # NEW this session: minimal standalone Ollama client
├── run_scenarios.py         # PHASE 4: finds 1 example event per scenario, runs Phases 2-3,
│                           #   calls llm_client, saves full run to exports/.../scenario_comparison.json
├── run_comparison.py        # Separate, older exploratory script (NSL-KDD + Credit Card Fraud,
│                           #   SHAP importances, full RAI report) — not part of the Phase 1-4 chain
├── is_and_ae_on_nsl_kdd.py  # NOT part of this pipeline — a Colab-exported script, Keras-based AE,
│                           #   flagged as "unclear origin" in the original handover doc
└── artifacts/nsl_kdd/       # Trained model artifacts, committed to git (~1.6MB total)
```

### 2a. Phase 2 — payload enrichment (`enriched_payload.py`)

For one raw NSL-KDD event, `generate_enriched_payload()` computes:
- `if_score = -if_model.decision_function(x)` (sklearn convention: higher = more anomalous
  after negation)
- `ae_score = mean((AE(x) - x)^2)` (overall reconstruction MSE)
- `if_predicted_class` / `ae_predicted_class`: thresholded against `manifest["thresholds"]`
  (test-set-derived, from Phase 1)

**XAI evidence** (unchanged logic):
- IF: `shap.TreeExplainer(if_model).shap_values(x)`, top-3 by `|value|`, signed contribution
- AE: per-feature `(x - reconstruction)^2`, top-3 largest (which features looked least
  "normal" to the AE)

**NEW this session — `cross_model_signal`** (added to BOTH `if_payload` and `ae_payload`,
identical dict in both):
```python
{
  "isolation_forest_anomaly_score": if_score,
  "isolation_forest_predicted_class": "anomaly" | "normal",
  "autoencoder_reconstruction_error": ae_score,
  "autoencoder_predicted_class": "anomaly" | "normal",
}
```
This is the mechanism that answers requirement #2 above — it lets the IF alert's prompt
"see" what AE thought about the exact same event, and vice versa, without touching the
top-3 XAI extraction functions (`_top3_if`, `_top3_ae` are byte-for-byte unchanged).

**RAI metadata** (unchanged, read verbatim from Phase 1's `manifest.json`):
`precision`, `recall`, `f1`, `false_positive_rate`, `fairness_gap` — these are GLOBAL
(computed once on the held-out test set in Phase 1), attached identically to every event
scored by that model. Not recomputed per-event.

### 2b. Phase 3 — governance decision (`llm_orchestrator.py`)

`rai_policy_evaluator(payload)` — **completely unchanged this session**:
```python
FPR_STRICT_THRESHOLD = 0.10
FAIRNESS_GAP_STRICT_THRESHOLD = 0.10
```
Logic: if `predicted_class == "normal"` → no containment question applies. Else, if
`false_positive_rate > 10%` OR `fairness_gap > 10%` → `automated_containment_allowed=False,
human_approval_required=True`. Otherwise → `automated_containment_allowed=True`.
This function reads ONLY the model's precomputed global track record — never the
per-event anomaly score — by design (a single anomalous-looking event shouldn't override
a model's known reliability profile).

`build_llm_prompt(payload, rai_decision)` — **modified this session**: added a new
`--- CROSS-MODEL SIGNAL ---` section printing both models' own scores/classes, and a
4th numbered task asking the LLM to explicitly comment on IF/AE agreement or disagreement
and what it implies for confidence. Everything else in the prompt template (ALERT header,
XAI evidence section, RAI track record section, GOVERNANCE DECISION section) is unchanged.

### 2c. Phase 4 — real LLM calls (`run_scenarios.py`, rewritten this session)

Previously this script only *printed* the prompt text (no LLM was ever called). Now:
- `llm_client.py` (new file): `call_llama(prompt, model, url, timeout=120)` — POSTs to
  Ollama's `/api/generate` endpoint (`stream: False`), returns `response.json()["response"]`.
  Deliberately has **zero import from `morpheus_lite.inference`** to preserve the research
  suite's existing decoupling from the live Kafka pipeline (this was an explicit design
  constraint already documented in the suite's own README before this session).
- Defaults: model `llama3.1:8b` (env override `MORPHEUS_XAI_RAI_LLM_MODEL`), URL
  `http://localhost:11434/api/generate` (env override `MORPHEUS_XAI_RAI_OLLAMA_URL`).
- CLI flags added: `--llm-model`, `--ollama-url`, `--no-llm` (skip the LLM call, keep
  old prompt-only behavior — useful for a quick smoke test without needing Ollama running).
- Output: for each of the 4 scenarios × 2 models = 8 LLM calls, saves everything
  (payload, rai_decision, prompt, llm_response, llm_error) to
  `exports/xai_rai_comparison/<timestamp>/scenario_comparison.json`. This directory is
  **gitignored** (regenerated every run) — it is NOT in the GitHub repo by design.

## 3. Scenarios & Data Analysis (actual run results from this session)

Ran successfully end-to-end against real `llama3.1:8b`. Four scenarios, defined by
`(if_pred, ae_pred)` on the NSL-KDD test set:

### Scenario A — Both Alert (test idx 2)
- IF: `anomaly_score=0.1770`, predicted=**anomaly**. Top-3 SHAP:
  `dst_host_srv_diff_host_rate: -1.4210`, `protocol_type_icmp: -1.2145`,
  `service_eco_i: -1.1104`.
- AE: `reconstruction_error=0.0638`, predicted=**anomaly**. Top-3 recon error:
  `srv_diff_host_rate: +2.2262`, `diff_srv_rate: +0.8644`, `service_eco_i: +0.5907`.
- **IF governance: DENIED** — fairness_gap 47.6% > 10% threshold → human approval required.
- **AE governance: ALLOWED** — FPR 8.6%, fairness_gap 7.2%, both under threshold.
- Llama's response for both correctly identified agreement between the two models and
  used it to reason about confidence, per the new task #4 instruction.

### Scenario B — Isolation Forest ONLY (test idx 43, disagreement)
- IF: `anomaly_score=0.1276`, predicted=**anomaly**. DENIED (same fairness-gap issue —
  IF's global fairness_gap of 47.6% applies to every IF anomaly alert, not just this one).
- AE: `reconstruction_error=0.0437`, predicted=**normal**. Governance: N/A (no anomaly).
- Llama's response on the IF side explicitly flagged: "The Autoencoder model predicts a
  normal class... this discrepancy is likely due to noise or anomalies specific to one
  of the features, rather than a fundamental flaw in either model" — reasonable but
  worth human review given this is exactly a disagreement case.

### Scenario C — Autoencoder ONLY (test idx 38, disagreement)
- IF: `anomaly_score=0.0498`, predicted=**normal**.
- AE: `reconstruction_error=1.1034` (large), predicted=**anomaly**. Top-3 recon error:
  `num_root: +47.3309`, `num_compromised: +40.7896`, `logged_in: +6.4183` — these are
  classic privilege-escalation indicator features, a qualitatively different "story"
  than IF's magnitude-based signal.
- **AE governance: ALLOWED** (meets trust thresholds) — meaning this scenario would
  trigger **automated containment** even though IF disagreed. Llama's response noted the
  disagreement and recommended reconciling both models' outputs before acting — a
  reasonable human-in-the-loop caveat that the automated policy itself doesn't enforce.

### Scenario D — Both Normal (test idx 0, agreement on benign)
- IF: `anomaly_score=0.0033`, AE: `reconstruction_error=0.0119`, both **normal**.
  No containment action; Llama used the agreement to state high confidence in the
  benign classification.

### Key structural finding (pre-existing, re-verified this session, unrelated to code changes)
IF's fairness gap comes from a large subgroup disparity by `protocol_type`:
`tcp` FPR 7.3%, `icmp` FPR **54.9%**, `udp` FPR 12.5% → 47.6-point gap, which is why
**every single IF anomaly alert** in this dataset is policy-denied for automated
containment (its global fairness_gap exceeds 10% regardless of the specific event).
AE's fairness gap (7.2%) stays under threshold, so AE anomalies (when RAI-eligible) can
be auto-contained. This is the central "IF vs AE" governance story the whole comparison
suite is built to surface. Caveat (carried over, still true): `protocol_type` is a proxy
attribute, not a demographic/protected class — this is a subgroup performance-disparity
check, not a legal fairness audit.

## 4. Files & Code Assets

- **`Project/docs/xai_rai_scenario_comparison.docx`** — pre-existing file (predates this
  session, NOT created by me), 38KB, sits under `Project/docs/`. I have not opened/edited
  its contents this session — only relocated it during the `Project/` restructure. If it
  documents scenario analysis, it may be worth reconciling with the live JSON output
  described below (I did not cross-check them against each other).
- **`exports/xai_rai_comparison/20260907-182821/scenario_comparison.json`** — the ONE
  real output artifact generated this session (prompts + actual llama3.1:8b responses for
  all 4 scenarios × 2 models). Lives at repo root (not under `Project/`) because it was
  generated before the `Project/` restructure; gitignored, not on GitHub.
- **No `scenario_comparison_2.json` exists anywhere in the working tree** (I searched;
  only the one JSON above and the `.docx` were found). If a second comparison run is
  expected to exist, it either wasn't generated yet, or was generated/saved somewhere
  outside this working directory — worth clarifying before assuming it's missing/lost.
- **`Project/research/xai_rai_comparison/artifacts/nsl_kdd/`** — committed to git
  (isolation_forest.pkl, autoencoder.pt, scaler.pkl, encoder.pkl, manifest.json, ~1.6MB
  total) so results reproduce without retraining.
- **New source files this session**: `llm_client.py` (new). **Modified**:
  `enriched_payload.py`, `llm_orchestrator.py`, `run_scenarios.py`,
  `research/xai_rai_comparison/README.md`, top-level `README.md`.

## 5. Git / Repo State (see Hebrew doc §4-6 for the full narrative)

- Local repo root: `d:\CyberSecurityAiBoLem\proj` (contains `.git`, `Labs/`, `Project/`).
- Remote: `origin` → `https://github.com/Snafuzila/AI-CyberSecurity.git`, branch `main`.
- Current HEAD / origin/main: commit `55931eb` ("Remove duplicate Project/newest/").
- The whole local project (previously flat at `proj/`) was restructured under `Project/`
  to match the existing GitHub monorepo layout (`Labs/` = other coursework, untouched;
  `Project/` = this project). **Important**: `.gitignore` lives at the repo ROOT
  (`proj/.gitignore`), NOT inside `Project/` — patterns with a `/` in them are prefixed
  `Project/...` accordingly (e.g. `Project/data/*.txt`) since gitignore patterns with a
  slash are anchored to the `.gitignore` file's own directory.
- Mid-session, a manual GitHub web upload created a duplicate `Project/newest/` folder
  (confirmed by user as accidental) — merged in and then deleted in a follow-up commit.
- A few pushes were transiently rejected as "non-fast-forward" even when hashes lined up
  (likely a race with concurrent activity on the repo); retrying the push resolved it.
  No `--force` was used at any point.
- Commit author shows as `VLSI Lab <vlsi@stud-hait.ac.il>` (auto-detected from Windows
  username/hostname) — not necessarily the user's real GitHub identity
  (`lotem1237@gmail.com` per this session's user context). Not fixed — requires the user
  to run `git config user.name`/`user.email` themselves; Claude avoided touching git
  config per safety policy.

## 6. Environment Gotcha (repeat warning)

Installing `shap` directly into the global Anaconda Python
(`C:\anaconda3\python.exe`) upgrades numpy to 2.x and **breaks pandas/pyarrow globally**.
This happened once this session and was fixed (`pip install "numpy<2"` in that global
env). **Always use the project's own `.venv`** (`proj/.venv`, NOT inside `Project/`):
```powershell
cd Project
python -m venv ..\.venv
..\.venv\Scripts\Activate.ps1
pip install -e ".[xai-research]"
```
`.venv/` is gitignored (1.4GB; individual DLLs inside it exceed GitHub's 100MB/file
hard limit, e.g. `torch_cpu.dll` at 305MB) — must be recreated on every new machine.

## 7. Next Steps / Open Items — action checklist

1. **[OPEN DECISION — not yet resolved]** User asked earlier to identify and delete
   everything under `Project/` that isn't part of `research/xai_rai_comparison/`
   (i.e., delete the entire live-pipeline scaffold: `morpheus_lite/`,
   `agent_orchestrator.py`, `dashboard.py`, `docker-compose.yml`, `config/`, `tests/`,
   `docs/`, etc. — on the theory that "only research/xai_rai_comparison files are the
   actual project"). This was **never executed** — the conversation redirected to
   resolving a perceived local/GitHub mismatch instead (which turned out to be a
   non-issue). **Before doing this on the next machine/session**: confirm with the user
   whether they still want this, since it would delete a large, separately-valuable body
   of coursework (the Morpheus Lite Laboratory scaffold) from the repo — a destructive,
   hard-to-reverse action on a shared/public repo.
2. **Reconcile `xai_rai_scenario_comparison.docx`** against the JSON scenario output —
   neither I nor (as far as I know) this session checked whether the Word doc's narrative
   matches the actual A/B/C/D results above; worth a manual diff/read-through.
3. **Locate or regenerate the "second" scenario comparison** the user referenced
   (`scenario_comparison_2.json`) if it's supposed to exist — currently not found.
4. **Fix commit author identity** if it matters for grading/attribution (see §5).
5. **Optional Phase 5** (mentioned in the original handover doc, still unimplemented):
   wire `robustness_report()`/`transparency_report()` from `rai_analysis.py` into the
   Phase 1-4 payload schema — they exist and are used by the separate
   `run_comparison.py`, but not by the Phase 1-4 LLM pipeline.
6. **On a fresh machine**: `git clone https://github.com/Snafuzila/AI-CyberSecurity.git`,
   `cd AI-CyberSecurity/Project`, then follow §6 above for the venv, download NSL-KDD
   (`KDDTrain+.txt`/`KDDTest+.txt` from unb.ca/cic/datasets/nsl.html) into `Project/data/`
   (not committed — licensing), `ollama pull llama3.1:8b`, then
   `cd research/xai_rai_comparison && python run_scenarios.py`.
