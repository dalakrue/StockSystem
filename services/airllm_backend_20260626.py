"""Optional, explicit-request-only AirLLM server backend.

Importing this module never imports AirLLM, downloads a model, or starts
inference. The existing deterministic canonical assistant remains the fallback.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import threading
from typing import Any, Mapping

_LOCK = threading.Lock()
_MODEL: Any = None
_MODEL_ID: str | None = None


def _env_true(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def backend_status(runtime_enabled: bool | None = None, runtime_model_id: str | None = None) -> dict[str, Any]:
    enabled = bool(runtime_enabled) if runtime_enabled is not None else _env_true("ADX_ENABLE_AIRLLM")
    model_id = str(runtime_model_id or os.getenv("ADX_AIRLLM_MODEL_ID", os.getenv("ADX_AIRLLM_MODEL", "Qwen/Qwen2.5-0.5B-Instruct"))).strip()
    installed = importlib.util.find_spec("airllm") is not None if enabled else False
    return {
        "enabled": enabled,
        "model_id": model_id,
        "installed": installed,
        "ready_to_request": bool(enabled and model_id and installed),
        "allow_download": _env_true("ADX_AIRLLM_ALLOW_DOWNLOAD"),
        "execution": "server_only",
        "max_output_tokens": max(16, min(int(os.getenv("ADX_AIRLLM_MAX_OUTPUT_TOKENS", "160")), 256)),
        "max_context_chars": max(1000, min(int(os.getenv("ADX_AIRLLM_MAX_CONTEXT_CHARS", "5000")), 12000)),
    }


def compact_canonical_context(contract: Mapping[str, Any], status: Mapping[str, Any] | None = None) -> str:
    allowed = {
        "identity": contract.get("identity"),
        "current_decision": contract.get("current_decision"),
        "entry_decision": contract.get("entry_decision"),
        "less_risky_decision": contract.get("less_risky_decision"),
        "current_price": contract.get("current_price"),
        "tp_sl": contract.get("tp_sl"),
        "prediction_horizons": contract.get("prediction_horizons"),
        "session": contract.get("session"),
        "regime_standards": contract.get("regime_standards"),
        "reliability": contract.get("reliability"),
        "uncertainty": contract.get("uncertainty"),
        "system_health": contract.get("system_health"),
        "reversal_evidence": contract.get("reversal_evidence"),
        "history": contract.get("history"),
        "generation": contract.get("generation"),
        "broker_candle": contract.get("broker_candle"),
    }
    text = json.dumps(allowed, sort_keys=True, default=str, separators=(",", ":"))
    active = status or backend_status()
    return text[: int(active["max_context_chars"])]


def _load_model(status: Mapping[str, Any]) -> Any:
    global _MODEL, _MODEL_ID
    model_id = str(status.get("model_id") or "")
    if _MODEL is not None and _MODEL_ID == model_id:
        return _MODEL
    model_path = Path(model_id).expanduser()
    if not model_path.exists() and not bool(status.get("allow_download")):
        raise RuntimeError(
            "AirLLM model is not local and downloads are disabled. Set ADX_AIRLLM_ALLOW_DOWNLOAD=1 only for an explicit server deployment that has sufficient disk and network capacity."
        )
    # Lazy optional import occurs only after an explicit assistant request.
    from airllm import AutoModel  # type: ignore

    kwargs: dict[str, Any] = {}
    device = os.getenv("ADX_AIRLLM_DEVICE", "").strip()
    if not device:
        try:
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            device = "cpu"
    kwargs["device"] = device
    _MODEL = AutoModel.from_pretrained(model_id, **kwargs)
    _MODEL_ID = model_id
    return _MODEL


def generate_grounded_answer(question: str, contract: Mapping[str, Any], *, runtime_enabled: bool | None = None, runtime_model_id: str | None = None) -> dict[str, Any]:
    status = backend_status(runtime_enabled=runtime_enabled, runtime_model_id=runtime_model_id)
    if not status["enabled"]:
        return {"ok": False, "status": "DISABLED", "error": "AirLLM is disabled."}
    if not status["model_id"]:
        return {"ok": False, "status": "MODEL_ID_MISSING", "error": "ADX_AIRLLM_MODEL_ID is not configured."}
    if not status["installed"]:
        return {"ok": False, "status": "PACKAGE_UNAVAILABLE", "error": "The optional airllm package is not installed."}
    if not _LOCK.acquire(blocking=False):
        return {"ok": False, "status": "BUSY", "error": "Another AirLLM request is already running."}
    try:
        model = _load_model(status)
        context = compact_canonical_context(contract, status)
        prompt = (
            "You are a read-only EURUSD H1 assistant. Use only the canonical JSON below. "
            "Do not invent history, accuracy, evidence, news, weights, outcomes, or performance. "
            "Do not change BUY/SELL/WAIT/HOLD/NO-TRADE logic. State unavailable facts as unavailable.\n"
            f"CANONICAL_JSON={context}\nQUESTION={str(question)[:1000]}\nANSWER="
        )
        max_input = max(128, min(int(os.getenv("ADX_AIRLLM_MAX_INPUT_TOKENS", "768")), 2048))
        tokens = model.tokenizer(
            [prompt], return_tensors="pt", return_attention_mask=False,
            truncation=True, max_length=max_input, padding=False,
        )
        input_ids = tokens["input_ids"]
        device = os.getenv("ADX_AIRLLM_DEVICE", "").strip().lower()
        if device.startswith("cuda") and hasattr(input_ids, "cuda"):
            input_ids = input_ids.cuda()
        output = model.generate(
            input_ids,
            max_new_tokens=int(status["max_output_tokens"]),
            use_cache=True,
            return_dict_in_generate=True,
        )
        decoded = model.tokenizer.decode(output.sequences[0], skip_special_tokens=True)
        answer = decoded[len(prompt):].strip() if decoded.startswith(prompt) else decoded.strip()
        if not answer:
            raise RuntimeError("AirLLM returned an empty response.")
        return {"ok": True, "status": "COMPLETE", "answer": answer, "model_id": status["model_id"]}
    except Exception as exc:
        return {"ok": False, "status": "FAILED", "error": f"{type(exc).__name__}: {exc}"}
    finally:
        _LOCK.release()


__all__ = ["backend_status", "compact_canonical_context", "generate_grounded_answer"]
