"""
Learned scorer service that trains drift severity models on historical data.
Uses historical drift runs + human labels to learn optimal scoring weights.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from datetime import datetime

try:
    from sklearn.preprocessing import StandardScaler
    from sklearn.ensemble import GradientBoostingClassifier
    import joblib
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

logger = logging.getLogger(__name__)


class LearnedDriftScorer:
    """
    Trains and applies learned drift severity models.
    Replaces manual thresholds with learned weights from historical data.
    """
    
    def __init__(self, model_dir: Path):
        self.model_dir = model_dir
        self.model_dir.mkdir(parents=True, exist_ok=True)
        
        self.model_path = self.model_dir / "drift_severity_model.pkl"
        self.scaler_path = self.model_dir / "scaler.pkl"
        self.training_log_path = self.model_dir / "training_log.json"
        
        self.model = None
        self.scaler = None
        self._load_model()
    
    def extract_features(self, drift_result: Dict[str, Any]) -> np.ndarray:
        """
        Extract feature vector from drift result for scoring.
        Features include:
        - # of statistically significant columns
        - Average p-value (lowest = most significant)
        - # of semantic changes
        - # of new categories
        - Behavioral divergence
        - Missing value changes
        """
        features = []
        
        # Statistical signals
        stat_sigs = drift_result.get('statistical_signals', [])
        num_significant = 0
        p_values = []
        ks_stats = []
        chi2_stats = []
        new_cat_count = 0
        missing_changes = 0
        
        for sig in stat_sigs:
            if sig.get('ks_pvalue', 1.0) < 0.05:
                num_significant += 1
            if sig.get('ks_pvalue') is not None:
                p_values.append(sig['ks_pvalue'])
            if sig.get('ks_statistic') is not None:
                ks_stats.append(sig['ks_statistic'])
            if sig.get('chi2_statistic') is not None:
                chi2_stats.append(sig['chi2_statistic'])
            
            new_cat_count += len(sig.get('new_categories', []))
            
            missing_a = sig.get('missing_rate_baseline', 0.0)
            missing_b = sig.get('missing_rate_current', 0.0)
            if abs(missing_a - missing_b) > 0.01:
                missing_changes += 1
        
        features.append(float(num_significant))
        features.append(float(np.mean(p_values)) if p_values else 1.0)
        features.append(float(np.mean(ks_stats)) if ks_stats else 0.0)
        features.append(float(np.mean(chi2_stats)) if chi2_stats else 0.0)
        features.append(float(new_cat_count))
        features.append(float(missing_changes))
        
        # Semantic signals
        sem_sigs = drift_result.get('semantic_signals', [])
        num_name_changes = sum(1 for s in sem_sigs if s.get('name_changed', False))
        num_unit_changes = sum(1 for s in sem_sigs if s.get('unit_changed', False))
        avg_sem_confidence = np.mean([s.get('confidence', 0.0) for s in sem_sigs]) if sem_sigs else 0.0
        
        features.append(float(num_name_changes))
        features.append(float(num_unit_changes))
        features.append(float(avg_sem_confidence))
        
        # Behavioral signals
        behav_sig = drift_result.get('behavioral_signals')
        if behav_sig:
            features.append(float(abs(behav_sig.get('feature_impact_delta', 0.0))))
            features.append(float(abs(behav_sig.get('ranking_correlation_change', 0.0))))
            features.append(float(behav_sig.get('release_outcome_divergence', 0.0)))
        else:
            features.extend([0.0, 0.0, 0.0])
        
        # Dataset metadata
        is_internal = float(drift_result.get('is_internal_drift', False))
        features.append(is_internal)
        
        return np.array(features, dtype=np.float32)
    
    def train(self, labeled_drift_results: List[Tuple[Dict[str, Any], str]]) -> Dict[str, Any]:
        """
        Train the drift severity model.
        
        Args:
            labeled_drift_results: List of (drift_result_dict, label) tuples
                where label is one of: 'low', 'moderate', 'high'
        
        Returns:
            Training metrics
        """
        if not HAS_SKLEARN:
            logger.warning("scikit-learn not available, skipping model training")
            return {'error': 'scikit-learn not installed'}
        
        if len(labeled_drift_results) < 10:
            logger.warning(f"Not enough training data: {len(labeled_drift_results)} < 10")
            return {'error': f'Insufficient data: {len(labeled_drift_results)} samples'}
        
        # Extract features and labels
        X = []
        y = []
        
        for drift_result, label in labeled_drift_results:
            try:
                features = self.extract_features(drift_result)
                X.append(features)
                # Convert labels to numeric
                label_map = {'low': 0, 'moderate': 1, 'high': 2}
                y.append(label_map.get(label, 1))
            except Exception as e:
                logger.warning(f"Failed to extract features from drift result: {e}")
                continue
        
        if len(X) < 10:
            logger.warning(f"Not enough valid samples: {len(X)} < 10")
            return {'error': f'Insufficient valid samples: {len(X)}'}
        
        X = np.array(X)
        y = np.array(y)
        
        # Fit scaler and model
        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)
        
        self.model = GradientBoostingClassifier(
            n_estimators=100,
            learning_rate=0.1,
            max_depth=5,
            random_state=42,
        )
        self.model.fit(X_scaled, y)
        
        # Save model and scaler
        joblib.dump(self.model, self.model_path)
        joblib.dump(self.scaler, self.scaler_path)
        
        # Calculate and log metrics
        train_accuracy = float(self.model.score(X_scaled, y))
        
        metrics = {
            'timestamp': datetime.utcnow().isoformat(),
            'n_samples': len(X),
            'train_accuracy': train_accuracy,
            'feature_importance': dict(zip(
                range(len(self.model.feature_importances_)),
                self.model.feature_importances_.tolist()
            )),
        }
        
        # Save training log
        log_path = self.training_log_path
        logs = []
        if log_path.exists():
            logs = json.loads(log_path.read_text())
        logs.append(metrics)
        log_path.write_text(json.dumps(logs, indent=2))
        
        logger.info(f"Trained drift scorer with {len(X)} samples, accuracy: {train_accuracy:.3f}")
        return metrics
    
    def predict_severity(self, drift_result: Dict[str, Any]) -> Tuple[str, float]:
        """
        Predict drift severity from a drift result.
        
        Returns:
            (severity_label, confidence_score)
        """
        if self.model is None or self.scaler is None:
            # No model trained, return heuristic score
            return self._heuristic_severity(drift_result)
        
        try:
            features = self.extract_features(drift_result)
            X_scaled = self.scaler.transform(features.reshape(1, -1))
            
            # Get prediction and probability
            pred_class = self.model.predict(X_scaled)[0]
            pred_proba = self.model.predict_proba(X_scaled)[0]
            confidence = float(pred_proba[pred_class])
            
            label_map = {0: 'low', 1: 'moderate', 2: 'high'}
            severity = label_map.get(pred_class, 'moderate')
            
            return severity, confidence
        except Exception as e:
            logger.warning(f"Failed to predict severity: {e}, using heuristic")
            return self._heuristic_severity(drift_result)
    
    def _heuristic_severity(self, drift_result: Dict[str, Any]) -> Tuple[str, float]:
        """
        Heuristic severity scoring when no model is available.
        """
        overall_score = drift_result.get('overall_drift_score', 0.0)
        
        if overall_score >= 0.7:
            return 'high', overall_score
        elif overall_score >= 0.4:
            return 'moderate', overall_score
        else:
            return 'low', overall_score
    
    def _load_model(self) -> None:
        """Load saved model if available."""
        if not HAS_SKLEARN:
            return
        
        if self.model_path.exists() and self.scaler_path.exists():
            try:
                self.model = joblib.load(self.model_path)
                self.scaler = joblib.load(self.scaler_path)
                logger.info("Loaded saved drift severity model")
            except Exception as e:
                logger.warning(f"Failed to load saved model: {e}")
    
    def get_training_stats(self) -> Dict[str, Any]:
        """Get statistics on model training."""
        if not self.training_log_path.exists():
            return {'status': 'no_model_trained'}
        
        logs = json.loads(self.training_log_path.read_text())
        if not logs:
            return {'status': 'empty_log'}
        
        latest = logs[-1]
        return {
            'status': 'model_trained',
            'latest_training': latest,
            'n_trainings': len(logs),
        }
