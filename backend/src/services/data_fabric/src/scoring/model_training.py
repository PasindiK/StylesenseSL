"""Model training pipeline for relationship inference scoring."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple
import logging
import json

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)


class RelationshipModelTrainer:
    """Train and evaluate supervised relationship inference models."""

    def __init__(self, model_version: str = "v1.0"):
        self.model: Any = None
        self.scaler: StandardScaler | None = None
        self.feature_names: List[str] = []
        self.model_version = model_version
        self.feature_vector_version = "v1.0"
        self.training_date: str | None = None
        self.model_type: str = "logistic_regression"

    def prepare_dataset(
        self,
        feature_vectors: List[Dict[str, float]],
        labels: List[int],
    ) -> Tuple[pd.DataFrame, np.ndarray]:
        """Convert feature vectors and labels into model-ready X/y."""
        if not feature_vectors:
            raise ValueError("feature_vectors cannot be empty")
        if len(feature_vectors) != len(labels):
            raise ValueError("feature_vectors and labels must have same length")

        df = pd.DataFrame(feature_vectors)
        df = df.apply(pd.to_numeric, errors="coerce").fillna(0.0)
        self.feature_names = df.columns.tolist()

        y = np.array(labels, dtype=int)
        return df, y

    def train_model(
        self,
        X: pd.DataFrame,
        y: np.ndarray,
        test_size: float = 0.2,
        model_type: str = "gradient_boosting",
        class_weight: str | None = "balanced",
        positive_oversample_factor: int = 2,
        hyperparameters: Dict[str, Any] | None = None,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Split, scale, and train logistic regression model."""
        hyperparameters = hyperparameters or {}
        self.model_type = model_type

        X_train, X_test, y_train, y_test = train_test_split(
            X,
            y,
            test_size=test_size,
            random_state=42,
            stratify=y if len(np.unique(y)) > 1 else None,
        )

        if positive_oversample_factor > 1:
            X_train, y_train = self._oversample_positives(
                X_train,
                y_train,
                factor=positive_oversample_factor,
            )

        self.scaler = StandardScaler()
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)

        if model_type == "gradient_boosting":
            params = {"n_estimators": 200, "random_state": 42, **hyperparameters}
            self.model = GradientBoostingClassifier(**params)
        elif model_type == "random_forest":
            params = {
                "n_estimators": 200,
                "random_state": 42,
                "class_weight": class_weight,
                **hyperparameters,
            }
            self.model = RandomForestClassifier(**params)
        elif model_type == "logistic_regression":
            params = {
                "max_iter": 1000,
                "class_weight": class_weight,
                "random_state": 42,
                **hyperparameters,
            }
            self.model = LogisticRegression(**params)
        else:
            raise ValueError(f"Unsupported model_type: {model_type}")

        self.model.fit(X_train_scaled, y_train)
        self.training_date = datetime.now().isoformat()

        return X_train_scaled, X_test_scaled, y_train, y_test

    def evaluate_model(
        self,
        X_test: np.ndarray,
        y_test: np.ndarray,
        decision_threshold: float = 0.5,
    ) -> Dict[str, Any]:
        """Evaluate model and return classification metrics."""
        if self.model is None:
            raise ValueError("Model is not trained")

        if not (0.0 < decision_threshold < 1.0):
            raise ValueError("decision_threshold must be between 0 and 1")

        if hasattr(self.model, "predict_proba"):
            y_prob = self.model.predict_proba(X_test)[:, 1]
            y_pred = (y_prob >= decision_threshold).astype(int)
        else:
            y_pred = self.model.predict(X_test)
            y_prob = y_pred.astype(float)

        cm = confusion_matrix(y_test, y_pred)
        metrics: Dict[str, Any] = {
            "accuracy": float(accuracy_score(y_test, y_pred)),
            "precision": float(precision_score(y_test, y_pred, zero_division=0)),
            "recall": float(recall_score(y_test, y_pred, zero_division=0)),
            "f1_score": float(f1_score(y_test, y_pred, zero_division=0)),
            "roc_auc": float(roc_auc_score(y_test, y_prob)) if len(np.unique(y_test)) > 1 else 0.0,
            "confusion_matrix": cm.tolist(),
            "model_type": self.model_type,
            "decision_threshold": float(decision_threshold),
        }

        report = classification_report(y_test, y_pred, zero_division=0)
        logger.info("classification_report\n%s", report)
        metrics["classification_report"] = report
        logger.info("evaluation_metrics=%s", metrics)

        if metrics["accuracy"] < 0.80:
            logger.warning(
                "Accuracy below 0.80. Check feature separability and dataset quality."
            )

        return metrics

    def get_feature_importance(self) -> pd.DataFrame:
        """Return feature importance ranking as DataFrame."""
        if self.model is None:
            raise ValueError("Model is not trained")

        if hasattr(self.model, "feature_importances_"):
            values = self.model.feature_importances_
        elif hasattr(self.model, "coef_"):
            coef = self.model.coef_[0] if getattr(self.model, "coef_", None) is not None else []
            values = np.abs(np.array(coef))
        else:
            values = np.zeros(len(self.feature_names), dtype=float)

        return (
            pd.DataFrame({"feature": self.feature_names, "importance": values})
            .sort_values("importance", ascending=False)
            .reset_index(drop=True)
        )

    def save_feature_importance(self, path: str) -> None:
        """Persist feature importance ranking to CSV."""
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        self.get_feature_importance().to_csv(output, index=False)

    def save_metrics(self, metrics: Dict[str, Any], path: str) -> None:
        """Persist evaluation metrics to JSON."""
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8") as f:
            json.dump(metrics, f, indent=2)

    def save_model(self, path: str) -> None:
        """Persist trained model bundle to disk."""
        if self.model is None or self.scaler is None:
            raise ValueError("Model and scaler must be trained before saving")

        model_path = Path(path)
        model_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "model": self.model,
            "scaler": self.scaler,
            "feature_names": self.feature_names,
            "model_version": self.model_version,
            "feature_vector_version": self.feature_vector_version,
            "training_date": self.training_date,
            "model_type": self.model_type,
        }
        joblib.dump(payload, model_path)

    def load_model(self, path: str) -> None:
        """Load trained model bundle from disk."""
        payload = joblib.load(path)
        self.model = payload["model"]
        self.scaler = payload["scaler"]
        self.feature_names = payload.get("feature_names", [])
        self.model_version = payload.get("model_version", "v1.0")
        self.feature_vector_version = payload.get("feature_vector_version", "v1.0")
        self.training_date = payload.get("training_date")
        self.model_type = payload.get("model_type", "logistic_regression")

    def predict(self, feature_vector: Dict[str, float]) -> float:
        """Predict relationship probability for a single feature vector."""
        if self.model is None or self.scaler is None:
            raise ValueError("Model is not loaded or trained")
        if not self.feature_names:
            raise ValueError("feature_names missing in model bundle")

        df = pd.DataFrame([feature_vector])
        for name in self.feature_names:
            if name not in df.columns:
                df[name] = 0.0
        df = df[self.feature_names].apply(pd.to_numeric, errors="coerce").fillna(0.0)

        X = self.scaler.transform(df)
        if hasattr(self.model, "predict_proba"):
            prob = float(self.model.predict_proba(X)[0][1])
        else:
            prob = float(self.model.predict(X)[0])
        return prob

    @staticmethod
    def _oversample_positives(
        X_train: pd.DataFrame,
        y_train: np.ndarray,
        factor: int,
    ) -> Tuple[pd.DataFrame, np.ndarray]:
        if factor <= 1:
            return X_train, y_train

        train_df = X_train.copy()
        train_df["__target__"] = y_train

        pos_df = train_df[train_df["__target__"] == 1]
        if pos_df.empty:
            return X_train, y_train

        frames = [train_df]
        for _ in range(factor - 1):
            frames.append(pos_df.copy())

        balanced = pd.concat(frames, axis=0, ignore_index=True)
        balanced = balanced.sample(frac=1.0, random_state=42).reset_index(drop=True)

        y_balanced = balanced["__target__"].to_numpy(dtype=int)
        X_balanced = balanced.drop(columns=["__target__"])
        return X_balanced, y_balanced
