"""
Comprehensive drift detection service with statistical tests and learned scoring.
Detects: internal drift, external drift, statistical drift, semantic drift, behavioral drift.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
import hashlib
import numpy as np
import pandas as pd
from scipy import stats
from collections import Counter

logger = logging.getLogger(__name__)


@dataclass
class StatisticalDriftSignals:
    """Statistical drift signals for a single feature or column."""
    column_name: str
    dtype: str  # 'numeric' or 'categorical'
    
    # For numeric columns
    ks_statistic: Optional[float] = None  # Kolmogorov-Smirnov test statistic
    ks_pvalue: Optional[float] = None
    mean_delta: Optional[float] = None
    std_delta: Optional[float] = None
    
    # For categorical columns
    chi2_statistic: Optional[float] = None
    chi2_pvalue: Optional[float] = None
    new_categories: List[str] = None
    missing_categories: List[str] = None
    
    # Missingness
    missing_rate_baseline: Optional[float] = None
    missing_rate_current: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data.pop('column_name', None)
        data.pop('dtype', None)
        return data


@dataclass
class SemanticDriftSignals:
    """Semantic drift signals for schema/meaning changes."""
    column_name: str
    name_changed: bool = False
    meaning_changed: bool = False  # Detected via LLM or heuristic
    unit_changed: bool = False  # e.g., Celsius -> Fahrenheit
    label_mapping_changed: bool = False
    old_meaning: Optional[str] = None
    new_meaning: Optional[str] = None
    confidence: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BehavioralDriftSignals:
    """Behavioral drift signals for downstream effect changes."""
    feature_impact_delta: float  # Change in feature importance
    ranking_correlation_change: float  # How much rankings changed
    release_outcome_divergence: float  # How often release decisions diverged
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ComprehensiveDriftResult:
    """Full drift detection result across all types."""
    drift_run_id: str
    timestamp: str
    dataset_version_a: str
    dataset_version_b: Optional[str]  # None if internal drift
    is_internal_drift: bool
    
    # Drift type results
    statistical_signals: List[StatisticalDriftSignals]
    semantic_signals: List[SemanticDriftSignals]
    behavioral_signals: Optional[BehavioralDriftSignals]
    
    # Learned scores (from trained model)
    statistical_drift_score: float  # 0-1
    semantic_drift_score: float  # 0-1
    behavioral_drift_score: float  # 0-1
    internal_drift_score: float  # 0-1
    external_drift_score: float  # 0-1
    
    # Overall
    overall_drift_score: float  # 0-1 (weighted combination)
    severity: str  # 'low', 'moderate', 'high'
    drift_detected: bool
    reasons: List[str]
    
    # Optional human review
    human_reviewed: bool = False
    human_label: Optional[str] = None  # For training data
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'drift_run_id': self.drift_run_id,
            'timestamp': self.timestamp,
            'dataset_version_a': self.dataset_version_a,
            'dataset_version_b': self.dataset_version_b,
            'is_internal_drift': self.is_internal_drift,
            'statistical_signals': [s.to_dict() for s in self.statistical_signals],
            'semantic_signals': [s.to_dict() for s in self.semantic_signals],
            'behavioral_signals': self.behavioral_signals.to_dict() if self.behavioral_signals else None,
            'statistical_drift_score': self.statistical_drift_score,
            'semantic_drift_score': self.semantic_drift_score,
            'behavioral_drift_score': self.behavioral_drift_score,
            'internal_drift_score': self.internal_drift_score,
            'external_drift_score': self.external_drift_score,
            'overall_drift_score': self.overall_drift_score,
            'severity': self.severity,
            'drift_detected': self.drift_detected,
            'reasons': self.reasons,
            'human_reviewed': self.human_reviewed,
            'human_label': self.human_label,
        }


class ComprehensiveDriftDetector:
    """Main drift detection service."""
    
    def __init__(self, state_dir: Path):
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.results_dir = self.state_dir / "drift_results"
        self.results_dir.mkdir(parents=True, exist_ok=True)
    
    def detect_internal_drift(
        self,
        data: pd.DataFrame,
        dataset_name: str,
    ) -> ComprehensiveDriftResult:
        """
        Detect drift within a single dataset by comparing early vs. late rows.
        """
        run_id = self._generate_run_id()
        
        # Split data into two halves
        split_point = len(data) // 2
        early_data = data.iloc[:split_point]
        late_data = data.iloc[split_point:]
        
        # Detect statistical drift
        statistical_signals = self._detect_statistical_drift_pairwise(early_data, late_data)
        
        # Semantic drift is less relevant for internal drift
        semantic_signals = []
        
        # Behavioral drift: not directly applicable here without outcomes
        behavioral_signals = None
        
        # Apply learned scorer
        scores = self._apply_learned_scorer(
            statistical_signals=statistical_signals,
            semantic_signals=semantic_signals,
            behavioral_signals=behavioral_signals,
            is_internal=True,
            is_external=False,
        )
        
        # Determine severity and detectability
        severity, drift_detected, reasons = self._determine_severity_and_reasons(
            statistical_signals, semantic_signals, behavioral_signals, scores, is_internal=True
        )
        
        result = ComprehensiveDriftResult(
            drift_run_id=run_id,
            timestamp=datetime.utcnow().isoformat(),
            dataset_version_a=f"{dataset_name}_early",
            dataset_version_b=f"{dataset_name}_late",
            is_internal_drift=True,
            statistical_signals=statistical_signals,
            semantic_signals=semantic_signals,
            behavioral_signals=behavioral_signals,
            statistical_drift_score=scores['statistical'],
            semantic_drift_score=scores['semantic'],
            behavioral_drift_score=scores['behavioral'],
            internal_drift_score=scores['internal'],
            external_drift_score=0.0,
            overall_drift_score=scores['overall'],
            severity=severity,
            drift_detected=drift_detected,
            reasons=reasons,
        )
        
        # Save result
        self._save_result(result)
        return result
    
    def detect_external_drift(
        self,
        data_baseline: pd.DataFrame,
        data_current: pd.DataFrame,
        dataset_name: str,
        baseline_version: str,
        current_version: str,
        schema_info: Optional[Dict[str, Any]] = None,
    ) -> ComprehensiveDriftResult:
        """
        Detect drift between two versions of a dataset.
        """
        run_id = self._generate_run_id()
        
        # Detect statistical drift
        statistical_signals = self._detect_statistical_drift_pairwise(data_baseline, data_current)
        
        # Detect semantic drift (schema changes, meaning changes)
        semantic_signals = self._detect_semantic_drift(
            data_baseline, data_current, schema_info
        )
        
        # Behavioral drift: placeholder (would compare ranking outcomes)
        behavioral_signals = None
        
        # Apply learned scorer
        scores = self._apply_learned_scorer(
            statistical_signals=statistical_signals,
            semantic_signals=semantic_signals,
            behavioral_signals=behavioral_signals,
            is_internal=False,
            is_external=True,
        )
        
        # Determine severity
        severity, drift_detected, reasons = self._determine_severity_and_reasons(
            statistical_signals, semantic_signals, behavioral_signals, scores, is_internal=False
        )
        
        result = ComprehensiveDriftResult(
            drift_run_id=run_id,
            timestamp=datetime.utcnow().isoformat(),
            dataset_version_a=f"{dataset_name}:{baseline_version}",
            dataset_version_b=f"{dataset_name}:{current_version}",
            is_internal_drift=False,
            statistical_signals=statistical_signals,
            semantic_signals=semantic_signals,
            behavioral_signals=behavioral_signals,
            statistical_drift_score=scores['statistical'],
            semantic_drift_score=scores['semantic'],
            behavioral_drift_score=scores['behavioral'],
            internal_drift_score=0.0,
            external_drift_score=scores['external'],
            overall_drift_score=scores['overall'],
            severity=severity,
            drift_detected=drift_detected,
            reasons=reasons,
        )
        
        # Save result
        self._save_result(result)
        return result
    
    def _detect_statistical_drift_pairwise(
        self,
        data_a: pd.DataFrame,
        data_b: pd.DataFrame,
        alpha: float = 0.05,
    ) -> List[StatisticalDriftSignals]:
        """
        Detect statistical drift by comparing distributions of columns.
        Uses KS test for numeric, chi-square for categorical.
        """
        signals = []
        
        for col in data_a.columns:
            if col not in data_b.columns:
                continue
            
            col_a = data_a[col].dropna()
            col_b = data_b[col].dropna()
            
            if len(col_a) == 0 or len(col_b) == 0:
                continue
            
            # Detect dtype
            if pd.api.types.is_numeric_dtype(col_a):
                signal = self._detect_numeric_drift(col, col_a, col_b, alpha)
            else:
                signal = self._detect_categorical_drift(col, col_a, col_b, alpha)
            
            # Detect missingness change
            missing_a = 1.0 - (len(col_a) / len(data_a))
            missing_b = 1.0 - (len(col_b) / len(data_b))
            signal.missing_rate_baseline = missing_a
            signal.missing_rate_current = missing_b
            
            signals.append(signal)
        
        return signals
    
    def _detect_numeric_drift(
        self,
        col_name: str,
        col_a: pd.Series,
        col_b: pd.Series,
        alpha: float = 0.05,
    ) -> StatisticalDriftSignals:
        """Detect drift in numeric column using KS test."""
        ks_stat, ks_pval = stats.ks_2samp(col_a, col_b)
        mean_delta = abs(col_b.mean() - col_a.mean())
        std_delta = abs(col_b.std() - col_a.std())
        
        # Handle inf and nan values (convert to None for JSON serialization)
        ks_stat_val = None if (np.isnan(ks_stat) or np.isinf(ks_stat)) else float(ks_stat)
        ks_pval_val = None if (np.isnan(ks_pval) or np.isinf(ks_pval)) else float(ks_pval)
        mean_delta_val = None if (np.isnan(mean_delta) or np.isinf(mean_delta)) else float(mean_delta)
        std_delta_val = None if (np.isnan(std_delta) or np.isinf(std_delta)) else float(std_delta)
        
        return StatisticalDriftSignals(
            column_name=col_name,
            dtype='numeric',
            ks_statistic=ks_stat_val,
            ks_pvalue=ks_pval_val,
            mean_delta=mean_delta_val,
            std_delta=std_delta_val,
        )
    
    def _detect_categorical_drift(
        self,
        col_name: str,
        col_a: pd.Series,
        col_b: pd.Series,
        alpha: float = 0.05,
    ) -> StatisticalDriftSignals:
        """Detect drift in categorical column using chi-square test."""
        # Get categories
        cat_a = Counter(col_a)
        cat_b = Counter(col_b)
        
        # All categories
        all_cats = set(cat_a.keys()) | set(cat_b.keys())
        
        # Build contingency table
        obs_a = [cat_a.get(cat, 0) for cat in all_cats]
        obs_b = [cat_b.get(cat, 0) for cat in all_cats]
        
        # Chi-square test
        chi2, chi2_pval = stats.chisquare(obs_b, obs_a) if sum(obs_a) > 0 else (np.nan, 1.0)
        
        # Handle inf and nan values (convert to None for JSON serialization)
        if np.isnan(chi2) or np.isinf(chi2):
            chi2_stat = None
        else:
            chi2_stat = float(chi2)
        
        if np.isnan(chi2_pval) or np.isinf(chi2_pval):
            chi2_p = 1.0
        else:
            chi2_p = float(chi2_pval)
        
        # New and missing categories
        new_cats = list(set(cat_b.keys()) - set(cat_a.keys()))
        missing_cats = list(set(cat_a.keys()) - set(cat_b.keys()))
        
        return StatisticalDriftSignals(
            column_name=col_name,
            dtype='categorical',
            chi2_statistic=chi2_stat,
            chi2_pvalue=chi2_p,
            new_categories=new_cats,
            missing_categories=missing_cats,
        )
    
    def _detect_semantic_drift(
        self,
        data_baseline: pd.DataFrame,
        data_current: pd.DataFrame,
        schema_info: Optional[Dict[str, Any]] = None,
    ) -> List[SemanticDriftSignals]:
        """
        Detect semantic drift: column name/order/meaning changes.
        """
        signals = []
        
        # Check column name/order changes
        cols_baseline = set(data_baseline.columns)
        cols_current = set(data_current.columns)
        
        new_cols = cols_current - cols_baseline
        removed_cols = cols_baseline - cols_current
        
        for col in removed_cols:
            signals.append(SemanticDriftSignals(
                column_name=col,
                name_changed=True,
                confidence=0.9,
            ))
        
        for col in new_cols:
            signals.append(SemanticDriftSignals(
                column_name=col,
                name_changed=True,
                confidence=0.9,
            ))
        
        # Check for potential unit/meaning changes in common columns
        if schema_info:
            for col in cols_baseline & cols_current:
                old_info = schema_info.get('baseline', {}).get(col, {})
                new_info = schema_info.get('current', {}).get(col, {})
                
                if old_info.get('unit') != new_info.get('unit'):
                    signals.append(SemanticDriftSignals(
                        column_name=col,
                        unit_changed=True,
                        old_meaning=old_info.get('unit'),
                        new_meaning=new_info.get('unit'),
                        confidence=0.85,
                    ))
        
        return signals
    
    def _apply_learned_scorer(
        self,
        statistical_signals: List[StatisticalDriftSignals],
        semantic_signals: List[SemanticDriftSignals],
        behavioral_signals: Optional[BehavioralDriftSignals],
        is_internal: bool,
        is_external: bool,
    ) -> Dict[str, float]:
        """
        Apply learned scorer to generate drift scores.
        For now, uses heuristic scoring; will be replaced with trained model.
        """
        # Calculate feature vectors from signals
        statistical_score = self._score_statistical_signals(statistical_signals)
        semantic_score = self._score_semantic_signals(semantic_signals)
        behavioral_score = self._score_behavioral_signals(behavioral_signals)
        
        internal_score = statistical_score if is_internal else 0.0
        external_score = (statistical_score + semantic_score) / 2.0 if is_external else 0.0
        
        # Weighted combination (these weights will come from trained model)
        if is_internal:
            overall_score = internal_score
        else:
            overall_score = (
                statistical_score * 0.4 +
                semantic_score * 0.3 +
                behavioral_score * 0.3
            )
        
        return {
            'statistical': statistical_score,
            'semantic': semantic_score,
            'behavioral': behavioral_score,
            'internal': internal_score,
            'external': external_score,
            'overall': overall_score,
        }
    
    def _score_statistical_signals(self, signals: List[StatisticalDriftSignals]) -> float:
        """Score statistical drift from signals."""
        if not signals:
            return 0.0
        
        p_values = []
        effect_sizes = []
        
        for sig in signals:
            if sig.dtype == 'numeric':
                if sig.ks_pvalue is not None:
                    p_values.append(sig.ks_pvalue)
                    effect_sizes.append(min(1.0, sig.ks_statistic or 0.0))
            elif sig.dtype == 'categorical':
                if sig.chi2_pvalue is not None:
                    p_values.append(sig.chi2_pvalue)
                    effect_sizes.append(min(1.0, sig.chi2_statistic / 50.0 if sig.chi2_statistic else 0.0))
        
        if not p_values:
            return 0.0
        
        # Bonferroni correction
        alpha = 0.05 / len(p_values)
        significant_tests = sum(1 for p in p_values if p < alpha)
        
        # Score based on significant tests and effect sizes
        proportion_significant = significant_tests / len(p_values)
        avg_effect_size = np.mean(effect_sizes)
        
        score = (proportion_significant * 0.6 + avg_effect_size * 0.4)
        return float(min(1.0, score))
    
    def _score_semantic_signals(self, signals: List[SemanticDriftSignals]) -> float:
        """Score semantic drift from signals."""
        if not signals:
            return 0.0
        
        weighted_score = 0.0
        max_confidence = 0.0
        
        for sig in signals:
            if sig.name_changed or sig.unit_changed or sig.meaning_changed:
                weighted_score += sig.confidence
                max_confidence += 1.0
        
        if max_confidence == 0.0:
            return 0.0
        
        return float(min(1.0, weighted_score / max_confidence))
    
    def _score_behavioral_signals(self, signals: Optional[BehavioralDriftSignals]) -> float:
        """Score behavioral drift from signals."""
        if signals is None:
            return 0.0
        
        score = (
            min(1.0, abs(signals.feature_impact_delta)) * 0.4 +
            min(1.0, abs(signals.ranking_correlation_change)) * 0.3 +
            min(1.0, signals.release_outcome_divergence) * 0.3
        )
        return float(score)
    
    def _determine_severity_and_reasons(
        self,
        statistical_signals: List[StatisticalDriftSignals],
        semantic_signals: List[SemanticDriftSignals],
        behavioral_signals: Optional[BehavioralDriftSignals],
        scores: Dict[str, float],
        is_internal: bool,
    ) -> Tuple[str, bool, List[str]]:
        """Determine severity level and generate reasons."""
        overall_score = scores['overall']
        reasons = []
        
        # Add reasons based on signals
        for sig in statistical_signals:
            if sig.dtype == 'numeric' and sig.ks_pvalue and sig.ks_pvalue < 0.05:
                reasons.append(f"Column '{sig.column_name}' shows significant distribution shift (p={sig.ks_pvalue:.4f})")
            elif sig.dtype == 'categorical' and sig.chi2_pvalue and sig.chi2_pvalue < 0.05:
                reasons.append(f"Column '{sig.column_name}' shows category frequency change (p={sig.chi2_pvalue:.4f})")
            
            if sig.new_categories:
                reasons.append(f"Column '{sig.column_name}' has new categories: {sig.new_categories}")
            if sig.missing_categories:
                reasons.append(f"Column '{sig.column_name}' missing categories: {sig.missing_categories}")
        
        for sig in semantic_signals:
            if sig.name_changed:
                reasons.append(f"Column '{sig.column_name}' name or structure changed")
            if sig.unit_changed:
                reasons.append(f"Column '{sig.column_name}' unit changed: {sig.old_meaning} -> {sig.new_meaning}")
        
        # Determine severity
        if overall_score >= 0.7:
            severity = 'high'
        elif overall_score >= 0.4:
            severity = 'moderate'
        else:
            severity = 'low'
        
        drift_detected = overall_score >= 0.3
        
        return severity, drift_detected, reasons
    
    def _generate_run_id(self) -> str:
        """Generate unique run ID."""
        import uuid
        return str(uuid.uuid4())
    
    def _save_result(self, result: ComprehensiveDriftResult) -> None:
        """Save drift result to file."""
        result_path = self.results_dir / f"{result.drift_run_id}.json"
        result_path.write_text(json.dumps(result.to_dict(), indent=2))
    
    def get_result(self, run_id: str) -> Optional[ComprehensiveDriftResult]:
        """Retrieve a saved drift result."""
        result_path = self.results_dir / f"{run_id}.json"
        if result_path.exists():
            data = json.loads(result_path.read_text())
            return self._dict_to_result(data)
        return None
    
    def _dict_to_result(self, data: Dict[str, Any]) -> ComprehensiveDriftResult:
        """Convert dict back to ComprehensiveDriftResult."""
        stat_sigs = [
            StatisticalDriftSignals(**sig) for sig in data.get('statistical_signals', [])
        ]
        sem_sigs = [
            SemanticDriftSignals(**sig) for sig in data.get('semantic_signals', [])
        ]
        behav_sig = None
        if data.get('behavioral_signals'):
            behav_sig = BehavioralDriftSignals(**data['behavioral_signals'])
        
        return ComprehensiveDriftResult(
            drift_run_id=data['drift_run_id'],
            timestamp=data['timestamp'],
            dataset_version_a=data['dataset_version_a'],
            dataset_version_b=data.get('dataset_version_b'),
            is_internal_drift=data['is_internal_drift'],
            statistical_signals=stat_sigs,
            semantic_signals=sem_sigs,
            behavioral_signals=behav_sig,
            statistical_drift_score=data['statistical_drift_score'],
            semantic_drift_score=data['semantic_drift_score'],
            behavioral_drift_score=data['behavioral_drift_score'],
            internal_drift_score=data['internal_drift_score'],
            external_drift_score=data['external_drift_score'],
            overall_drift_score=data['overall_drift_score'],
            severity=data['severity'],
            drift_detected=data['drift_detected'],
            reasons=data['reasons'],
            human_reviewed=data.get('human_reviewed', False),
            human_label=data.get('human_label'),
        )
