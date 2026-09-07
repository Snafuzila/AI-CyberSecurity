"""Phase 4: find one real NSL-KDD test event for each of the 4 agreement/disagreement
scenarios, run it through the Phase 2 payload generator and the Phase 3 orchestrator,
send the resulting prompts to a local Ollama Llama model, and print/save the IF vs AE
results side-by-side per scenario for direct XAI/RAI comparison."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import requests
import torch

from config import RunConfig
from data_pipeline import load_nsl_kdd
from enriched_payload import generate_enriched_payload, load_artifacts
from llm_client import DEFAULT_MODEL, DEFAULT_URL, call_llama
from llm_orchestrator import build_llm_prompt, rai_policy_evaluator

LAB_ROOT = Path(__file__).resolve().parents[2]

SCENARIOS = {
    "A: Both Alert (agreement on anomaly)": lambda ifp, aep: (ifp == 1) & (aep == 1),
    "B: Isolation Forest ONLY (disagreement)": lambda ifp, aep: (ifp == 1) & (aep == 0),
    "C: Autoencoder ONLY (disagreement)": lambda ifp, aep: (ifp == 0) & (aep == 1),
    "D: Both Normal (agreement on benign)": lambda ifp, aep: (ifp == 0) & (aep == 0),
}


def _score_all(artifacts, X_test: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if_scores = -artifacts.if_model.decision_function(X_test)
    with torch.no_grad():
        x_t = torch.tensor(X_test, dtype=torch.float32)
        ae_scores = torch.mean((artifacts.ae_net(x_t) - x_t) ** 2, dim=1).numpy()
    return if_scores, ae_scores


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--llm-model", default=DEFAULT_MODEL, help="Ollama model tag (default: %(default)s)")
    parser.add_argument("--ollama-url", default=DEFAULT_URL, help="Ollama generate endpoint (default: %(default)s)")
    parser.add_argument("--no-llm", action="store_true", help="Print prompts only; skip calling the local LLM")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    cfg = RunConfig(nsl_kdd_dir=LAB_ROOT / "data")
    dataset = load_nsl_kdd(cfg)
    artifacts = load_artifacts()
    thresholds = artifacts.manifest["thresholds"]

    if_scores, ae_scores = _score_all(artifacts, dataset.X_test)
    if_pred = (if_scores >= thresholds["Isolation_Forest"]).astype(int)
    ae_pred = (ae_scores >= thresholds["Autoencoder"]).astype(int)

    run_results: dict[str, dict] = {}

    for label, mask_fn in SCENARIOS.items():
        matches = np.where(mask_fn(if_pred, ae_pred))[0]
        print("\n" + "=" * 100)
        print(label)
        print("=" * 100)
        if len(matches) == 0:
            print("No test event matches this scenario.")
            continue

        idx = int(matches[0])
        event = dataset.test_raw.iloc[idx]
        event_id = f"scenario-{label[0]}-idx{idx}"
        if_payload, ae_payload = generate_enriched_payload(event, event_id)

        scenario_result = {"event_id": event_id, "models": {}}
        for payload in (if_payload, ae_payload):
            decision = rai_policy_evaluator(payload)
            prompt = build_llm_prompt(payload, decision)
            print(f"\n--- {payload['triggering_model']} prompt (predicted_class={payload['predicted_class']}) ---")
            print(prompt)

            model_result = {
                "payload": payload,
                "rai_decision": decision,
                "prompt": prompt,
                "llm_response": None,
                "llm_error": None,
            }
            if not args.no_llm:
                print(f"--- {payload['triggering_model']} response ({args.llm_model}) ---")
                try:
                    response_text = call_llama(prompt, model=args.llm_model, url=args.ollama_url)
                    print(response_text)
                    model_result["llm_response"] = response_text
                except requests.RequestException as exc:
                    error_msg = f"LLM call failed ({exc}); is `ollama serve` running with {args.llm_model} pulled?"
                    print(error_msg)
                    model_result["llm_error"] = error_msg

            scenario_result["models"][payload["triggering_model"]] = model_result
        run_results[label] = scenario_result

    if not args.no_llm:
        output_dir = cfg.output_dir / time.strftime("%Y%m%d-%H%M%S")
        output_dir.mkdir(parents=True, exist_ok=True)
        report_path = output_dir / "scenario_comparison.json"
        report_path.write_text(json.dumps(run_results, indent=2), encoding="utf-8")
        print(f"\nSaved full IF-vs-AE comparison (prompts + LLM responses) to {report_path}")


if __name__ == "__main__":
    main()
