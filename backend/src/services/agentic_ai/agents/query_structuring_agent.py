"""Inference wrapper for query structuring model (style/event/budget)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict

import joblib


class QueryStructuringAgent:
    def __init__(self, model_dir: str = "src/services/agentic_ai/agents/models/query_structurer"):
        self.model_dir = Path(model_dir)
        self.model = None
        self.vectorizer = None
        self.labels = {}
        self.enabled = False
        self._load()

    @staticmethod
    def _clean(text: str) -> str:
        text = (text or "").lower().strip()
        text = re.sub(r"[^a-z0-9\s]", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text

    def _load(self) -> None:
        model_path = self.model_dir / "query_structurer_model.pkl"
        vect_path = self.model_dir / "query_structurer_vectorizer.pkl"
        labels_path = self.model_dir / "query_structurer_labels.json"

        if not (model_path.exists() and vect_path.exists() and labels_path.exists()):
            return

        self.model = joblib.load(model_path)
        self.vectorizer = joblib.load(vect_path)
        self.labels = json.loads(labels_path.read_text(encoding="utf-8"))
        self.enabled = True

    def predict(self, query: str) -> Dict[str, Any]:
        if not self.enabled:
            return {
                "style": None,
                "event": None,
                "budget": None,
                "enabled": False,
            }

        X = self.vectorizer.transform([self._clean(query)])
        pred = self.model.predict(X)[0]

        style_labels = self.labels.get("style", [])
        event_labels = self.labels.get("event", [])
        budget_labels = self.labels.get("budget", [])

        style = style_labels[int(pred[0])] if int(pred[0]) < len(style_labels) else None
        event = event_labels[int(pred[1])] if int(pred[1]) < len(event_labels) else None
        budget = budget_labels[int(pred[2])] if int(pred[2]) < len(budget_labels) else None

        return {
            "style": style,
            "event": event,
            "budget": budget,
            "enabled": True,
        }


_query_structurer = None


def get_query_structuring_agent() -> QueryStructuringAgent:
    global _query_structurer
    if _query_structurer is None:
        _query_structurer = QueryStructuringAgent()
    return _query_structurer
