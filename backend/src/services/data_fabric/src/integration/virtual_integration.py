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
from difflib import SequenceMatcher
from itertools import combinations
from typing import Any, Dict, List, Optional, Tuple
import warnings

import pandas as pd
import logging

from src.metadata.catalog import MetadataCatalog

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
        }


class IntelligentRelationshipDiscovery:
    """Infer candidate inter-dataset relationships with weighted confidence."""

    NAME_WEIGHT = 0.3
    TYPE_WEIGHT = 0.2
    OVERLAP_WEIGHT = 0.5

    STRONG_THRESHOLD = 0.75
    PROBABLE_THRESHOLD = 0.5

    def __init__(self, sample_size: int = 10000):
        self.sample_size = sample_size

    def discover(self, datasets: Dict[str, pd.DataFrame]) -> List[InferredRelationship]:
        """Discover relationships across all dataset pairs.

        Returns inferred relationships with decisions:
        - strong: confidence >= 0.75
        - probable: 0.50 <= confidence < 0.75
        - weak: confidence < 0.50
        """
        inferences: List[InferredRelationship] = []
        dataset_names = sorted(datasets.keys())

        for left_name, right_name in combinations(dataset_names, 2):
            left_df = datasets[left_name]
            right_df = datasets[right_name]

            for left_col in left_df.columns:
                for right_col in right_df.columns:
                    name_similarity = self._name_similarity(left_col, right_col)
                    type_score = self._type_compatibility_score(left_df[left_col], right_df[right_col])
                    if type_score == 0:
                        continue

                    overlap_ratio = self._value_overlap_ratio(left_df[left_col], right_df[right_col])
                    feature_vector = self._build_feature_vector(
                        left_series=left_df[left_col],
                        right_series=right_df[right_col],
                        name_similarity=name_similarity,
                        type_score=type_score,
                        overlap_ratio=overlap_ratio,
                    )
                    confidence = (
                        self.NAME_WEIGHT * name_similarity
                        + self.TYPE_WEIGHT * type_score
                        + self.OVERLAP_WEIGHT * overlap_ratio
                    )

                    decision = self._decision(confidence)
                    if decision == "weak":
                        continue

                    cardinality = self._detect_cardinality(left_df[left_col], right_df[right_col])
                    inferences.append(
                        InferredRelationship(
                            left_dataset=left_name,
                            right_dataset=right_name,
                            left_column=left_col,
                            right_column=right_col,
                            name_similarity=name_similarity,
                            type_score=type_score,
                            overlap_ratio=overlap_ratio,
                            confidence=confidence,
                            cardinality=cardinality,
                            decision=decision,
                            feature_vector=feature_vector,
                        )
                    )

        inferences.sort(key=lambda rel: rel.confidence, reverse=True)
        return inferences

    def get_best_relationship(
        self,
        left_dataset: str,
        right_dataset: str,
        relationships: List[InferredRelationship],
    ) -> Optional[InferredRelationship]:
        """Return highest-confidence relationship for a dataset pair."""
        candidates = [
            rel
            for rel in relationships
            if {rel.left_dataset, rel.right_dataset} == {left_dataset, right_dataset}
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda rel: rel.confidence, reverse=True)
        return candidates[0]

    def _decision(self, confidence: float) -> str:
        if confidence >= self.STRONG_THRESHOLD:
            return "strong"
        if confidence >= self.PROBABLE_THRESHOLD:
            return "probable"
        return "weak"

    def _normalize_column_name(self, name: str) -> str:
        return "".join(ch for ch in name.lower() if ch.isalnum())

    def _name_similarity(self, left_col: str, right_col: str) -> float:
        left = self._normalize_column_name(left_col)
        right = self._normalize_column_name(right_col)
        return SequenceMatcher(None, left, right).ratio()

    def _type_compatibility_score(self, left: pd.Series, right: pd.Series) -> float:
        if pd.api.types.is_numeric_dtype(left) and pd.api.types.is_numeric_dtype(right):
            return 1.0

        if pd.api.types.is_datetime64_any_dtype(left) and pd.api.types.is_datetime64_any_dtype(right):
            return 1.0

        if pd.api.types.is_string_dtype(left) and pd.api.types.is_string_dtype(right):
            return 1.0

        if self._convertibility_score(left, right) >= 0.8:
            return 0.7

        return 0.0

    def _convertibility_score(self, left: pd.Series, right: pd.Series) -> float:
        left_non_null = left.dropna().astype(str)
        right_non_null = right.dropna().astype(str)
        if left_non_null.empty or right_non_null.empty:
            return 0.0

        left_sample = left_non_null.head(min(self.sample_size, len(left_non_null)))
        right_sample = right_non_null.head(min(self.sample_size, len(right_non_null)))

        left_to_numeric = pd.to_numeric(left_sample, errors="coerce").notna().mean()
        right_to_numeric = pd.to_numeric(right_sample, errors="coerce").notna().mean()
        numeric_score = min(left_to_numeric, right_to_numeric)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=UserWarning)
            left_to_date = pd.to_datetime(left_sample, errors="coerce").notna().mean()
            right_to_date = pd.to_datetime(right_sample, errors="coerce").notna().mean()
        datetime_score = min(left_to_date, right_to_date)

        return max(float(numeric_score), float(datetime_score))

    def _value_overlap_ratio(self, left: pd.Series, right: pd.Series) -> float:
        left_values = self._sample_unique_values(left)
        right_values = self._sample_unique_values(right)
        if not left_values or not right_values:
            return 0.0

        intersection = len(left_values.intersection(right_values))
        denominator = min(len(left_values), len(right_values))
        return float(intersection / denominator) if denominator > 0 else 0.0

    def _sample_unique_values(self, series: pd.Series) -> set:
        cleaned = series.dropna()
        if cleaned.empty:
            return set()

        if len(cleaned) > self.sample_size:
            cleaned = cleaned.sample(self.sample_size, random_state=42)

        return set(cleaned.astype(str).unique().tolist())

    def _detect_cardinality(self, left: pd.Series, right: pd.Series) -> str:
        left_non_null = left.dropna()
        right_non_null = right.dropna()
        if left_non_null.empty or right_non_null.empty:
            return "unknown"

        left_unique_ratio = float(left_non_null.nunique() / len(left_non_null))
        right_unique_ratio = float(right_non_null.nunique() / len(right_non_null))

        left_unique = left_unique_ratio >= 0.95
        right_unique = right_unique_ratio >= 0.95

        if left_unique and right_unique:
            return "one_to_one"
        if left_unique and not right_unique:
            return "one_to_many"
        if not left_unique and right_unique:
            return "many_to_one"
        return "many_to_many"

    def _build_feature_vector(
        self,
        left_series: pd.Series,
        right_series: pd.Series,
        name_similarity: float,
        type_score: float,
        overlap_ratio: float,
    ) -> Dict[str, Any]:
        """Build a structured feature vector for a candidate column pair."""
        left_non_null = left_series.dropna()
        right_non_null = right_series.dropna()

        left_unique_values = self._sample_unique_values(left_series)
        right_unique_values = self._sample_unique_values(right_series)

        left_uniqueness_ratio = float(
            left_non_null.nunique() / len(left_non_null)
        ) if len(left_non_null) > 0 else 0.0
        right_uniqueness_ratio = float(
            right_non_null.nunique() / len(right_non_null)
        ) if len(right_non_null) > 0 else 0.0

        if left_unique_values:
            containment_left_in_right = float(
                len(left_unique_values.intersection(right_unique_values)) / len(left_unique_values)
            )
        else:
            containment_left_in_right = 0.0

        if right_unique_values:
            containment_right_in_left = float(
                len(right_unique_values.intersection(left_unique_values)) / len(right_unique_values)
            )
        else:
            containment_right_in_left = 0.0

        left_null_pct = float(left_series.isna().mean() * 100)
        right_null_pct = float(right_series.isna().mean() * 100)
        null_percentage_diff = abs(left_null_pct - right_null_pct)

        numeric_range_similarity = self._numeric_range_similarity(left_series, right_series)

        return {
            "name_similarity": round(name_similarity, 6),
            "type_score": round(type_score, 6),
            "overlap_ratio": round(overlap_ratio, 6),
            "uniqueness_ratio": {
                "left": round(left_uniqueness_ratio, 6),
                "right": round(right_uniqueness_ratio, 6),
            },
            "bidirectional_containment_ratio": {
                "left_in_right": round(containment_left_in_right, 6),
                "right_in_left": round(containment_right_in_left, 6),
            },
            "null_percentage": {
                "left": round(left_null_pct, 6),
                "right": round(right_null_pct, 6),
                "difference": round(null_percentage_diff, 6),
            },
            "numeric_range_similarity": (
                round(numeric_range_similarity, 6)
                if numeric_range_similarity is not None
                else None
            ),
        }

    def _numeric_range_similarity(self, left_series: pd.Series, right_series: pd.Series) -> Optional[float]:
        """Compute min/max range similarity for numeric columns.

        Returns similarity score in [0, 1], or None when not numeric.
        """
        left_num = pd.to_numeric(left_series, errors="coerce").dropna()
        right_num = pd.to_numeric(right_series, errors="coerce").dropna()

        if left_num.empty or right_num.empty:
            return None

        left_min, left_max = float(left_num.min()), float(left_num.max())
        right_min, right_max = float(right_num.min()), float(right_num.max())

        left_range = left_max - left_min
        right_range = right_max - right_min

        if left_range == 0 and right_range == 0:
            return 1.0 if left_min == right_min else 0.0

        overlap_start = max(left_min, right_min)
        overlap_end = min(left_max, right_max)
        overlap = max(0.0, overlap_end - overlap_start)

        union_start = min(left_min, right_min)
        union_end = max(left_max, right_max)
        union_range = union_end - union_start
        if union_range == 0:
            return 0.0

        return float(overlap / union_range)


class VirtualIntegrationLayer:
    """Virtual integration manager for on-demand joins and inferred relationships."""

    def __init__(self, metadata_catalog: MetadataCatalog):
        self.catalog = metadata_catalog
        self.discovery = IntelligentRelationshipDiscovery()

    def infer_relationships(
        self,
        datasets: Dict[str, pd.DataFrame],
        register_results: bool = True,
    ) -> List[InferredRelationship]:
        """Infer potential relationships and optionally register in metadata catalog."""
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
    ) -> Tuple[pd.DataFrame, InferredRelationship]:
        """Perform on-demand join and register derived dataset + lineage.

        If join keys are omitted, the best inferred relationship is used.
        """
        if left_dataset not in datasets:
            raise ValueError(f"Dataset not found: {left_dataset}")
        if right_dataset not in datasets:
            raise ValueError(f"Dataset not found: {right_dataset}")

        left_df = datasets[left_dataset]
        right_df = datasets[right_dataset]

        if left_on is None or right_on is None:
            pair_relationships = self.infer_relationships(
                datasets={left_dataset: left_df, right_dataset: right_df},
                register_results=True,
            )
            best = self.discovery.get_best_relationship(left_dataset, right_dataset, pair_relationships)
            if best is None:
                raise ValueError(
                    f"No reliable relationship found between {left_dataset} and {right_dataset}"
                )
            left_on = best.left_column
            right_on = best.right_column
            relationship = best
        else:
            relationship = self._build_manual_relationship(
                left_dataset=left_dataset,
                right_dataset=right_dataset,
                left_col=left_on,
                right_col=right_on,
                left_df=left_df,
                right_df=right_df,
            )

        joined = pd.merge(
            left_df,
            right_df,
            left_on=left_on,
            right_on=right_on,
            how=how,
            suffixes=(f"_{left_dataset}", f"_{right_dataset}"),
        )

        output_name = output_dataset or (
            f"virtual_{left_dataset}_{right_dataset}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        )

        self._register_derived_dataset(
            output_dataset=output_name,
            joined_df=joined,
            input_datasets=[left_dataset, right_dataset],
            producer_pipeline=producer_pipeline,
            relationship=relationship,
        )

        logger.info(
            "event=virtual_integration.join_created "
            f"output_dataset={output_name} left_dataset={left_dataset} right_dataset={right_dataset} "
            f"left_on={left_on} right_on={right_on} confidence={relationship.confidence:.4f} "
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
        confidence = (
            self.discovery.NAME_WEIGHT * name_similarity
            + self.discovery.TYPE_WEIGHT * type_score
            + self.discovery.OVERLAP_WEIGHT * overlap_ratio
        )
        decision = self.discovery._decision(confidence)
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
            feature_vector=self.discovery._build_feature_vector(
                left_series=left_df[left_col],
                right_series=right_df[right_col],
                name_similarity=name_similarity,
                type_score=type_score,
                overlap_ratio=overlap_ratio,
            ),
        )

    def _register_inferred_relationship(self, relationship: InferredRelationship) -> None:
        """Persist inferred relationship metadata for both datasets."""
        payload = relationship.to_dict()

        for dataset_name, counterpart in [
            (relationship.left_dataset, relationship.right_dataset),
            (relationship.right_dataset, relationship.left_dataset),
        ]:
            asset = self.catalog.get_asset(dataset_name)
            if asset is None:
                continue

            metadata = asset.metadata
            existing = metadata.properties.get("inferred_relationships", [])
            dedup_key = (
                f"{payload['left_dataset']}:{payload['left_column']}->"
                f"{payload['right_dataset']}:{payload['right_column']}"
            )

            filtered = [
                item
                for item in existing
                if item.get("relationship_key") != dedup_key
            ]
            filtered.append(
                {
                    **payload,
                    "relationship_key": dedup_key,
                    "counterpart_dataset": counterpart,
                    "registered_at": datetime.now().isoformat(),
                }
            )
            metadata.properties["inferred_relationships"] = filtered
            metadata.properties["last_updated"] = datetime.now().isoformat()
            metadata.updated_at = datetime.now()

            self.catalog.update_asset_metadata(dataset_name, metadata)

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
