"""Intent classifier using calibrated DistilBERT with LLM fallback."""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from src.services.agentic_ai.agents.intent_taxonomy import INTENT_TYPES

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_AVAILABLE = bool(OPENAI_API_KEY)


class IntentClassifierAgent:
    """Model-first intent classifier with calibrated confidence thresholding."""

    def __init__(self):
        self.model_dir = Path("src/services/agentic_ai/agents/models/intent_distilbert")
        self.inference_config: Dict[str, Any] = {}
        self.model_loaded = False
        self.tokenizer = None
        self.model = None

        self._init_model()
        self._init_llm()

    def _init_model(self) -> None:
        if not self.model_dir.exists():
            logger.warning("DistilBERT intent model directory not found: %s", self.model_dir)
            return

        try:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer

            cfg_path = self.model_dir / "intent_inference_config.json"
            if cfg_path.exists():
                self.inference_config = json.loads(cfg_path.read_text(encoding="utf-8"))
            else:
                self.inference_config = {
                    "temperature": 1.0,
                    "confidence_threshold": 0.65,
                    "ambiguity_margin": 0.08,
                    "id2label": {str(i): label for i, label in enumerate(INTENT_TYPES)},
                }

            self.tokenizer = AutoTokenizer.from_pretrained(self.model_dir)
            self.model = AutoModelForSequenceClassification.from_pretrained(self.model_dir)
            self.model.eval()
            self._torch = torch
            self.model_loaded = True
            logger.info("Loaded calibrated DistilBERT intent model from %s", self.model_dir)
        except Exception as exc:
            logger.error("Failed to load DistilBERT intent model: %s", exc)
            self.model_loaded = False

    def _init_llm(self) -> None:
        self.llm_enabled = OPENAI_AVAILABLE
        self.client = None
        if self.llm_enabled:
            try:
                from openai import OpenAI

                self.client = OpenAI(api_key=OPENAI_API_KEY)
            except Exception as exc:
                logger.warning("OpenAI init failed for fallback: %s", exc)
                self.llm_enabled = False

    def _predict_with_model(self, query: str) -> Optional[Dict[str, Any]]:
        if not self.model_loaded:
            return None

        inputs = self.tokenizer(query, truncation=True, padding=True, max_length=64, return_tensors="pt")
        with self._torch.no_grad():
            logits = self.model(**inputs).logits

        temperature = float(self.inference_config.get("temperature", 1.0))
        probs = self._torch.softmax(logits / max(temperature, 1e-6), dim=-1).cpu().numpy()[0]
        sorted_indices = probs.argsort()[::-1]
        pred_idx = int(sorted_indices[0])
        second_idx = int(sorted_indices[1]) if len(sorted_indices) > 1 else pred_idx
        confidence = float(probs[pred_idx])
        second_confidence = float(probs[second_idx])
        score_margin = confidence - second_confidence

        id2label = self.inference_config.get("id2label", {})
        intent = id2label.get(str(pred_idx), "product_search")
        second_intent = id2label.get(str(second_idx), intent)
        threshold = float(self.inference_config.get("confidence_threshold", 0.65))
        ambiguity_margin = float(self.inference_config.get("ambiguity_margin", 0.08))

        candidates = [
            {"intent": intent, "confidence": confidence},
            {"intent": second_intent, "confidence": second_confidence},
        ]

        if confidence < threshold:
            return {
                "intent": intent,
                "confidence": confidence,
                "reasoning": "Calibrated DistilBERT confidence below threshold",
                "fallback": True,
                "source": "distilbert_low_confidence",
                "action": "fallback_low_confidence",
                "second_intent": second_intent,
                "second_confidence": second_confidence,
                "score_margin": score_margin,
                "confidence_threshold": threshold,
                "ambiguity_margin": ambiguity_margin,
                "candidates": candidates,
            }

        if score_margin < ambiguity_margin:
            return {
                "intent": "clarification",
                "confidence": confidence,
                "reasoning": "Top two intents are too close; clarification required",
                "fallback": True,
                "source": "distilbert_ambiguous",
                "action": "ask_clarification",
                "top_intent": intent,
                "second_intent": second_intent,
                "second_confidence": second_confidence,
                "score_margin": score_margin,
                "confidence_threshold": threshold,
                "ambiguity_margin": ambiguity_margin,
                "candidates": candidates,
            }

        return {
            "intent": intent,
            "confidence": confidence,
            "reasoning": "Calibrated DistilBERT prediction accepted",
            "fallback": False,
            "source": "distilbert_calibrated",
            "action": "accept",
            "second_intent": second_intent,
            "second_confidence": second_confidence,
            "score_margin": score_margin,
            "confidence_threshold": threshold,
            "ambiguity_margin": ambiguity_margin,
            "candidates": candidates,
        }

    def _classify_with_llm(self, query: str, user_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self.llm_enabled or self.client is None:
            return {
                "intent": "product_search",
                "confidence": 0.0,
                "reasoning": "No model/LLM available",
                "fallback": True,
                "source": "default",
            }

        intents_text = "\n".join([f"- {name}" for name in INTENT_TYPES])
        context_text = json.dumps(user_context or {}, ensure_ascii=True)
        prompt = (
            "Classify fashion assistant intent. Return strict JSON with keys intent, confidence, reasoning.\n"
            f"Allowed intents:\n{intents_text}\n"
            f"Context: {context_text}\n"
            f"Query: {query}"
        )

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a strict JSON intent classifier."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,
                max_tokens=120,
            )
            text = response.choices[0].message.content.strip()
            parsed = json.loads(text)
            intent = parsed.get("intent", "product_search")
            if intent not in INTENT_TYPES:
                intent = "product_search"
            confidence = float(parsed.get("confidence", 0.6))
            return {
                "intent": intent,
                "confidence": max(0.0, min(1.0, confidence)),
                "reasoning": parsed.get("reasoning", "LLM fallback classification"),
                "fallback": True,
                "source": "llm_fallback",
            }
        except Exception as exc:
            logger.warning("LLM fallback failed: %s", exc)
            return {
                "intent": "product_search",
                "confidence": 0.0,
                "reasoning": "LLM fallback failed",
                "fallback": True,
                "source": "default",
            }

    def classify_intent(self, query: str, user_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        result = self._predict_with_model(query)
        if result:
            action = result.get("action", "accept")
            if action == "accept":
                return result
            if action == "ask_clarification":
                return result

            llm_result = self._classify_with_llm(query, user_context)
            llm_result["model_hint"] = {
                "reason": result.get("reasoning"),
                "candidates": result.get("candidates", []),
                "score_margin": result.get("score_margin"),
                "confidence_threshold": result.get("confidence_threshold"),
                "ambiguity_margin": result.get("ambiguity_margin"),
            }
            return llm_result
        return self._classify_with_llm(query, user_context)


_intent_classifier = None


def get_intent_classifier() -> IntentClassifierAgent:
    global _intent_classifier
    if _intent_classifier is None:
        _intent_classifier = IntentClassifierAgent()
    return _intent_classifier
