from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import joblib
except Exception:  # pragma: no cover
    joblib = None

try:
    import numpy as np
except Exception:  # pragma: no cover
    np = None

from src.services.agentic_ai.agents.ltr_support import FEATURE_ORDER
from src.services.agentic_ai.featureops.orchestrator import AgenticSemanticFeatureOps
from src.services.agentic_ai.kg.scoring import KGScoringService


class MultiStageRanker:
    """Governed two-stage ranker replacing the legacy weighted equation."""
    FEATURE_ORDER = FEATURE_ORDER

    def __init__(self, kg_scorer: KGScoringService):
        self.kg_scorer = kg_scorer
        self.featureops = AgenticSemanticFeatureOps()
        self.model, self.model_metadata = self._load_ranker()

    @staticmethod
    def _normalize(value: Any) -> float:
        try:
            return float(value)
        except Exception:
            return 0.0

    def _load_ranker(self):
        model_path = Path(__file__).resolve().parent / "models" / "ltr" / "lambdamart_ranker.joblib"
        if not model_path.exists() or joblib is None:
            return None, {}
        try:
            artifact = joblib.load(model_path)
            if isinstance(artifact, dict) and "model" in artifact:
                return artifact.get("model"), artifact
            return artifact, {}
        except Exception:
            return None, {}

    @staticmethod
    def _lower(value: Any) -> str:
        return str(value or "").strip().lower()

    def _intent_match(self, candidate: Dict[str, Any], intent: Dict[str, Any]) -> Tuple[float, List[str]]:
        if not intent:
            return 0.5, []
        score = 0.0
        reasons: List[str] = []
        if intent.get("category") and self._lower(intent.get("category")) in self._lower(candidate.get("category")):
            score += 0.45
            reasons.append("Matches your requested category.")
        if intent.get("color") and self._lower(intent.get("color")) in self._lower(candidate.get("color")):
            score += 0.30
            reasons.append("Matches your requested color.")
        if intent.get("occasion"):
            tags = [self._lower(tag) for tag in (candidate.get("normalized_style_tags") or candidate.get("style_tags") or [])]
            if self._lower(intent.get("occasion")) in tags:
                score += 0.25
                reasons.append("Fits the requested occasion.")
        return min(score, 1.0), reasons

    def _profile_affinity(self, candidate: Dict[str, Any], prefs: Dict[str, Any]) -> Tuple[float, List[str]]:
        if not prefs:
            return 0.5, []
        score = 0.0
        reasons: List[str] = []
        categories = [self._lower(v) for v in prefs.get("top_categories", [])]
        colors = [self._lower(v) for v in prefs.get("top_colors", [])]
        shops = {self._lower(v) for v in prefs.get("preferred_shops", [])}
        tag_freq = {self._lower(k): v for k, v in (prefs.get("style_tag_frequency") or {}).items()}
        candidate_tags = {self._lower(v) for v in (candidate.get("normalized_style_tags") or candidate.get("style_tags") or [])}

        if self._lower(candidate.get("category")) in categories:
            score += 0.35
            reasons.append("Aligned with your frequent categories.")
        if self._lower(candidate.get("color")) in colors:
            score += 0.25
            reasons.append("Aligned with your preferred colors.")
        if self._lower(candidate.get("shop_id")) in shops or self._lower(candidate.get("_shop_name") or candidate.get("shop_name") or candidate.get("shop")) in shops:
            score += 0.20
            reasons.append("From one of your preferred shops.")
        if candidate_tags & set(tag_freq.keys()):
            score += 0.20
            reasons.append("Aligned with your style-tag history.")
        return min(score, 1.0), reasons

    def _graph_affinities(self, candidate: Dict[str, Any], graph_scores: Dict[str, Dict[str, Any]]) -> Tuple[float, float, List[str]]:
        product_id = str(candidate.get("product_id") or "")
        payload = graph_scores.get(product_id) or {}
        graph_score = self._normalize(payload.get("graph_score"))
        behavior_affinity = min(graph_score * 1.1, 1.0)
        collaborative_affinity = min(graph_score * 0.9, 1.0)
        reasons = list(payload.get("graph_reasons") or [])
        return behavior_affinity, collaborative_affinity, reasons

    def _price_fit(self, candidate: Dict[str, Any], intent: Dict[str, Any], prefs: Dict[str, Any]) -> float:
        price = self._normalize(candidate.get("price") or candidate.get("price_LKR"))
        budget = self._normalize(intent.get("max_price") or ((prefs or {}).get("price_range") or {}).get("max"))
        if budget <= 0:
            return 0.65
        if price <= budget:
            return 1.0
        return max(0.0, 1.0 - ((price - budget) / max(budget, 1.0)))

    def _context_signal(self, candidate: Dict[str, Any], context: Dict[str, Any], intent: Dict[str, Any]) -> float:
        signal = 1.0
        hour = self._normalize((context or {}).get("time_of_day"))
        device = self._lower((context or {}).get("device"))
        occasion = self._lower((intent or {}).get("occasion"))
        tags = {self._lower(t) for t in (candidate.get("normalized_style_tags") or candidate.get("style_tags") or [])}

        if 18 <= hour <= 22 and self._normalize(candidate.get("popularity_score")) >= 4.0:
            signal *= 1.08
        if device == "mobile" and self._normalize(candidate.get("popularity_score")) >= 3.5:
            signal *= 1.05
        if occasion and occasion in tags:
            signal *= 1.08
        return max(0.6, min(signal, 1.2))

    @staticmethod
    def _trust_signal(feature_statuses: Dict[str, str]) -> float:
        if not feature_statuses:
            return 0.85
        statuses = list(feature_statuses.values())
        if any(status == "QUARANTINED" for status in statuses):
            return 0.15
        if any(status == "CONDITIONAL" for status in statuses):
            return 0.75
        return 1.0

    def _govern_features(self, feature_vectors: List[Dict[str, float]], lineage: Dict[str, Any]) -> Dict[str, str]:
        columns: Dict[str, List[Any]] = {name: [] for name in self.FEATURE_ORDER}
        for vector in feature_vectors:
            for name in self.FEATURE_ORDER:
                columns[name].append(vector.get(name))
        return self.featureops.govern_feature_bundle(columns, lineage=lineage)

    def _predict_rank_score(self, vector: Dict[str, float]) -> float:
        # Non-linear fallback: geometric fusion instead of an arbitrary linear weighted sum.
        relevance = max(vector.get("semantic_similarity", 0.05), 0.05)
        affinity = max((vector.get("profile_affinity", 0.0) + vector.get("behavior_affinity", 0.0) + vector.get("collaborative_affinity", 0.0)) / 3.0, 0.05)
        commercial = max((vector.get("price_fit", 0.0) + vector.get("popularity_signal", 0.0)) / 2.0, 0.05)
        trust = max(vector.get("trust_signal", 0.05), 0.05)
        context_signal = max(vector.get("context_signal", 0.8), 0.2)
        score = math.sqrt(relevance * affinity) * math.sqrt(commercial * trust) * context_signal
        return max(0.0, min(1.0, score))

    def _predict_model_scores(self, vectors: List[Dict[str, float]]) -> Optional[List[float]]:
        if self.model is None or np is None or not vectors:
            return None
        try:
            matrix = np.asarray([[vector.get(name, 0.0) for name in self.FEATURE_ORDER] for vector in vectors], dtype=float)
            raw = self.model.predict(matrix)
            raw_scores = [float(value) for value in raw]
            if not raw_scores:
                return None
            min_score = min(raw_scores)
            max_score = max(raw_scores)
            if max_score - min_score < 1e-9:
                return [0.75 for _ in raw_scores]
            return [max(0.0, min(1.0, (score - min_score) / (max_score - min_score))) for score in raw_scores]
        except Exception:
            return None

    def _mmr_diversify(self, ranked_rows: List[Dict[str, Any]], top_k: int = 6) -> List[Dict[str, Any]]:
        selected: List[Dict[str, Any]] = []
        remaining = list(ranked_rows)

        def similarity(a: Dict[str, Any], b: Dict[str, Any]) -> float:
            a_product = a["product"]
            b_product = b["product"]
            sim = 0.0
            if self._lower(a_product.get("category")) == self._lower(b_product.get("category")):
                sim += 0.35
            if self._lower(a_product.get("color")) == self._lower(b_product.get("color")):
                sim += 0.20
            if self._lower(a_product.get("shop_id")) == self._lower(b_product.get("shop_id")):
                sim += 0.20
            if set(self._lower(t) for t in (a_product.get("normalized_style_tags") or [])) & set(self._lower(t) for t in (b_product.get("normalized_style_tags") or [])):
                sim += 0.25
            return min(sim, 1.0)

        while remaining and len(selected) < top_k:
            if not selected:
                selected.append(remaining.pop(0))
                continue

            best_idx = 0
            best_score = float("-inf")
            for idx, row in enumerate(remaining):
                redundancy = max(similarity(row, chosen) for chosen in selected)
                mmr = (0.8 * row["score"]) - (0.2 * redundancy)
                if mmr > best_score:
                    best_idx = idx
                    best_score = mmr
            selected.append(remaining.pop(best_idx))

        return selected

    def rank_candidates(
        self,
        user_id: Optional[str],
        candidates: List[Dict[str, Any]],
        user_preferences: Optional[Dict[str, Any]],
        intent: Optional[Dict[str, Any]],
        context: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if not candidates:
            return {"results": [], "best_matches": [], "new_suggestions": [], "explanations": {}}

        prefs = user_preferences or {}
        graph_scores = self.kg_scorer.score_candidates(user_id, candidates, intent=intent)
        feature_vectors: List[Dict[str, float]] = []
        row_payloads: List[Dict[str, Any]] = []

        for candidate in candidates:
            semantic_similarity = self._normalize(candidate.get("_similarity_score") or candidate.get("similarity_score") or 0.55)
            intent_match, intent_reasons = self._intent_match(candidate, intent or {})
            profile_affinity, profile_reasons = self._profile_affinity(candidate, prefs)
            behavior_affinity, collaborative_affinity, graph_reasons = self._graph_affinities(candidate, graph_scores)
            price_fit = self._price_fit(candidate, intent or {}, prefs)
            popularity_signal = min(max(self._normalize(candidate.get("popularity_score")) / 5.0, 0.0), 1.0)
            context_signal = self._context_signal(candidate, context or {}, intent or {})

            vector = {
                "semantic_similarity": semantic_similarity,
                "intent_match": intent_match,
                "profile_affinity": profile_affinity,
                "behavior_affinity": behavior_affinity,
                "collaborative_affinity": collaborative_affinity,
                "price_fit": price_fit,
                "popularity_signal": popularity_signal,
                "context_signal": context_signal,
                "trust_signal": 1.0,  # populated after governance
            }
            feature_vectors.append(vector)
            row_payloads.append(
                {
                    "product": candidate,
                    "vector": vector,
                    "reasons": intent_reasons + profile_reasons + graph_reasons,
                }
            )

        feature_statuses = self._govern_features(
            feature_vectors=feature_vectors,
            lineage={
                "component": "agentic_semantic_featureops",
                "source_systems": ["data_architecture", "data_fabric", "data_mesh", "agentic_ai_local"],
                "ranking_model": "lambdamart_or_geometric_fallback",
            },
        )
        trust_signal = self._trust_signal(feature_statuses)
        scoring_vectors: List[Dict[str, float]] = []
        for payload in row_payloads:
            vector = dict(payload["vector"])
            vector["trust_signal"] = trust_signal
            scoring_vectors.append(vector)

        model_scores = self._predict_model_scores(scoring_vectors)

        ranked_rows: List[Dict[str, Any]] = []
        for idx, payload in enumerate(row_payloads):
            vector = scoring_vectors[idx]
            score = model_scores[idx] if model_scores is not None else self._predict_rank_score(vector)
            if trust_signal <= 0.2 and vector["semantic_similarity"] < 0.6:
                # Non-compensatory suppression for suspicious weak candidates.
                score *= 0.2
            ranked_rows.append(
                {
                    "product": payload["product"],
                    "score": score,
                    "stage_scores": vector,
                    "reasons": payload["reasons"] or ["Recommended from governed semantic ranking."],
                    "release_status": "QUARANTINED" if trust_signal <= 0.2 else ("CONDITIONAL" if trust_signal < 1.0 else "READY"),
                }
            )

        ranked_rows.sort(key=lambda item: item["score"], reverse=True)
        diversified = self._mmr_diversify(ranked_rows, top_k=6)

        results: List[Dict[str, Any]] = []
        for row in diversified:
            product = dict(row["product"])
            product["personalization_score"] = round(row["score"], 4)
            product["_why_reasons"] = list(dict.fromkeys(row["reasons"]))[:3]
            product["feature_release_status"] = row["release_status"]
            product["feature_stage_scores"] = {k: round(v, 4) for k, v in row["stage_scores"].items()}
            results.append(product)

        best_matches = results[:3]
        new_suggestions = []
        for item in results[3:6]:
            new_item = dict(item)
            new_item["why"] = item.get("_why_reasons") or ["Fresh governed suggestion."]
            similarity = self._normalize(item.get("_similarity_score"))
            if similarity >= 0.40:
                new_item["_show_match_score"] = True
                new_item["_match_score_percent"] = round(similarity * 100, 1)
            else:
                new_item["_show_match_score"] = False
                new_item["_match_score_percent"] = None
            new_suggestions.append(new_item)

        return {
            "results": results,
            "best_matches": best_matches,
            "new_suggestions": new_suggestions,
            "explanations": {
                "ranking_architecture": "semantic_retrieval + governed_featureops + learning_to_rank",
                "feature_statuses": feature_statuses,
                "trust_signal": round(trust_signal, 4),
                "model_used": "lambdamart" if model_scores is not None else "geometric_fallback",
                "model_metadata": {
                    "model_family": self.model_metadata.get("model_family"),
                    "trained_at": self.model_metadata.get("trained_at"),
                    "dataset_rows": self.model_metadata.get("dataset_rows"),
                    "dataset_queries": self.model_metadata.get("dataset_queries"),
                    "source_catalog": self.model_metadata.get("source_catalog"),
                    "metrics": self.model_metadata.get("metrics"),
                } if self.model_metadata else {},
            },
        }
