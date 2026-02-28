"""Model prediction and serving."""

from dataclasses import dataclass
from typing import Any, List, Dict, Optional
import logging
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class PredictionResult:
    """Result of a prediction."""

    predictions: np.ndarray
    probabilities: Optional[np.ndarray] = None
    confidence: Optional[np.ndarray] = None
    feature_importance: Optional[Dict[str, float]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "predictions": self.predictions.tolist() if isinstance(self.predictions, np.ndarray) else self.predictions,
            "probabilities": self.probabilities.tolist() if self.probabilities is not None else None,
            "confidence": self.confidence.tolist() if self.confidence is not None else None,
            "feature_importance": self.feature_importance,
        }


class ModelPredictor:
    """Predictor for ML models."""

    def __init__(self, model):
        """Initialize predictor.

        Args:
            model: Trained ML model
        """
        self.model = model

    def predict(self, X: pd.DataFrame) -> PredictionResult:
        """Make predictions.

        Args:
            X: Input features

        Returns:
            PredictionResult
        """
        try:
            predictions = self.model.predict(X)

            # Try to get probabilities if available
            probabilities = None
            confidence = None
            if hasattr(self.model, "predict_proba"):
                probabilities = self.model.predict_proba(X)
                confidence = np.max(probabilities, axis=1)

            logger.info(f"Made predictions for {len(X)} samples")

            return PredictionResult(
                predictions=predictions,
                probabilities=probabilities,
                confidence=confidence,
            )
        except Exception as e:
            logger.error(f"Prediction failed: {e}")
            raise

    def batch_predict(
        self, X: pd.DataFrame, batch_size: int = 100
    ) -> List[PredictionResult]:
        """Make batch predictions.

        Args:
            X: Input features
            batch_size: Batch size

        Returns:
            List of PredictionResult
        """
        results = []
        for i in range(0, len(X), batch_size):
            batch = X.iloc[i : i + batch_size]
            result = self.predict(batch)
            results.append(result)

        logger.info(f"Completed batch prediction with {len(results)} batches")
        return results

    def predict_single(self, X: pd.DataFrame) -> Dict[str, Any]:
        """Predict for a single sample.

        Args:
            X: Single sample as DataFrame

        Returns:
            Prediction dictionary
        """
        result = self.predict(X)
        return {
            "prediction": result.predictions[0],
            "probability": result.probabilities[0] if result.probabilities is not None else None,
            "confidence": result.confidence[0] if result.confidence is not None else None,
        }

    def explain_prediction(self, X: pd.DataFrame) -> Dict[str, Any]:
        """Explain predictions (SHAP-like capability).

        Args:
            X: Input features

        Returns:
            Explanation dictionary
        """
        explanation = {
            "feature_names": X.columns.tolist(),
            "feature_values": X.iloc[0].tolist() if len(X) > 0 else [],
        }

        # Try to get feature importances if available
        if hasattr(self.model, "feature_importances_"):
            explanation["feature_importance"] = {
                name: float(importance)
                for name, importance in zip(X.columns, self.model.feature_importances_)
            }

        logger.info("Generated prediction explanation")
        return explanation


class PredictionCache:
    """Cache predictions to avoid redundant computation."""

    def __init__(self, max_size: int = 1000):
        """Initialize prediction cache.

        Args:
            max_size: Maximum cache size
        """
        self.cache: Dict[str, PredictionResult] = {}
        self.max_size = max_size

    def get(self, key: str) -> Optional[PredictionResult]:
        """Get cached prediction.

        Args:
            key: Cache key

        Returns:
            PredictionResult or None
        """
        return self.cache.get(key)

    def put(self, key: str, result: PredictionResult) -> None:
        """Cache a prediction.

        Args:
            key: Cache key
            result: PredictionResult to cache
        """
        if len(self.cache) >= self.max_size:
            # Remove oldest entry
            self.cache.pop(next(iter(self.cache)))

        self.cache[key] = result
        logger.debug(f"Cached prediction: {key}")

    def clear(self) -> None:
        """Clear the cache."""
        self.cache.clear()
        logger.info("Cleared prediction cache")

    def get_size(self) -> int:
        """Get cache size."""
        return len(self.cache)
