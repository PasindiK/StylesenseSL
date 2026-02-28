"""ML Model definitions and registry."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional, List
from datetime import datetime
import logging
import pickle

logger = logging.getLogger(__name__)


@dataclass
class ModelMetadata:
    """Metadata for an ML model."""

    model_name: str
    model_version: str
    model_type: str  # regression, classification, clustering, etc.
    description: str
    train_date: datetime
    accuracy: float
    precision: Optional[float] = None
    recall: Optional[float] = None
    f1_score: Optional[float] = None
    hyperparameters: Dict[str, Any] = None
    feature_importance: Optional[Dict[str, float]] = None
    training_samples: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "model_name": self.model_name,
            "model_version": self.model_version,
            "model_type": self.model_type,
            "description": self.description,
            "train_date": self.train_date.isoformat(),
            "accuracy": self.accuracy,
            "precision": self.precision,
            "recall": self.recall,
            "f1_score": self.f1_score,
            "hyperparameters": self.hyperparameters or {},
            "training_samples": self.training_samples,
        }


class MLModel(ABC):
    """Abstract base class for ML models."""

    def __init__(self, metadata: ModelMetadata):
        """Initialize ML model.

        Args:
            metadata: Model metadata
        """
        self.metadata = metadata
        self.model = None

    @abstractmethod
    def train(self, X, y, **kwargs):
        """Train the model."""
        pass

    @abstractmethod
    def predict(self, X):
        """Make predictions."""
        pass

    @abstractmethod
    def evaluate(self, X, y):
        """Evaluate model performance."""
        pass

    def save(self, filepath: str) -> bool:
        """Save model to disk.

        Args:
            filepath: Path to save model

        Returns:
            True if successful
        """
        try:
            with open(filepath, "wb") as f:
                pickle.dump(self.model, f)
            logger.info(f"Saved model to {filepath}")
            return True
        except Exception as e:
            logger.error(f"Failed to save model: {e}")
            return False

    @classmethod
    def load(cls, filepath: str, metadata: ModelMetadata) -> "MLModel":
        """Load model from disk.

        Args:
            filepath: Path to model file
            metadata: Model metadata

        Returns:
            Loaded MLModel
        """
        try:
            with open(filepath, "rb") as f:
                model = pickle.load(f)
            instance = cls(metadata)
            instance.model = model
            logger.info(f"Loaded model from {filepath}")
            return instance
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise


class SklearnModel(MLModel):
    """Wrapper for scikit-learn models."""

    def __init__(self, metadata: ModelMetadata, sklearn_model=None):
        """Initialize scikit-learn model.

        Args:
            metadata: Model metadata
            sklearn_model: scikit-learn model instance
        """
        super().__init__(metadata)
        self.model = sklearn_model

    def train(self, X, y, **kwargs):
        """Train the sklearn model."""
        try:
            self.model.fit(X, y, **kwargs)
            logger.info(f"Trained {self.metadata.model_type} model")
        except Exception as e:
            logger.error(f"Failed to train model: {e}")
            raise

    def predict(self, X):
        """Make predictions."""
        return self.model.predict(X)

    def evaluate(self, X, y):
        """Evaluate model performance."""
        score = self.model.score(X, y)
        logger.info(f"Model score: {score:.4f}")
        return {"score": score}


class TensorflowModel(MLModel):
    """Wrapper for TensorFlow models."""

    def __init__(self, metadata: ModelMetadata, tf_model=None):
        """Initialize TensorFlow model.

        Args:
            metadata: Model metadata
            tf_model: TensorFlow model instance
        """
        super().__init__(metadata)
        self.model = tf_model

    def train(self, X, y, epochs=10, batch_size=32, **kwargs):
        """Train the TensorFlow model."""
        try:
            self.model.fit(X, y, epochs=epochs, batch_size=batch_size, **kwargs)
            logger.info(f"Trained TensorFlow {self.metadata.model_type} model")
        except Exception as e:
            logger.error(f"Failed to train TensorFlow model: {e}")
            raise

    def predict(self, X):
        """Make predictions."""
        return self.model.predict(X)

    def evaluate(self, X, y):
        """Evaluate model performance."""
        loss, accuracy = self.model.evaluate(X, y)
        logger.info(f"Model loss: {loss:.4f}, accuracy: {accuracy:.4f}")
        return {"loss": loss, "accuracy": accuracy}


class ModelRegistry:
    """Registry for managing ML models."""

    def __init__(self):
        """Initialize model registry."""
        self.models: Dict[str, MLModel] = {}
        self.model_history: Dict[str, List[MLModel]] = {}

    def register_model(self, model_id: str, model: MLModel) -> bool:
        """Register a model.

        Args:
            model_id: Unique model ID
            model: MLModel instance

        Returns:
            True if successful
        """
        if model_id not in self.model_history:
            self.model_history[model_id] = []

        self.models[model_id] = model
        self.model_history[model_id].append(model)

        logger.info(f"Registered model: {model_id} v{model.metadata.model_version}")
        return True

    def get_model(self, model_id: str) -> Optional[MLModel]:
        """Get latest model version.

        Args:
            model_id: Model ID

        Returns:
            MLModel or None
        """
        return self.models.get(model_id)

    def get_model_version(self, model_id: str, version: str) -> Optional[MLModel]:
        """Get specific model version.

        Args:
            model_id: Model ID
            version: Model version

        Returns:
            MLModel or None
        """
        if model_id not in self.model_history:
            return None

        for model in self.model_history[model_id]:
            if model.metadata.model_version == version:
                return model

        return None

    def get_model_history(self, model_id: str) -> List[MLModel]:
        """Get model version history.

        Args:
            model_id: Model ID

        Returns:
            List of models
        """
        return self.model_history.get(model_id, [])

    def list_models(self) -> Dict[str, ModelMetadata]:
        """List all registered models.

        Returns:
            Dictionary mapping model IDs to metadata
        """
        return {model_id: model.metadata for model_id, model in self.models.items()}
