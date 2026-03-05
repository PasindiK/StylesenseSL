"""Integration layer for Data Fabric.

Handles orchestration and workflow management including:
- Workflow orchestration
- Job scheduling
- Pipeline management
"""

from .orchestrator import WorkflowOrchestrator, WorkflowStatus
from .workflows import Workflow, WorkflowStep, WorkflowExecutor
from .virtual_integration import (
    VirtualIntegrationLayer,
    IntelligentRelationshipDiscovery,
    InferredRelationship,
)
from .relationship_engines import (
    StructuralFeatureExtractor,
    StatisticalFeatureExtractor,
    BehavioralFeatureExtractor,
    FeatureVectorBuilder,
    RelationshipScoringEngine,
    RelationshipDiscoveryEngine,
)
from .relationship_discovery_engine import (
    RelationshipDiscoveryEngine as RelationshipDiscoveryEngineV2,
    InferredRelationship as InferredRelationshipV2,
)
from .statistical_features import StatisticalFeatureExtractor as StatisticalFeatureExtractorV2
from .behavioral_features import BehavioralFeatureExtractor as BehavioralFeatureExtractorV2
from .feature_vector_builder import FeatureVectorBuilder as FeatureVectorBuilderV2
from .scoring_engine import RelationshipScoringEngine as RelationshipScoringEngineV2
from .join_executor import JoinExecutor, ManualInterventionRequired

__all__ = [
    "WorkflowOrchestrator",
    "WorkflowStatus",
    "Workflow",
    "WorkflowStep",
    "WorkflowExecutor",
    "VirtualIntegrationLayer",
    "IntelligentRelationshipDiscovery",
    "InferredRelationship",
    "StructuralFeatureExtractor",
    "StatisticalFeatureExtractor",
    "BehavioralFeatureExtractor",
    "FeatureVectorBuilder",
    "RelationshipScoringEngine",
    "RelationshipDiscoveryEngine",
    "StatisticalFeatureExtractorV2",
    "BehavioralFeatureExtractorV2",
    "FeatureVectorBuilderV2",
    "RelationshipScoringEngineV2",
    "JoinExecutor",
    "ManualInterventionRequired",
    "RelationshipDiscoveryEngineV2",
    "InferredRelationshipV2",
]
