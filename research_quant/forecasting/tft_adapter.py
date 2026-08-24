from __future__ import annotations
from typing import Any

class TFTAdapter:
    """Optional lazy adapter. The application remains functional without TFT libraries."""
    def __init__(self, model_path: str | None = None):
        self.model_path = model_path
        self.model: Any = None
        self.status = "MODEL_UNAVAILABLE"

    def load(self) -> str:
        try:
            import torch  # noqa: F401
            from pytorch_forecasting import TemporalFusionTransformer  # type: ignore
        except Exception:
            self.status = "MODEL_UNAVAILABLE"
            return self.status
        self.status = "RESEARCH_ONLY" if self.model_path else "MODEL_UNAVAILABLE"
        return self.status

    def predict(self, data):
        if self.model is None:
            return {"status": "MODEL_UNAVAILABLE", "reason": "Optional TFT artifact is not loaded."}
        return self.model.predict(data)
