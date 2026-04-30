from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class FeatureContract:
    name: str
    dtype: str = "float"
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    nullable: bool = True
    severity: str = "hard"
    description: str = ""


@dataclass
class FeatureValidationIssue:
    feature_name: str
    severity: str
    message: str


@dataclass
class FeatureValidationResult:
    is_valid: bool
    issues: List[FeatureValidationIssue] = field(default_factory=list)

    @property
    def hard_failures(self) -> List[FeatureValidationIssue]:
        return [issue for issue in self.issues if issue.severity == "hard"]

    @property
    def soft_failures(self) -> List[FeatureValidationIssue]:
        return [issue for issue in self.issues if issue.severity != "hard"]


@dataclass
class DriftResult:
    drift_detected: bool
    score: float
    reasons: List[str] = field(default_factory=list)


@dataclass
class FeatureReleaseDecision:
    status: str
    validation: FeatureValidationResult
    drift: DriftResult
    lineage: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RankedCandidate:
    product: Dict[str, Any]
    score: float
    stage_scores: Dict[str, float]
    release_status: str
    reasons: List[str]

