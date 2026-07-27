# Morpheus Lite Agentic SOC Dashboard - Case Report

**Pipeline Flow:** Kafka → Detection → Agent Orchestration → RAI → Meta-AI → Human Decision

---

## Dashboard Metrics Overview

| Metric | Count |
| :--- | :--- |
| **Total Cases** | 318 |
| **High Risk** | 38 |
| **Pending Human Review** | 38 |
| **Meta-AI Escalations** | 0 |

---

## Active Case Details: `alert-0-91`

This case requires human review. Human review remains authoritative.

### Summary Table

| Field | Value |
| :--- | :--- |
| **alert_id** | `alert-0-91` |
| **risk score** | `100` |
| **user** | `svc-backup` |
| **host** | `host-02` |
| **event type** | `privilege_escalation` |
| **fingerprint deviation** | `256.2106` |
| **inference provider** | `deterministic` |
| **RAI approval required** | `TRUE` |
| **current human decision** | `pending` |

---

### XAI Explanation
* **Risk Score:** 100 (Critical)
* **Recommended Next Step:** `recommend_isolation_with_human_approval`
* **Evidence Items (7):**
  1. High number of failed login attempts
  2. Large outbound data transfer
  3. Abnormally high process count
  4. Login/source country is outside normal profile
  5. Suspicious event type: `privilege_escalation`
  6. Isolation Forest marked this event as anomalous
  7. User-specific fingerprint deviation ($z = 256.2106$)

---

### RAI Decision (`RAI Policy Agent`)
* **Allowed:** `true`
* **Recommended Action:** `recommend_isolation_with_human_approval`
* **Policy Note:** High risk. Isolation may be recommended, but human approval is required.
* **Human Approval Required:** `true`
* **Policy Evidence Count:** 7

---

### Meta-AI Review (`Meta-AI Supervisory Agent`)
* **Approved:** `true`
* **Disposition:** `approve`
* **Issues:** None
* **Questions / Requests:** None
* **Uncertainty:** 0
* **Reflection:** Decision is sufficiently supported for governed continuation.

---

### Correlation & Metadata
* **Correlation ID:** `a0b6d3b3-1034-4cc9-a580-306713c603ee`
* **Status:** Pending Analyst Review / Human Decision





# Morpheus Lite Agentic SOC Dashboard - Redpanda Console Trace Report

**Pipeline Flow:** Kafka → Detection → Agent Orchestration → RAI → Meta-AI → Human Decision  
**Target Alert ID:** `alert-0-91`  
**Correlation ID:** `a0b6d3b3-1034-4cc9-a580-306713c603ee`

---

## Topic Inspection Summary Table

| Topic | What you found |
| :--- | :--- |
| **raw.logs** | Ingestion of raw telemetry for user `svc-backup` on `host-02` from IP `91.240.118.9` (Country: `KP`), showing a `privilege_escalation` event with 21 failed logins, 35,358,658 bytes out, and 324 processes. |
| **morpheus.alerts** | The generated alert record (`alert-0-91`) flagging a risk score of 100, driven by an Isolation Forest anomaly score (`-0.0793`) and a max user fingerprint z-score of `256.2106`, with status set to `new`. |
| **agent.investigations** | Orchestrated agent payload grouping the alert details, Threat Hunter findings, MITRE mappings, RAI policy evaluation, deterministic XAI output, and Meta-AI review, with status `awaiting_human_decision`. |
| **agent.explanations** | Detailed output from the `deterministic XAI Agent` (`rule-based-explainer`), providing 7 distinct evidence items, confidence 1, and noting a local model fallback (`http://localhost:11434/api/generate` 404 error). |
| **audit.rai** | `RAI Policy Agent` audit log confirming `allowed: true`, recommending `recommend_isolation_with_human_approval`, requiring human approval (`true`), and recording 7 policy evidence items. |
| **agent.meta_ai** | `Meta-AI Supervisory Agent` review confirming `approved: true`, `disposition: approve`, zero uncertainty, and the reflection: *"Decision is sufficiently supported for governed continuation."* |
| **human.decisions** | The final event queue destination capturing the case state awaiting the analyst's manual decision and justification for `alert-0-91`. |

---

## Detailed JSON Payloads Extracted

### 1. `raw.logs` Payload
```json
{
  "event_id": "089a75e0-30b4-4ab4-b19e-fcf55992b799",
  "correlation_id": "a0b6d3b3-1034-4cc9-a580-306713c603ee",
  "timestamp": "2026-07-27T16:38:00.033900+00:00",
  "user": "svc-backup",
  "host": "host-02",
  "src_ip": "91.240.118.9",
  "event_type": "privilege_escalation",
  "failed_logins": 21,
  "bytes_out": 35358658,
  "process_count": 324,
  "country": "KP",
  "label": "suspicious",
  "schema_version": "1.0"
}
```

### 2. `morpheus.alerts` Payload
```json
{
  "alert_id": "alert-0-91",
  "correlation_id": "a0b6d3b3-1034-4cc9-a580-306713c603ee",
  "risk_score": 100,
  "detector": "isolation-forest-plus-user-fingerprint",
  "ml_model": "IsolationForest",
  "isolation_forest_prediction": -1,
  "anomaly_score": -0.07939423713885818,
  "fingerprint": {
    "user": "svc-backup",
    "profile_samples": 200,
    "max_z_score": 256.2106,
    "user_specific": true
  },
  "features": {
    "failed_logins": 21,
    "bytes_out": 35358658,
    "process_count": 324,
    "risky_country": 1,
    "suspicious_event_type": 1
  },
  "reasons": [
    "high number of failed login attempts",
    "large outbound data transfer",
    "abnormally high process count",
    "login/source country is outside normal profile",
    "suspicious event type: privilege_escalation",
    "Isolation Forest marked this event as anomalous",
    "user-specific fingerprint deviation z=256.2106"
  ],
  "status": "new"
}
```

### 3. `agent.explanations` Payload
```json
{
  "agent": "deterministic XAI Agent",
  "alert_id": "alert-0-91",
  "plain_language_explanation": "Risk score 100. Strongest evidence: high number of failed login attempts; large outbound data transfer; abnormally high process count; login/source country is outside normal profile; suspicious event type: privilege_escalation; Isolation Forest marked this event as anomalous; user-specific fingerprint deviation z=256.2106.",
  "evidence": [
    "high number of failed login attempts",
    "large outbound data transfer",
    "abnormally high process count",
    "login/source country is outside normal profile",
    "suspicious event type: privilege_escalation",
    "Isolation Forest marked this event as anomalous",
    "user-specific fingerprint deviation z=256.2106"
  ],
  "confidence": 1,
  "provider": "deterministic",
  "model": "rule-based-explainer",
  "latency_ms": 0,
  "fallback_used": true,
  "provider_metadata": {
    "fallback_reason": "404 Client Error: Not Found for url: http://localhost:11434/api/generate"
  }
}
```

### 4. `audit.rai` Payload
```json
{
  "agent": "RAI Policy Agent",
  "allowed": true,
  "recommended_action": "recommend_isolation_with_human_approval",
  "policy_note": "High risk. Isolation may be recommended, but human approval is required.",
  "human_approval_required": true,
  "policy_evidence_count": 7
}
```

### 5. `agent.meta_ai` Payload
```json
{
  "agent": "Meta-AI Supervisory Agent",
  "approved": true,
  "disposition": "approve",
  "issues": [],
  "questions_or_requests": [],
  "uncertainty": 0,
  "reflection": "Decision is sufficiently supported for governed continuation."
}
```


##Strongest evidence:High user-specific fingerprint deviation ($z = 256.2106$), Isolation Forest anomaly classification (-1), 21 failed login attempts, an abnormally high process count (324), and large outbound data transfer (35.3 MB) from an unusual source country (KP).

##Missing or weak evidence:None significant; all expected telemetry features and multi-agent validation layers (XAI, RAI, and Meta-AI) are fully populated and consistent.




# Morpheus Lite Agentic SOC - Section 6 Analysis

## 6.1 Detection and Evidence
* **Strongest evidence:** User-specific fingerprint deviation ($z = 256.2106$), Isolation Forest anomaly classification, high number of failed login attempts (21), large outbound data transfer (35.3 MB), abnormally high process count (324), and login from an unusual country outside normal profile (KP).
* **Missing or weak evidence:** None; all telemetry vectors, statistical anomaly flags, and policy guardrail items are fully present and strongly aligned.

## 6.2 XAI Explanation
* **What triggered the alert?** A highly anomalous privilege_escalation event featuring extreme statistical deviation ($z = 256.2106$), an Isolation Forest anomaly flag, 21 failed logins, and massive outbound data transfer originating from an untrusted country profile (KP).
* **Does the explanation match the displayed evidence?** Yes, the XAI explanation maps directly and accurately to all 7 items listed in the evidence array.
* **Does it clearly distinguish observed evidence from interpretation?** Yes, it separates objective telemetry metrics (failed login count, data transfer volume, process count, country) from model-driven interpretations (Isolation Forest anomaly classification and fingerprint z-score deviation).
* **Does it overstate certainty?** No, it maintains a confidence score of 1 based on robust, multi-factor anomaly signals without making unwarranted assumptions about intent.
* **What additional evidence would improve confidence?** Internal network flow telemetry (such as destination IP reputation or lateral movement logs) or process lineage command-line arguments.

## 6.3 RAI Decision
* **RAI interpretation:** The policy permits the recommended action (recommend_isolation_with_human_approval) because the risk score is critically high (100) and backed by 7 distinct policy evidence items. However, the policy explicitly limits automated execution by enforcing a strict guardrail (human_approval_required: true), meaning isolation cannot be performed automatically and remains legally/operationally dependent on human authorization.

## 6.4 Meta-AI Review
* **Meta-AI interpretation:** The Meta-AI review largely confirmed the pipeline recommendation (approved: true, disposition: approve, uncertainty: 0) rather than aggressively challenging it. Its reflection notes that the decision is "sufficiently supported for governed continuation," indicating it validated the logical coherence and policy alignment of the upstream outputs rather than flagging dissenting issues or requesting modifications.

## 7. Human Decision

* **Selected Decision:** `approve`

## Write a Justification
* **Chosen Decision:** `approve`
* **Evidence Considered:** Telemetry indicating 21 failed login attempts, 35.3 MB of outbound data transfer, 324 processes, source location in country `KP`, Isolation Forest anomaly prediction (`-1`), and a user-specific fingerprint deviation of $z = 256.2106$ resulting in a risk score of 100.
* **Interpretation of the Evidence:** The convergence of extreme statistical anomaly ($z = 256.2106$), high-volume outbound data transfer, failed logins, and unauthorized privilege escalation strongly indicates an active, severe host compromise rather than benign operational noise.
* **Uncertainty or Limitations:** While internal process lineage details and destination IP threat intel are absent from immediate logs, the multi-factor anomaly signals and independent policy/supervisory validation provide overwhelming corroboration.
* **Relevant Policy Constraint:** The RAI Policy Agent mandates that while isolation is recommended due to high risk (`recommend_isolation_with_human_approval`), human approval remains strictly required and authoritative before execution.
* **Why the Action is Proportionate:** Approving host isolation for an active compromise with a risk score of 100 and a fingerprint z-score of 256.2106 represents an immediate, necessary containment measure to prevent data 

## Verification Results

| Check Item | Result | Status |
| :--- | :--- | :--- |
| **Same `alert_id` visible** | Pass / Fail | **Pass** |
| **Decision changed from `pending`** | Pass / Fail | **Pass** |
| **Pending-review count updated** | Pass / Fail | **Pass** |
| **Decision visible in `human.decisions`** | Pass / Fail | **Pass** |
| **Justification preserved** | Pass / Fail | **Pass** |

# Morpheus Lite Agentic SOC - Post-Decision Reflection

* **Which evidence most influenced your decision?** The extreme user-specific fingerprint deviation ($z = 256.2106$), Isolation Forest anomaly prediction, and massive outbound data transfer (35.3 MB) from an unusual country (`KP`).
* **Did your decision agree with the AI recommendation? Why or why not?** Yes, because the convergence of multiple high-severity anomaly metrics and a risk score of 100 clearly warranted host isolation to prevent ongoing data exfiltration.
* **Did the RAI policy meaningfully constrain the action?** Yes, by strictly enforcing that human approval was required before isolation could be executed, preventing fully autonomous containment.
* **Did the Meta-AI review identify uncertainty or challenge the recommendation?** No, the Meta-AI review reported zero uncertainty and approved the recommendation, noting that it was sufficiently supported for governed continuation.
* **What additional evidence would have changed your decision?** Internal process execution command-line arguments or local endpoint verification confirming the activity was authorized maintenance.
* **At what point in the pipeline should human authority be strongest?** At the final decision stage before automated destructive actions (like host isolation or network blocking) are executed.
* **What are the risks of automatically executing the recommended action?** Unintended disruption of legitimate administrative tasks, business-critical service downtime, or false-positive containment of authorized backend processes.