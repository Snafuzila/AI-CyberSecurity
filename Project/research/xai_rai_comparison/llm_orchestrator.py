"""Phase 3: the orchestrator no longer counts alerts or hardcodes IF/ELSE decisions --
it evaluates a RAI policy from the payload's track record, then formats the payload
into a prompt for the SOC LLM. No LLM is called here; build_llm_prompt() returns the
text that would be sent to one."""
from __future__ import annotations

FPR_STRICT_THRESHOLD = 0.10
FAIRNESS_GAP_STRICT_THRESHOLD = 0.10

_EVIDENCE_DESCRIPTION = {
    "Isolation_Forest": (
        "SHAP values: each feature's signed contribution to the Isolation Forest "
        "anomaly score for this specific event (positive = pushed toward anomalous)."
    ),
    "Autoencoder": (
        "Per-feature reconstruction error: how far each value deviated from what the "
        "Autoencoder expected for normal behavior (higher = more surprising)."
    ),
}


def rai_policy_evaluator(payload: dict) -> dict:
    """Decides automated-containment eligibility from the model's own global track
    record (rai_metadata) -- never from the raw anomaly score alone."""
    if payload["predicted_class"] == "normal":
        return {
            "automated_containment_allowed": False,
            "human_approval_required": False,
            "policy_reason": "No anomaly predicted; no containment action applicable.",
        }

    rai = payload["rai_metadata"]
    fpr = rai.get("false_positive_rate")
    fairness_gap = rai.get("fairness_gap")
    model = payload["triggering_model"]

    concerns = []
    if fpr is not None and fpr > FPR_STRICT_THRESHOLD:
        concerns.append(f"false positive rate {fpr:.1%} exceeds the {FPR_STRICT_THRESHOLD:.0%} trust threshold")
    if fairness_gap is not None and fairness_gap > FAIRNESS_GAP_STRICT_THRESHOLD:
        concerns.append(f"fairness gap {fairness_gap:.1%} exceeds the {FAIRNESS_GAP_STRICT_THRESHOLD:.0%} threshold")

    if concerns:
        return {
            "automated_containment_allowed": False,
            "human_approval_required": True,
            "policy_reason": (
                f"{model} alert requires human approval: " + "; ".join(concerns) +
                ". Automated action risks alert fatigue from unreliable positives."
            ),
        }
    return {
        "automated_containment_allowed": True,
        "human_approval_required": False,
        "policy_reason": (
            f"{model} meets trust thresholds (FPR {fpr:.1%}, fairness gap "
            f"{fairness_gap:.1%}). Automated containment approved; decision logged for audit."
        ),
    }


def build_llm_prompt(payload: dict, rai_decision: dict) -> str:
    evidence_lines = "\n".join(f"  - {feat}: {weight:+.4f}" for feat, weight in payload["xai_evidence"].items())
    rai = payload["rai_metadata"]
    cross = payload["cross_model_signal"]
    if payload["predicted_class"] == "normal":
        containment = "N/A - no anomaly predicted"
    elif rai_decision["automated_containment_allowed"]:
        containment = "ALLOWED"
    else:
        containment = "DENIED - human approval required"

    return f"""You are a SOC analyst assistant. Explain why this alert fired and what action follows, using only the evidence below.

--- ALERT ---
Alert ID: {payload['alert_id']}
Dataset: {payload['dataset_name']}
Detection model: {payload['triggering_model']}
Anomaly score: {payload['anomaly_score']:.4f}
Predicted class: {payload['predicted_class']}

--- MATHEMATICAL EVIDENCE (XAI) ---
{_EVIDENCE_DESCRIPTION[payload['triggering_model']]}
{evidence_lines}

--- CROSS-MODEL SIGNAL (both models' own outputs for this same event) ---
Isolation Forest: anomaly_score={cross['isolation_forest_anomaly_score']:.4f}, predicted_class={cross['isolation_forest_predicted_class']}
Autoencoder: reconstruction_error={cross['autoencoder_reconstruction_error']:.4f}, predicted_class={cross['autoencoder_predicted_class']}

--- MODEL TRACK RECORD (RAI) ---
Precision: {rai['precision']:.3f} | Recall: {rai['recall']:.3f} | F1: {rai['f1']:.3f}
False Positive Rate: {rai['false_positive_rate']:.3f}
Fairness gap (max subgroup FPR difference): {rai['fairness_gap']:.3f}

--- GOVERNANCE DECISION (already determined, do not override) ---
Automated containment: {containment}
Reason: {rai_decision['policy_reason']}

--- YOUR TASK ---
1. In 2-4 sentences, explain why this event's evidence indicates anomalous (or benign) behavior, using only the features and values listed above.
2. State the recommended SOC action, consistent with the governance decision above.
3. Note anything a human analyst should double-check before acting.
4. Briefly note whether the other model (see CROSS-MODEL SIGNAL) agrees or disagrees with this alert, and what that agreement/disagreement implies for confidence in this decision.
"""
