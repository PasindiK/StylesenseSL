"""Virtual integration layer with intelligent relationship discovery.

This module provides:
- On-demand virtual joins without permanent materialization
- Automatic relationship inference across datasets
- Confidence scoring using weighted signals
- Metadata catalog updates with inferred relationships
- Automatic lineage registration for derived datasets
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import logging

from ..metadata.catalog import MetadataCatalog
from .relationship_engines import (
    BehavioralFeatureExtractor,
    FeatureVectorBuilder,
    RelationshipDiscoveryEngine,
    RelationshipScoringEngine,
    StatisticalFeatureExtractor,
    StructuralFeatureExtractor,
)
from .join_executor import JoinExecutor

logger = logging.getLogger(__name__)


@dataclass
class InferredRelationship:
    """Represents a discovered relationship between two dataset columns."""

    left_dataset: str
    right_dataset: str
    left_column: str
    right_column: str
    name_similarity: float
    type_score: float
    overlap_ratio: float
    confidence: float
    cardinality: str
    decision: str
    feature_vector: Dict[str, Any]
    model_version: str
    feature_vector_version: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert inference to dictionary."""
        return {
            "left_dataset": self.left_dataset,
            "right_dataset": self.right_dataset,
            "left_column": self.left_column,
            "right_column": self.right_column,
            "name_similarity": round(self.name_similarity, 4),
            "type_score": round(self.type_score, 4),
            "overlap_ratio": round(self.overlap_ratio, 4),
            "confidence": round(self.confidence, 4),
            "cardinality": self.cardinality,
            "decision": self.decision,
            "feature_vector": self.feature_vector,
            "model_version": self.model_version,
            "feature_vector_version": self.feature_vector_version,
        }


class IntelligentRelationshipDiscovery:
    """Infer candidate inter-dataset relationships with weighted confidence."""

    NAME_WEIGHT = 0.3
    TYPE_WEIGHT = 0.2
    OVERLAP_WEIGHT = 0.5

    STRONG_THRESHOLD = 0.80
    PROBABLE_THRESHOLD = 0.5

    MODEL_DIR = Path(__file__).resolve().parents[2] / "models"
    LR_MODEL_FILENAME = "relationship_model_lr_v1.pkl"
    RF_MODEL_FILENAME = "relationship_model_v1.pkl"

    def __init__(self, sample_size: int = 10000):
        self.sample_size = sample_size
        self.behavioral_extractor = BehavioralFeatureExtractor(sample_size=sample_size)
        self.structural_extractor = StructuralFeatureExtractor(self.behavioral_extractor)
        self.statistical_extractor = StatisticalFeatureExtractor(sample_size=sample_size)
        self.feature_vector_builder = FeatureVectorBuilder(
            structural_extractor=self.structural_extractor,
            statistical_extractor=self.statistical_extractor,
            behavioral_extractor=self.behavioral_extractor,
        )
        lr_model_path = self.MODEL_DIR / self.LR_MODEL_FILENAME
        rf_model_path = self.MODEL_DIR / self.RF_MODEL_FILENAME
        self.scoring_engine = RelationshipScoringEngine(
            model_path=str(lr_model_path) if lr_model_path.exists() else None,
            rf_model_path=str(rf_model_path) if rf_model_path.exists() else None,
            lr_weight=0.3,
            rf_weight=0.7,
            name_weight=self.NAME_WEIGHT,
            type_weight=self.TYPE_WEIGHT,
            overlap_weight=self.OVERLAP_WEIGHT,
            strong_threshold=self.STRONG_THRESHOLD,
            probable_threshold=self.PROBABLE_THRESHOLD,
        )
        self.discovery_engine = RelationshipDiscoveryEngine(
            structural_extractor=self.structural_extractor,
            statistical_extractor=self.statistical_extractor,
            behavioral_extractor=self.behavioral_extractor,
            feature_vector_builder=self.feature_vector_builder,
            scoring_engine=self.scoring_engine,
        )

    def discover(self, datasets: Dict[str, pd.DataFrame]) -> List[InferredRelationship]:
        """Discover relationships across all dataset pairs.

        Returns inferred relationships with decisions:
        - strong: confidence >= 0.75
        - probable: 0.50 <= confidence < 0.75
        - weak: confidence < 0.50
        """
        return self.discovery_engine.discover(
            datasets=datasets,
            relationship_factory=InferredRelationship,
        )

    def get_best_relationship(
        self,
        left_dataset: str,
        right_dataset: str,
        relationships: List[InferredRelationship],
    ) -> Optional[InferredRelationship]:
        """Return highest-confidence relationship for a dataset pair."""
        return self.discovery_engine.get_best_relationship(
            left_dataset=left_dataset,
            right_dataset=right_dataset,
            relationships=relationships,
        )

    def _decision(self, confidence: float) -> str:
        return self.scoring_engine.decision(confidence)

    def _normalize_column_name(self, name: str) -> str:
        return self.structural_extractor.normalize_column_name(name)

    def _name_similarity(self, left_col: str, right_col: str) -> float:
        return self.structural_extractor.name_similarity(left_col, right_col)

    def _type_compatibility_score(self, left: pd.Series, right: pd.Series) -> float:
        return self.structural_extractor.type_compatibility_score(left, right)

    def _convertibility_score(self, left: pd.Series, right: pd.Series) -> float:
        return self.behavioral_extractor.convertibility_score(left, right)

    def _value_overlap_ratio(self, left: pd.Series, right: pd.Series) -> float:
        return self.statistical_extractor.value_overlap_ratio(left, right)

    def _sample_unique_values(self, series: pd.Series) -> set:
        return self.statistical_extractor.sample_unique_values(series)

    def _detect_cardinality(self, left: pd.Series, right: pd.Series) -> str:
        return self.structural_extractor.detect_cardinality(left, right)

    def _build_feature_vector(
        self,
        left_dataset: str,
        right_dataset: str,
        left_column: str,
        right_column: str,
        left_series: pd.Series,
        right_series: pd.Series,
        name_similarity: float,
        type_score: float,
        overlap_ratio: float,
    ) -> Dict[str, Any]:
        """Build a structured feature vector for a candidate column pair."""
        return self.feature_vector_builder.build(
            left_dataset=left_dataset,
            right_dataset=right_dataset,
            left_column=left_column,
            right_column=right_column,
            left_series=left_series,
            right_series=right_series,
        )

    def _numeric_range_similarity(self, left_series: pd.Series, right_series: pd.Series) -> Optional[float]:
        """Compute min/max range similarity for numeric columns.

        Returns similarity score in [0, 1], or None when not numeric.
        """
        return self.statistical_extractor.numeric_range_similarity(left_series, right_series)


class VirtualIntegrationLayer:
    """Virtual integration manager for on-demand joins and inferred relationships."""

    def __init__(self, metadata_catalog: MetadataCatalog):
        self.catalog = metadata_catalog
        self.discovery = IntelligentRelationshipDiscovery()
        self.join_executor = JoinExecutor(metadata_catalog=self.catalog)

    def _collect_catalog_relationships(self) -> List[Dict[str, Any]]:
        """Return unique relationship records currently persisted in catalog."""
        unique: Dict[str, Dict[str, Any]] = {}
        for asset in self.catalog.list_assets(asset_type="table"):
            for record in self.catalog.get_inferred_relationships(asset.name):
                key = str(record.get("relationship_key", "")).strip()
                if not key:
                    continue
                if key not in unique:
                    unique[key] = dict(record)
        return list(unique.values())

    def _hydrate_behavioral_context_from_catalog(self) -> None:
        """Feed persisted behavioral/catalog history back into discovery features."""
        join_history: Dict[Tuple[str, str], int] = {}
        co_query_history: Dict[Tuple[str, str], int] = {}
        inference_history: Dict[Tuple[str, str], Dict[str, int]] = {}

        lineage_graph: Dict[str, set] = {}
        for asset in self.catalog.list_assets(asset_type="table"):
            dataset_name = str(asset.name)
            dataset_info = self.catalog.get_dataset(dataset_name) or {}
            lineage_graph[dataset_name] = set(dataset_info.get("downstream_datasets", []))

        for rel in self._collect_catalog_relationships():
            left_dataset = str(rel.get("left_dataset", "")).strip()
            right_dataset = str(rel.get("right_dataset", "")).strip()
            left_column = str(rel.get("left_column", "")).strip()
            right_column = str(rel.get("right_column", "")).strip()
            if not left_dataset or not right_dataset or not left_column or not right_column:
                continue

            usage_count = int(rel.get("join_usage_count", 0) or 0)
            history = list(rel.get("history", []))

            column_pair = tuple(sorted((left_column, right_column)))
            dataset_pair = tuple(sorted((left_dataset, right_dataset)))

            join_history[column_pair] = max(join_history.get(column_pair, 0), usage_count)
            co_query_history[dataset_pair] = co_query_history.get(dataset_pair, 0) + max(1, usage_count)

            total_runs = len(history)
            if total_runs > 0:
                latest_decision = str(history[-1].get("decision", ""))
                stable_runs = sum(1 for item in history if str(item.get("decision", "")) == latest_decision)
            else:
                stable_runs = 0
            if bool(rel.get("is_unstable", False)) and total_runs > 0:
                stable_runs = min(stable_runs, max(0, total_runs - 1))

            previous = inference_history.get(column_pair, {"stable_runs": 0, "total_runs": 0})
            inference_history[column_pair] = {
                "stable_runs": int(previous.get("stable_runs", 0)) + int(stable_runs),
                "total_runs": int(previous.get("total_runs", 0)) + int(total_runs),
            }

        extractor = self.discovery.behavioral_extractor
        extractor.join_history = join_history
        extractor.co_query_history = co_query_history
        extractor.total_queries = max(1, sum(co_query_history.values())) if co_query_history else None
        extractor.lineage_graph = {node: set(neighbors) for node, neighbors in lineage_graph.items()}
        extractor.inference_history = inference_history

    def infer_relationships(
        self,
        datasets: Dict[str, pd.DataFrame],
        register_results: bool = True,
    ) -> List[InferredRelationship]:
        """Infer potential relationships and optionally register in metadata catalog."""
        self._hydrate_behavioral_context_from_catalog()
        inferences = self.discovery.discover(datasets)
        if register_results:
            for inference in inferences:
                self._register_inferred_relationship(inference)
        logger.info(
            "event=virtual_integration.relationships_inferred "
            f"total={len(inferences)}"
        )
        return inferences

    def join_on_demand(
        self,
        datasets: Dict[str, pd.DataFrame],
        left_dataset: str,
        right_dataset: str,
        left_on: Optional[str] = None,
        right_on: Optional[str] = None,
        how: str = "inner",
        output_dataset: Optional[str] = None,
        producer_pipeline: str = "integration.virtual_integration_layer",
        selected_relationship_key: Optional[str] = None,
        allow_weak_relationship: bool = False,
    ) -> Tuple[pd.DataFrame, InferredRelationship]:
        """Perform on-demand join and register derived dataset + lineage.

        If join keys are omitted, relationships are resolved from metadata first.
        Manual intervention is required for ambiguous candidates or weak-only matches.
        """
        output_name = output_dataset or f"virtual_{left_dataset}_{right_dataset}_{datetime.now().strftime('%Y%m%d%H%M%S')}"

        joined, relationship = self.join_executor.execute(
            datasets=datasets,
            left_dataset=left_dataset,
            right_dataset=right_dataset,
            relationship_factory=InferredRelationship,
            discover_relationships=lambda pair_datasets: self.infer_relationships(
                datasets=pair_datasets,
                register_results=True,
            ),
            build_manual_relationship=self._build_manual_relationship,
            register_inferred_relationship=self._register_inferred_relationship,
            register_derived_dataset=self._register_derived_dataset,
            left_on=left_on,
            right_on=right_on,
            how=how,
            output_dataset=output_name,
            producer_pipeline=producer_pipeline,
            selected_relationship_key=selected_relationship_key,
            allow_weak_relationship=allow_weak_relationship,
        )

        logger.info(
            "event=virtual_integration.join_created "
            f"output_dataset={output_name} left_dataset={left_dataset} right_dataset={right_dataset} "
            f"left_on={relationship.left_column} right_on={relationship.right_column} confidence={relationship.confidence:.4f} "
            f"decision={relationship.decision} rows={len(joined)}"
        )
        return joined, relationship

    def get_impact_analysis(self, dataset_name: str) -> Dict[str, Any]:
        """Get impact analysis using metadata lineage graph."""
        return {
            "dataset_name": dataset_name,
            "downstream_dependencies": self.catalog.get_downstream_dependencies(dataset_name),
        }

    def _build_manual_relationship(
        self,
        left_dataset: str,
        right_dataset: str,
        left_col: str,
        right_col: str,
        left_df: pd.DataFrame,
        right_df: pd.DataFrame,
    ) -> InferredRelationship:
        name_similarity = self.discovery._name_similarity(left_col, right_col)
        type_score = self.discovery._type_compatibility_score(left_df[left_col], right_df[right_col])
        overlap_ratio = self.discovery._value_overlap_ratio(left_df[left_col], right_df[right_col])
        feature_vector = self.discovery._build_feature_vector(
            left_dataset=left_dataset,
            right_dataset=right_dataset,
            left_column=left_col,
            right_column=right_col,
            left_series=left_df[left_col],
            right_series=right_df[right_col],
            name_similarity=name_similarity,
            type_score=type_score,
            overlap_ratio=overlap_ratio,
        )
        score_details = self.discovery.scoring_engine.score_with_details(feature_vector)
        confidence = float(score_details["confidence"])
        decision = str(score_details["decision"])
        cardinality = self.discovery._detect_cardinality(left_df[left_col], right_df[right_col])
        return InferredRelationship(
            left_dataset=left_dataset,
            right_dataset=right_dataset,
            left_column=left_col,
            right_column=right_col,
            name_similarity=name_similarity,
            type_score=type_score,
            overlap_ratio=overlap_ratio,
            confidence=confidence,
            cardinality=cardinality,
            decision=decision,
            feature_vector={
                **feature_vector,
                "models_used": score_details.get("models_used", {}),
                "confidence_source": score_details.get("confidence_source", "static"),
            },
            model_version=str(self.discovery.scoring_engine.model_version),
            feature_vector_version=str(feature_vector.get("feature_vector_version", "unknown")),
        )

    def _register_inferred_relationship(self, relationship: InferredRelationship) -> None:
        """Persist inferred relationship metadata for both datasets."""
        payload = relationship.to_dict()
        dedup_key = (
            f"{payload['left_dataset']}:{payload['left_column']}->"
            f"{payload['right_dataset']}:{payload['right_column']}"
        )

        for dataset_name, counterpart in [
            (relationship.left_dataset, relationship.right_dataset),
            (relationship.right_dataset, relationship.left_dataset),
        ]:
            self.catalog.upsert_inferred_relationship(
                dataset_name=dataset_name,
                relationship={
                    **payload,
                    "relationship_key": dedup_key,
                },
                counterpart_dataset=counterpart,
            )

            if relationship.decision == "probable":
                logger.warning(
                    "event=virtual_integration.relationship_registered_with_warning "
                    f"dataset_name={dataset_name} confidence={relationship.confidence:.4f}"
                )
            else:
                logger.info(
                    "event=virtual_integration.relationship_registered "
                    f"dataset_name={dataset_name} confidence={relationship.confidence:.4f}"
                )

    def _register_derived_dataset(
        self,
        output_dataset: str,
        joined_df: pd.DataFrame,
        input_datasets: List[str],
        producer_pipeline: str,
        relationship: InferredRelationship,
    ) -> None:
        """Register derived dataset metadata and lineage."""
        schema = {col: str(dtype) for col, dtype in joined_df.dtypes.items()}

        input_scores = []
        for source_name in input_datasets:
            source = self.catalog.get_asset(source_name)
            if source is not None:
                input_scores.append(source.metadata.quality_score)

        quality_score = float(sum(input_scores) / len(input_scores)) if input_scores else 0.0

        self.catalog.upsert_dataset(
            dataset_name=output_dataset,
            domain="integration",
            schema=schema,
            row_count=len(joined_df),
            producer_pipeline=producer_pipeline,
            validation_status="warning" if relationship.decision == "probable" else "pass",
            quality_score=quality_score,
            description=(
                f"Virtual join output from {input_datasets[0]} and {input_datasets[1]}"
            ),
            owner="integration",
            source_system="virtual_join",
            location=f"virtual://{output_dataset}",
            tags=["virtual_integration", relationship.decision],
            properties={
                "integration_confidence": relationship.confidence,
                "integration_decision": relationship.decision,
                "integration_cardinality": relationship.cardinality,
                "integration_feature_vector": relationship.feature_vector,
                "integration_columns": {
                    "left": relationship.left_column,
                    "right": relationship.right_column,
                },
            },
        )

        self.catalog.register_lineage(input_datasets=input_datasets, output_dataset=output_dataset)
