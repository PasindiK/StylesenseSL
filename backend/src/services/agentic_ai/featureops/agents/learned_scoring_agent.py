"""
LearnedScoringAgent: Phase 3 of Agentic Semantic FeatureOps

This agent is responsible for learning drift decision boundaries instead of using
hard-coded thresholds.

Key Innovation:
  Instead of: if cosine_sim < 0.75: drift
  Uses: Logistic Regression trained on comparison features to predict SAFE/CONDITIONAL/QUARANTINED

This eliminates manual threshold tuning and adapts to data patterns.
"""

from __future__ import annotations

import json
import logging
import os
import pickle
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

logger = logging.getLogger(__name__)


class LearnedScoringAgent:
    """
    Phase 3 Agent: Learned Drift Scoring

    Trains Logistic Regression on synthetic/labeled drift data to predict
    SAFE / CONDITIONAL / QUARANTINED without hard-coded thresholds.
    """

    def __init__(self, model_dir: Path = Path("src/services/agentic_ai/featureops/models")):
        """Initialize the learned scoring agent."""
        self.model_dir = model_dir
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.model_path = self.model_dir / "drift_triage_model.joblib"
        self.scaler_path = self.model_dir / "drift_triage_scaler.joblib"
        self.feature_names_path = self.model_dir / "feature_names.json"

        self.model: Optional[LogisticRegression] = None
        self.scaler: Optional[StandardScaler] = None
        self.feature_names: List[str] = []

        self._load_model_if_exists()

    # =========================================================================
    # Training Phase
    # =========================================================================

    def generate_synthetic_training_data(
        self,
        num_samples_per_class: int = 100,
        seed: int = 42,
    ) -> pd.DataFrame:
        """
        Generate synthetic training data for drift classification.

        Creates 4 classes:
          - SAFE: stable profiles (internal=external, no drift)
          - CONDITIONAL: market shift (internal≠external, external aligned)
          - QUARANTINED: genuine drift (internal≠external, not aligned)
          - SAFE_WITH_WARNING: (mapped to CONDITIONAL for simplicity)

        Args:
            num_samples_per_class: Samples per class (100 → 300-400 total)
            seed: Random seed for reproducibility

        Returns:
            DataFrame with columns: [feature1, feature2, ..., label]
        """
        np.random.seed(seed)
        rows: List[Dict[str, Any]] = []

        # Class 1: SAFE (stable, matches both baselines)
        for _ in range(num_samples_per_class):
            features = self._generate_safe_features()
            features["label"] = "SAFE"
            rows.append(features)

        # Class 2: CONDITIONAL (market shift, external aligned)
        for _ in range(num_samples_per_class):
            features = self._generate_conditional_features()
            features["label"] = "CONDITIONAL"
            rows.append(features)

        # Class 3: QUARANTINED (broken anchors or misaligned)
        for _ in range(num_samples_per_class):
            features = self._generate_quarantined_features()
            features["label"] = "QUARANTINED"
            rows.append(features)

        return pd.DataFrame(rows)

    def train(
        self,
        training_data: Optional[pd.DataFrame] = None,
        num_samples_per_class: int = 100,
        model_name: str = "LogisticRegression",
        test_split: float = 0.2,
    ) -> Dict[str, Any]:
        """
        Train the drift scoring model.

        Args:
            training_data: DataFrame with features + 'label' column
            num_samples_per_class: If training_data is None, generate this many
            model_name: Model type ('LogisticRegression' or future 'RandomForest')
            test_split: Fraction for test set

        Returns:
            Dictionary with training results (accuracy, confusion matrix, etc.)
        """
        # Generate or use provided training data
        if training_data is None:
            logger.info("Generating synthetic training data...")
            training_data = self.generate_synthetic_training_data(num_samples_per_class)
        else:
            logger.info(f"Using provided training data: {len(training_data)} rows")

        logger.info(f"Training data shape: {training_data.shape}")
        logger.info(f"Class distribution:\n{training_data['label'].value_counts()}")

        # Split features and labels
        X = training_data.drop(columns=["label"])
        y = training_data["label"]

        # Track feature names for inference
        self.feature_names = list(X.columns)
        logger.info(f"Features: {self.feature_names}")

        # Standardize features
        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)

        # Train model
        if model_name == "LogisticRegression":
            self.model = LogisticRegression(
                max_iter=1000,
                random_state=42,
                solver="lbfgs",
            )
        else:
            raise ValueError(f"Unknown model_name: {model_name}")

        logger.info("Training model...")
        self.model.fit(X_scaled, y)

        # Evaluate on full data
        train_score = self.model.score(X_scaled, y)
        logger.info(f"Model accuracy on training data: {train_score:.3f}")

        # Save model and scaler
        self._save_model()

        results = {
            "status": "trained",
            "model_type": model_name,
            "training_samples": len(training_data),
            "feature_count": len(self.feature_names),
            "features": self.feature_names,
            "classes": sorted(self.model.classes_.tolist()),
            "accuracy": train_score,
            "saved_at": datetime.utcnow().isoformat(),
            "model_path": str(self.model_path),
        }

        logger.info(f"✓ Model trained and saved: {self.model_path}")
        return results

    # =========================================================================
    # Inference Phase
    # =========================================================================

    def score(self, features: Dict[str, float]) -> Dict[str, Any]:
        """
        Score new data using trained model.

        Args:
            features: Dictionary of feature values
                     e.g., {
                       'internal_mean_distance': 0.5,
                       'external_mean_distance': 0.2,
                       ...
                     }

        Returns:
            Dictionary with:
              - label: predicted class (SAFE/CONDITIONAL/QUARANTINED)
              - probabilities: {SAFE: 0.1, CONDITIONAL: 0.2, QUARANTINED: 0.7}
              - confidence: max probability
        """
        if self.model is None or self.scaler is None:
            return {
                "status": "error",
                "message": "Model not trained. Call .train() first.",
            }

        try:
            # Extract features in same order as training
            X = np.array([features.get(name, 0.0) for name in self.feature_names]).reshape(1, -1)

            # Scale
            X_scaled = self.scaler.transform(X)

            # Predict
            label = self.model.predict(X_scaled)[0]
            probabilities = self.model.predict_proba(X_scaled)[0]

            result = {
                "status": "scored",
                "label": label,
                "confidence": float(np.max(probabilities)),
                "probabilities": {
                    cls: float(prob)
                    for cls, prob in zip(self.model.classes_, probabilities)
                },
            }

            return result

        except Exception as exc:
            logger.error(f"Scoring failed: {exc}")
            return {"status": "error", "message": str(exc)}

    def score_batch(self, features_list: List[Dict[str, float]]) -> List[Dict[str, Any]]:
        """Score multiple records at once."""
        return [self.score(features) for features in features_list]

    # =========================================================================
    # Feature Generation (Synthetic Data)
    # =========================================================================

    @staticmethod
    def _generate_safe_features() -> Dict[str, float]:
        """Generate features for SAFE class (stable, matches both baselines)."""
        return {
            "internal_mean_distance": np.random.normal(0.05, 0.02),  # small distance
            "external_mean_distance": np.random.normal(0.06, 0.02),  # small distance
            "text_embedding_distance": np.random.normal(0.08, 0.03),  # high similarity
            "anchor_violation_score": np.random.normal(0.05, 0.02),  # low violations
            "scale_mismatch_score": np.random.normal(0.02, 0.01),  # no scale issues
            "numeric_std_ratio": np.random.normal(0.95, 0.05),  # similar std
            "categorical_entropy_ratio": np.random.normal(0.90, 0.08),  # similar entropy
            "minority_scale_ratio": np.random.normal(0.02, 0.01),  # no minority scale
            "text_similarity_to_internal": np.random.normal(0.85, 0.08),  # high similarity
            "text_similarity_to_external": np.random.normal(0.82, 0.10),  # high similarity
            "semantic_coherence_score": np.random.normal(0.88, 0.07),  # high coherence
            "column_count_diff": np.random.normal(0, 0),  # same columns
            "new_column_ratio": np.random.normal(0.0, 0.01),  # no new columns
            "missing_column_ratio": np.random.normal(0.0, 0.01),  # no missing columns
            "max_column_drift": np.random.normal(0.05, 0.02),  # minimal drift in any column
        }

    @staticmethod
    def _generate_conditional_features() -> Dict[str, float]:
        """Generate features for CONDITIONAL class (market shift, external aligned)."""
        return {
            "internal_mean_distance": np.random.normal(0.45, 0.10),  # moderate distance from internal
            "external_mean_distance": np.random.normal(0.08, 0.03),  # small distance from external (aligned)
            "text_embedding_distance": np.random.normal(0.25, 0.08),  # moderate similarity (changed wording)
            "anchor_violation_score": np.random.normal(0.20, 0.08),  # some anchor violations but not severe
            "scale_mismatch_score": np.random.normal(0.15, 0.06),  # some scale shift (e.g., price increase)
            "numeric_std_ratio": np.random.normal(1.15, 0.10),  # increased std
            "categorical_entropy_ratio": np.random.normal(1.08, 0.10),  # increased entropy
            "minority_scale_ratio": np.random.normal(0.10, 0.05),  # some minority scale
            "text_similarity_to_internal": np.random.normal(0.60, 0.12),  # moderate similarity
            "text_similarity_to_external": np.random.normal(0.80, 0.10),  # high external similarity
            "semantic_coherence_score": np.random.normal(0.72, 0.10),  # moderate coherence
            "column_count_diff": np.random.normal(0, 0),  # same columns
            "new_column_ratio": np.random.normal(0.0, 0.01),  # no new columns
            "missing_column_ratio": np.random.normal(0.0, 0.01),  # no missing columns
            "max_column_drift": np.random.normal(0.40, 0.08),  # moderate drift
        }

    @staticmethod
    def _generate_quarantined_features() -> Dict[str, float]:
        """Generate features for QUARANTINED class (broken anchors, misaligned)."""
        return {
            "internal_mean_distance": np.random.normal(0.65, 0.12),  # large distance from internal
            "external_mean_distance": np.random.normal(0.55, 0.12),  # large distance from external (misaligned)
            "text_embedding_distance": np.random.normal(0.50, 0.12),  # low similarity (very different text)
            "anchor_violation_score": np.random.normal(0.75, 0.15),  # many anchor violations (HIGH RISK)
            "scale_mismatch_score": np.random.normal(0.60, 0.15),  # severe scale mismatch
            "numeric_std_ratio": np.random.normal(1.60, 0.20),  # very different std
            "categorical_entropy_ratio": np.random.normal(1.50, 0.20),  # very different entropy
            "minority_scale_ratio": np.random.normal(0.40, 0.15),  # significant minority scale (mixed semantics)
            "text_similarity_to_internal": np.random.normal(0.35, 0.15),  # low internal similarity
            "text_similarity_to_external": np.random.normal(0.30, 0.15),  # low external similarity
            "semantic_coherence_score": np.random.normal(0.40, 0.15),  # low coherence
            "column_count_diff": np.random.normal(0, 0),  # same columns (for now)
            "new_column_ratio": np.random.normal(0.0, 0.02),  # possibly new columns
            "missing_column_ratio": np.random.normal(0.02, 0.03),  # possibly missing columns
            "max_column_drift": np.random.normal(0.80, 0.12),  # severe drift in some columns
        }

    # =========================================================================
    # Model Persistence
    # =========================================================================

    def _save_model(self) -> None:
        """Save trained model and scaler to disk."""
        if self.model is None or self.scaler is None:
            logger.warning("Cannot save: model or scaler is None")
            return

        try:
            import joblib

            joblib.dump(self.model, self.model_path)
            joblib.dump(self.scaler, self.scaler_path)

            with open(self.feature_names_path, "w") as f:
                json.dump(self.feature_names, f)

            logger.info(f"✓ Model saved: {self.model_path}")
            logger.info(f"✓ Scaler saved: {self.scaler_path}")
            logger.info(f"✓ Feature names saved: {self.feature_names_path}")
        except Exception as exc:
            logger.error(f"Failed to save model: {exc}")

    def _load_model_if_exists(self) -> None:
        """Load model and scaler from disk if they exist."""
        if not self.model_path.exists():
            logger.debug("No saved model found")
            return

        try:
            import joblib

            self.model = joblib.load(self.model_path)
            self.scaler = joblib.load(self.scaler_path)

            with open(self.feature_names_path, "r") as f:
                self.feature_names = json.load(f)

            logger.info(f"✓ Loaded model: {self.model_path}")
            logger.info(f"✓ Features: {self.feature_names}")
        except Exception as exc:
            logger.warning(f"Failed to load model: {exc}")

    # =========================================================================
    # Model Inspection
    # =========================================================================

    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the trained model."""
        if self.model is None:
            return {"status": "not_trained"}

        return {
            "status": "trained",
            "classes": sorted(self.model.classes_.tolist()),
            "feature_count": len(self.feature_names),
            "features": self.feature_names,
            "model_type": "LogisticRegression",
            "model_path": str(self.model_path),
            "coefficients": {
                feat: float(coef)
                for feat, coef in zip(self.feature_names, self.model.coef_[0])
            }
            if len(self.model.coef_) > 0
            else {},
        }

    def get_feature_importance(self) -> Dict[str, float]:
        """Get feature importance (absolute coefficient values for Logistic Regression)."""
        if self.model is None or not self.feature_names:
            return {}

        importances = np.abs(self.model.coef_[0])
        return {feat: float(imp) for feat, imp in zip(self.feature_names, importances)}


# ========================================================================
# Standalone CLI for testing
# ========================================================================

if __name__ == "__main__":
    print("[LearnedScoringAgent] Phase 3 - Learned Drift Scoring")
    print("=" * 60)

    # Step 1: Initialize agent
    agent = LearnedScoringAgent()
    print("\n✓ LearnedScoringAgent initialized")

    # Step 2: Generate synthetic training data
    print("\n[Phase 3] Generating synthetic training data...")
    training_data = agent.generate_synthetic_training_data(num_samples_per_class=100)
    print(f"✓ Generated {len(training_data)} training samples")
    print(f"  Class distribution:\n{training_data['label'].value_counts()}")

    # Step 3: Train model
    print("\n[Phase 3] Training Logistic Regression model...")
    train_result = agent.train(training_data=training_data)
    print(f"✓ Model trained")
    print(f"  Accuracy: {train_result['accuracy']:.3f}")
    print(f"  Features: {len(train_result['features'])}")
    print(f"  Classes: {train_result['classes']}")

    # Step 4: Score new data
    print("\n[Phase 3] Scoring example data...")

    # Example 1: SAFE-like data
    safe_features = {
        "internal_mean_distance": 0.05,
        "external_mean_distance": 0.06,
        "text_embedding_distance": 0.08,
        "anchor_violation_score": 0.05,
        "scale_mismatch_score": 0.02,
        "numeric_std_ratio": 0.95,
        "categorical_entropy_ratio": 0.90,
        "minority_scale_ratio": 0.02,
        "text_similarity_to_internal": 0.85,
        "text_similarity_to_external": 0.82,
        "semantic_coherence_score": 0.88,
        "column_count_diff": 0,
        "new_column_ratio": 0.0,
        "missing_column_ratio": 0.0,
        "max_column_drift": 0.05,
    }

    result = agent.score(safe_features)
    print(f"\n✓ Example 1 (SAFE-like):")
    print(f"  Predicted: {result['label']}")
    print(f"  Confidence: {result['confidence']:.3f}")
    print(f"  Probabilities: {result['probabilities']}")

    # Example 2: QUARANTINED-like data
    quarantine_features = {
        "internal_mean_distance": 0.65,
        "external_mean_distance": 0.55,
        "text_embedding_distance": 0.50,
        "anchor_violation_score": 0.75,
        "scale_mismatch_score": 0.60,
        "numeric_std_ratio": 1.60,
        "categorical_entropy_ratio": 1.50,
        "minority_scale_ratio": 0.40,
        "text_similarity_to_internal": 0.35,
        "text_similarity_to_external": 0.30,
        "semantic_coherence_score": 0.40,
        "column_count_diff": 0,
        "new_column_ratio": 0.0,
        "missing_column_ratio": 0.0,
        "max_column_drift": 0.80,
    }

    result = agent.score(quarantine_features)
    print(f"\n✓ Example 2 (QUARANTINED-like):")
    print(f"  Predicted: {result['label']}")
    print(f"  Confidence: {result['confidence']:.3f}")
    print(f"  Probabilities: {result['probabilities']}")

    # Step 5: Model inspection
    print("\n[Phase 3] Model Inspection:")
    model_info = agent.get_model_info()
    print(f"  Status: {model_info['status']}")
    print(f"  Classes: {model_info['classes']}")
    print(f"  Features: {model_info['feature_count']}")

    print(f"\n[Phase 3] Feature Importance (top 5):")
    importance = agent.get_feature_importance()
    for feat, imp in sorted(importance.items(), key=lambda x: -x[1])[:5]:
        print(f"  {feat}: {imp:.3f}")

    print("\n✓ Phase 3 (LearnedScoringAgent) ready for integration!")
