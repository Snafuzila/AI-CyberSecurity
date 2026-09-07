"""Minimal local-Ollama client for the research suite. Deliberately standalone (no
import from morpheus_lite.inference) to preserve the suite's existing decoupling from
the live Kafka pipeline -- see research/xai_rai_comparison/README.md."""
from __future__ import annotations

import os

import requests

DEFAULT_MODEL = os.getenv("MORPHEUS_XAI_RAI_LLM_MODEL", "llama3.1:8b")
DEFAULT_URL = os.getenv("MORPHEUS_XAI_RAI_OLLAMA_URL", "http://localhost:11434/api/generate")


def call_llama(prompt: str, model: str = DEFAULT_MODEL, url: str = DEFAULT_URL, timeout: int = 120) -> str:
    """Sends prompt to a local Ollama server and returns the model's text response.
    Raises requests.RequestException on connection failure or non-2xx status -- callers
    decide whether to abort or fall back to prompt-only output."""
    response = requests.post(url, json={"model": model, "prompt": prompt, "stream": False}, timeout=timeout)
    response.raise_for_status()
    return response.json()["response"].strip()
