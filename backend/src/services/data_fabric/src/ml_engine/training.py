"""Model training module."""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple
import logging
from abc import ABC, abstractmethod
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class TrainingConfig:
    """Configuration for model training."""

    model_type: str
    train_size: float = 0.8
    test_size: float = 0.2
    random_state: int = 42
    hyperparameters: Dict[str, Any] = field(default_factory=dict)
    cross_validation_folds: int = 5
    scale_features: bool = True
    handle_imbalance: bool = False


class ModelTrainer(ABC):
    """Abstract base class for model trainers."""

    def __init__(self, config: TrainingConfig):
        """Initialize trainer.

        Args:
            config: Training configuration
        """
        self.config = config
        self.model = None
        self.training_history = {}

    @abstractmethod
    def prepare_data(
        self, X: pd.DataFrame, y: pd.Series
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Prepare data for training.

        Args:
            X: Features
            y: Target variable

        Returns:
            Tuple of (X_train, X_test, y_train, y_test)
        """
        pass

    @abstractmethod
    def build_model(self):
        """Build the model."""
        pass

    @abstractmethod
    def train(self, X_train: np.ndarray, y_train: np.ndarray) -> Dict[str, Any]:
        """Train the model.

        Args:
            X_train: Training features
            y_train: Training target

        Returns:
            Training results
        """
        pass

    @abstractmethod
    def evaluate(
        self, X_test: np.ndarray, y_test: np.ndarray
    ) -> Dict[str, Any]:
        """Evaluate the model.

        Args:
            X_test: Test features
            y_test: Test target

        Returns:
            Evaluation metrics
        """
        pass

    def train_and_evaluate(
        self, X: pd.DataFrame, y: pd.Series
    ) -> Dict[str, Any]:
        """Train and evaluate model.

        Args:
            X: Features
            y: Target variable

        Returns:
            Complete training results
        """
        logger.info(f"Starting training for {self.config.model_type}")

        # Prepare data
        X_train, X_test, y_train, y_test = self.prepare_data(X, y)

        # Build model
        self.build_model()

        # Train
        train_results = self.train(X_train, y_train)

        # Evaluate
        eval_results = self.evaluate(X_test, y_test)

        results = {
            "model_type": self.config.model_type,
            "training_results": train_results,
            "evaluation_results": eval_results,
            "train_size": len(X_train),
            "test_size": len(X_test),
        }

        logger.info(f"Training completed for {self.config.model_type}")
        return results


class SklearnTrainer(ModelTrainer):
    """Trainer for scikit-learn models."""

    def prepare_data(
        self, X: pd.DataFrame, y: pd.Series
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Prepare data for training."""
        from sklearn.model_selection import train_test_split
        from sklearn.preprocessing import StandardScaler

        X_train, X_test, y_train, y_test = train_test_split(
            X,
            y,
            train_size=self.config.train_size,
            random_state=self.config.random_state,
        )

        if self.config.scale_features:
            scaler = StandardScaler()
            X_train = scaler.fit_transform(X_train)
            X_test = scaler.transform(X_test)

        logger.info(f"Prepared data: {X_train.shape[0]} train, {X_test.shape[0]} test")
        return X_train, X_test, y_train, y_test

    def build_model(self):
        """Build scikit-learn model."""
        from sklearn.linear_model import LogisticRegression
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.svm import SVC

        model_mapping = {
            "logistic_regression": LogisticRegression,
            "random_forest": RandomForestClassifier,
            "svm": SVC,
        }

        ModelClass = model_mapping.get(self.config.model_type, LogisticRegression)
        self.model = ModelClass(**self.config.hyperparameters)
        logger.info(f"Built model: {self.config.model_type}")

    def train(self, X_train: np.ndarray, y_train: np.ndarray) -> Dict[str, Any]:
        """Train the model."""
        self.model.fit(X_train, y_train)
        train_score = self.model.score(X_train, y_train)

        logger.info(f"Training score: {train_score:.4f}")
        return {"train_score": train_score}

    def evaluate(self, X_test: np.ndarray, y_test: np.ndarray) -> Dict[str, Any]:
        """Evaluate the model."""
        from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

        predictions = self.model.predict(X_test)

        metrics = {
            "accuracy": accuracy_score(y_test, predictions),
            "precision": precision_score(y_test, predictions, average="weighted", zero_division=0),
            "recall": recall_score(y_test, predictions, average="weighted", zero_division=0),
            "f1": f1_score(y_test, predictions, average="weighted", zero_division=0),
        }

        logger.info(f"Evaluation metrics: {metrics}")
        return metrics


class HyperparameterTuner:
    """Tune hyperparameters using grid search."""

    def __init__(self, trainer: SklearnTrainer):
        """Initialize tuner.

        Args:
            trainer: Model trainer instance
        """
        self.trainer = trainer

    def grid_search(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        param_grid: Dict[str, list],
    ) -> Dict[str, Any]:
        """Perform grid search for hyperparameters.

        Args:
            X: Features
            y: Target variable
            param_grid: Parameter grid for search

        Returns:
            Best parameters and score
        """
        from sklearn.model_selection import GridSearchCV

        X_train, X_test, y_train, y_test = self.trainer.prepare_data(X, y)
        self.trainer.build_model()

        grid_search = GridSearchCV(
            self.trainer.model,
            param_grid,
            cv=self.trainer.config.cross_validation_folds,
        )

        grid_search.fit(X_train, y_train)

        logger.info(f"Best parameters: {grid_search.best_params_}")
        logger.info(f"Best CV score: {grid_search.best_score_:.4f}")

        return {
            "best_params": grid_search.best_params_,
            "best_score": grid_search.best_score_,
            "best_model": grid_search.best_estimator_,
        }
