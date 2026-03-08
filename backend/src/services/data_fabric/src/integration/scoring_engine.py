"""Relationship scoring engine with LR/RF ensemble + static fallback."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
import logging
import sys

import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)


class RelationshipScoringEngine:
    """Scores candidate relationships using ML when available.

    Supported modes:
    - LR only: use LogisticRegression probability.
    - Secondary model only: use tree-model probability.
    - LR + secondary model: ensemble by weighted average.
    - No ML: static weighted fallback.

    Static fallback:

        confidence = (
            0.3 * name_similarity +
            0.2 * type_score +
            0.5 * overlap_ratio
        )
    """

    DEFAULT_FEATURE_ORDER: Sequence[str] = (
        "name_similarity",
        "type_score",
        "overlap_ratio",
    )

    def __init__(
        self,
        model_path: Optional[str] = None,
        model_version: str = "v1.0",
        name_weight: float = 0.3,
        type_weight: float = 0.2,
        overlap_weight: float = 0.5,
        lr_weight: float = 0.3,
        rf_weight: float = 0.7,
        strong_threshold: float = 0.80,
        probable_threshold: float = 0.5,
        rf_model_path: Optional[str] = None,
    ):
        self.model_version = model_version
        self.model_path: Optional[str] = None
        self.name_weight = float(name_weight)
        self.type_weight = float(type_weight)
        self.overlap_weight = float(overlap_weight)
        self.lr_weight = float(lr_weight)
        self.rf_weight = float(rf_weight)
        self.strong_threshold = float(strong_threshold)
        self.probable_threshold = float(probable_threshold)

        self.model: Optional[LogisticRegression] = None
        self.scaler: Optional[StandardScaler] = None
        self.feature_order: List[str] = list(self.DEFAULT_FEATURE_ORDER)

        self.rf_model: Optional[RandomForestClassifier | GradientBoostingClassifier] = None
        self.rf_scaler: Optional[StandardScaler] = None
        self.rf_feature_order: List[str] = list(self.DEFAULT_FEATURE_ORDER)
        self.rf_model_label: str = "RF"

        if model_path:
            candidate = Path(model_path)
            if candidate.exists():
                self.load_model(str(candidate))

        if rf_model_path:
            candidate = Path(rf_model_path)
            if candidate.exists():
                self.load_model(str(candidate))

    @property
    def has_model(self) -> bool:
        return self.has_lr_model or self.has_rf_model

    @property
    def has_lr_model(self) -> bool:
        return self.model is not None and self.scaler is not None

    @property
    def has_rf_model(self) -> bool:
        return self.rf_model is not None

    def fit(
        self,
        X: Sequence[Sequence[float]] | np.ndarray,
        y: Sequence[int] | np.ndarray,
        feature_order: Optional[Sequence[str]] = None,
        **kwargs,
    ) -> None:
        """Train a LogisticRegression model for relationship scoring."""
        X_np = np.asarray(X, dtype=float)
        y_np = np.asarray(y, dtype=int)
        if X_np.ndim != 2:
            raise ValueError("X must be a 2D array-like")
        if len(X_np) != len(y_np):
            raise ValueError("X and y must have the same number of rows")

        self.feature_order = list(feature_order) if feature_order else list(self.DEFAULT_FEATURE_ORDER)
        if len(self.feature_order) != X_np.shape[1]:
            raise ValueError("feature_order length must match number of columns in X")

        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X_np)

        params = {"max_iter": 1000}
        params.update(kwargs)
        self.model = LogisticRegression(**params)
        self.model.fit(X_scaled, y_np)

    def _build_ordered_row(self, feature_vector: Dict[str, float], ordered_features: Sequence[str]) -> np.ndarray:
        ordered = [self._coerce_float(feature_vector.get(name, 0.0)) for name in ordered_features]
        return np.asarray([ordered], dtype=float)

    @staticmethod
    def _coerce_float(value: Any) -> float:
        """Convert mixed feature values to float for model input.

        Some serialized model bundles may include feature names that map to
        version-like strings (for example, "v1.0"). These should not crash
        scoring; we coerce safely and fall back to 0.0 when parsing fails.
        """
        if value is None:
            return 0.0
        if isinstance(value, bool):
            return 1.0 if value else 0.0
        if isinstance(value, (int, float, np.number)):
            return float(value)
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return 0.0
            try:
                return float(text)
            except ValueError:
                # Accept common version format like "v1.0".
                if text.lower().startswith("v"):
                    try:
                        return float(text[1:])
                    except ValueError:
                        return 0.0
                return 0.0
        return 0.0

    def _predict_lr_probability(self, feature_vector: Dict[str, float]) -> Optional[float]:
        if not self.has_lr_model:
            return None
        row = self._build_ordered_row(feature_vector, self.feature_order)
        row_scaled = self.scaler.transform(row)
        return float(np.clip(self.model.predict_proba(row_scaled)[0, 1], 0.0, 1.0))

    def _predict_rf_probability(self, feature_vector: Dict[str, float]) -> Optional[float]:
        if not self.has_rf_model:
            return None
        row = self._build_ordered_row(feature_vector, self.rf_feature_order)
        if self.rf_scaler is not None:
            row = self.rf_scaler.transform(row)
        if not hasattr(self.rf_model, "predict_proba"):
            return None
        return float(np.clip(self.rf_model.predict_proba(row)[0, 1], 0.0, 1.0))

    def _fallback_score(self, feature_vector: Dict[str, float]) -> float:
        name_similarity = self._coerce_float(feature_vector.get("name_similarity", 0.0))
        type_score = self._coerce_float(feature_vector.get("type_score", 0.0))
        overlap_ratio = self._coerce_float(feature_vector.get("overlap_ratio", 0.0))

        confidence = (
            (self.name_weight * name_similarity)
            + (self.type_weight * type_score)
            + (self.overlap_weight * overlap_ratio)
        )
        return float(np.clip(confidence, 0.0, 1.0))

    def score_with_details(self, feature_vector: Dict[str, float]) -> Dict[str, Any]:
        """Return scoring details for metadata persistence and auditing."""
        models_used: Dict[str, float] = {}

        try:
            lr_prob = self._predict_lr_probability(feature_vector)
            if lr_prob is not None:
                models_used["LR"] = float(lr_prob)
        except Exception as exc:
            logger.warning("LR scoring failed: %s", exc)

        try:
            rf_prob = self._predict_rf_probability(feature_vector)
            if rf_prob is not None:
                models_used[self.rf_model_label] = float(rf_prob)
        except Exception as exc:
            logger.warning("%s scoring failed: %s", self.rf_model_label, exc)

        if "LR" in models_used and self.rf_model_label in models_used:
            weight_sum = self.lr_weight + self.rf_weight
            if weight_sum <= 0:
                lr_w, rf_w = 0.3, 0.7
            else:
                lr_w, rf_w = self.lr_weight / weight_sum, self.rf_weight / weight_sum
            confidence = float(
                np.clip((lr_w * models_used["LR"]) + (rf_w * models_used[self.rf_model_label]), 0.0, 1.0)
            )
            confidence_source = "ensemble"
        elif "LR" in models_used:
            confidence = float(np.clip(models_used["LR"], 0.0, 1.0))
            confidence_source = "ml_single"
        elif self.rf_model_label in models_used:
            confidence = float(np.clip(models_used[self.rf_model_label], 0.0, 1.0))
            confidence_source = "ml_single"
        else:
            # Static confidence is only used when no ML model output is available.
            confidence = self._fallback_score(feature_vector)
            confidence_source = "static"

        decision = self.decision(confidence)
        return {
            "confidence": confidence,
            "decision": decision,
            "models_used": models_used,
            "confidence_source": confidence_source,
        }

    def score(self, feature_vector: Dict[str, float]) -> float:
        """Return confidence score in [0, 1] for a feature vector."""
        return float(self.score_with_details(feature_vector)["confidence"])

    def decision(
        self,
        confidence: float,
        strong_threshold: Optional[float] = None,
        probable_threshold: Optional[float] = None,
    ) -> str:
        """Map confidence score to decision band."""
        strong = float(self.strong_threshold if strong_threshold is None else strong_threshold)
        probable = float(self.probable_threshold if probable_threshold is None else probable_threshold)
        if confidence >= strong:
            return "strong"
        if confidence >= probable:
            return "probable"
        return "weak"

    def save_model(self, path: Optional[str] = None) -> None:
        """Save current LogisticRegression model bundle to disk."""
        target = path or self.model_path
        if not target:
            raise ValueError("No target path provided to save model")
        if not self.has_lr_model:
            raise ValueError("No trained LogisticRegression model is available to save")

        payload = {
            "model_type": "logistic_regression",
            "model": self.model,
            "scaler": self.scaler,
            "feature_order": list(self.feature_order),
            "model_version": self.model_version,
        }
        joblib.dump(payload, target)
        self.model_path = target

    def load_model(self, path: str) -> None:
        """Load a model bundle from disk.

        Supports:
        - Native logistic bundle written by this engine.
        - RelationshipModelTrainer bundles (LR or RF).
        """
        try:
            bundle = self._load_bundle(path)
        except Exception as exc:
            # Keep runtime resilient when pickled models are from a different sklearn version.
            logger.warning(
                "Failed to load ML scoring model from '%s' (%s). Falling back to static scoring.",
                path,
                exc,
            )
            return

        model = bundle
        scaler = None
        feature_order = None
        model_type = None
        version = self.model_version

        if isinstance(bundle, dict):
            model = bundle.get("model")
            scaler = bundle.get("scaler")
            feature_order = (
                bundle.get("feature_order")
                or bundle.get("feature_names")
                or bundle.get("feature_columns")
            )
            model_type = bundle.get("model_type")
            version = bundle.get("model_version", version)

        if isinstance(model, LogisticRegression) or model_type == "logistic_regression":
            if scaler is None or not isinstance(scaler, StandardScaler):
                logger.warning("Loaded LogisticRegression bundle is missing a valid StandardScaler: %s", path)
                return
            self._patch_legacy_logistic_model(model)
            self.model = model
            self.scaler = scaler
            self.feature_order = list(feature_order) if feature_order else list(self.DEFAULT_FEATURE_ORDER)
            self.model_version = version
            self.model_path = path
            return

        if (
            isinstance(model, RandomForestClassifier)
            or isinstance(model, GradientBoostingClassifier)
            or model_type in {"random_forest", "gradient_boosting"}
        ):
            self.rf_model = model
            self.rf_scaler = scaler if isinstance(scaler, StandardScaler) else None
            self.rf_feature_order = list(feature_order) if feature_order else list(self.DEFAULT_FEATURE_ORDER)
            self.rf_model_label = "GB" if isinstance(model, GradientBoostingClassifier) or model_type == "gradient_boosting" else "RF"
            self.model_version = version
            return

        logger.warning(
            "Loaded model is unsupported for ML scoring (type=%s). Keeping static fallback only.",
            type(model).__name__ if model is not None else "None",
        )

    def _load_bundle(self, path: str) -> Any:
        """Load model bundle with compatibility for legacy sklearn internals."""
        try:
            return joblib.load(path)
        except ModuleNotFoundError as exc:
            # Some older GradientBoosting pickles reference removed private module names.
            if "sklearn.ensemble._gb_losses" not in str(exc):
                raise
            self._install_legacy_sklearn_aliases()
            return joblib.load(path)

    @staticmethod
    def _install_legacy_sklearn_aliases() -> None:
        """Install alias shims so older sklearn model pickles can be deserialized."""
        from sklearn.ensemble import _gb

        # Old pickles import this private module path; map to the modern module.
        sys.modules.setdefault("sklearn.ensemble._gb_losses", _gb)

        # Old class name used in previous sklearn releases.
        if not hasattr(_gb, "BinomialDeviance") and hasattr(_gb, "HalfBinomialLoss"):
            _gb.BinomialDeviance = _gb.HalfBinomialLoss

    @staticmethod
    def _patch_legacy_logistic_model(model: LogisticRegression) -> None:
        """Patch missing attributes on cross-version LogisticRegression pickles."""
        if not hasattr(model, "multi_class"):
            model.multi_class = "auto"
        if not hasattr(model, "solver"):
            model.solver = "lbfgs"
