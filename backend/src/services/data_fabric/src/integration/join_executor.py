"""Autonomous join execution with manual intervention gates.

This module resolves join relationships from metadata-first signals and executes
on-demand joins. It enforces manual intervention when:
- multiple non-weak relationship candidates exist, or
- only weak relationships are available.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import pandas as pd

from src.metadata.catalog import MetadataCatalog


@dataclass
class JoinSuggestion:
    """Ranked candidate relationship suggestion for manual selection."""

    relationship_key: str
    left_dataset: str
    right_dataset: str
    left_column: str
    right_column: str
    confidence: float
    decision: str
    cardinality: str
    model_version: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "relationship_key": self.relationship_key,
            "left_dataset": self.left_dataset,
            "right_dataset": self.right_dataset,
            "left_column": self.left_column,
            "right_column": self.right_column,
            "confidence": self.confidence,
            "decision": self.decision,
            "cardinality": self.cardinality,
            "model_version": self.model_version,
        }


class JoinResolutionError(Exception):
    """Base class for join resolution failures."""


class ManualInterventionRequired(JoinResolutionError):
    """Raised when the system requires user selection before joining."""

    def __init__(self, message: str, suggestions: Sequence[JoinSuggestion]):
        super().__init__(message)
        self.suggestions = list(suggestions)


class JoinExecutor:
    """Resolve relationship candidates and execute autonomous joins."""

    def __init__(self, metadata_catalog: MetadataCatalog):
        self.catalog = metadata_catalog

    def execute(
        self,
        datasets: Dict[str, pd.DataFrame],
        left_dataset: str,
        right_dataset: str,
        *,
        relationship_factory: Callable[..., Any],
        discover_relationships: Callable[[Dict[str, pd.DataFrame]], List[Any]],
        build_manual_relationship: Callable[..., Any],
        register_inferred_relationship: Callable[[Any], None],
        register_derived_dataset: Callable[..., None],
        left_on: Optional[str] = None,
        right_on: Optional[str] = None,
        how: str = "inner",
        output_dataset: Optional[str] = None,
        producer_pipeline: str = "integration.virtual_integration_layer",
        selected_relationship_key: Optional[str] = None,
        allow_weak_relationship: bool = False,
    ) -> Tuple[pd.DataFrame, Any]:
        """Execute join with autonomous resolution and metadata lineage updates."""
        if left_dataset not in datasets:
            raise ValueError(f"Dataset not found: {left_dataset}")
        if right_dataset not in datasets:
            raise ValueError(f"Dataset not found: {right_dataset}")

        left_df = datasets[left_dataset]
        right_df = datasets[right_dataset]

        if left_on is None or right_on is None:
            relationship = self._resolve_relationship(
                datasets=datasets,
                left_dataset=left_dataset,
                right_dataset=right_dataset,
                relationship_factory=relationship_factory,
                discover_relationships=discover_relationships,
                selected_relationship_key=selected_relationship_key,
                allow_weak_relationship=allow_weak_relationship,
            )
        else:
            relationship = build_manual_relationship(
                left_dataset=left_dataset,
                right_dataset=right_dataset,
                left_col=left_on,
                right_col=right_on,
                left_df=left_df,
                right_df=right_df,
            )
            register_inferred_relationship(relationship)

        joined = pd.merge(
            left_df,
            right_df,
            left_on=relationship.left_column,
            right_on=relationship.right_column,
            how=how,
            suffixes=(f"_{left_dataset}", f"_{right_dataset}"),
        )

        join_name = output_dataset or f"virtual_{left_dataset}_{right_dataset}_joined"
        register_derived_dataset(
            output_dataset=join_name,
            joined_df=joined,
            input_datasets=[left_dataset, right_dataset],
            producer_pipeline=producer_pipeline,
            relationship=relationship,
        )

        return joined, relationship

    def _resolve_relationship(
        self,
        datasets: Dict[str, pd.DataFrame],
        left_dataset: str,
        right_dataset: str,
        relationship_factory: Callable[..., Any],
        discover_relationships: Callable[[Dict[str, pd.DataFrame]], List[Any]],
        selected_relationship_key: Optional[str],
        allow_weak_relationship: bool,
    ) -> Any:
        candidates = self._get_pair_candidates_from_metadata(
            dataset_name=left_dataset,
            left_dataset=left_dataset,
            right_dataset=right_dataset,
            relationship_factory=relationship_factory,
        )

        if not candidates:
            discover_relationships({
                left_dataset: datasets[left_dataset],
                right_dataset: datasets[right_dataset],
            })
            candidates = self._get_pair_candidates_from_metadata(
                dataset_name=left_dataset,
                left_dataset=left_dataset,
                right_dataset=right_dataset,
                relationship_factory=relationship_factory,
            )

        if not candidates:
            raise ManualInterventionRequired(
                (
                    f"No inferred relationship found for {left_dataset} and {right_dataset}. "
                    "Provide join keys manually."
                ),
                suggestions=[],
            )

        candidates.sort(key=lambda rel: float(rel.confidence), reverse=True)

        if selected_relationship_key:
            selected = next(
                (
                    rel
                    for rel in candidates
                    if self._relationship_key(rel) == str(selected_relationship_key)
                ),
                None,
            )
            if selected is None:
                raise ManualInterventionRequired(
                    f"Selected relationship_key '{selected_relationship_key}' was not found.",
                    suggestions=self._to_suggestions(candidates),
                )
            if str(selected.decision).lower() == "weak" and not allow_weak_relationship:
                raise ManualInterventionRequired(
                    "Selected relationship is weak. Confirm manually with allow_weak_relationship=True.",
                    suggestions=self._to_suggestions(candidates),
                )
            return selected

        non_weak = [rel for rel in candidates if str(rel.decision).lower() != "weak"]
        weak = [rel for rel in candidates if str(rel.decision).lower() == "weak"]

        if len(non_weak) > 1:
            raise ManualInterventionRequired(
                (
                    f"Multiple inferred relationships found between {left_dataset} and {right_dataset}. "
                    "Manual selection required."
                ),
                suggestions=self._to_suggestions(non_weak),
            )

        if len(non_weak) == 1:
            return non_weak[0]

        if weak and not allow_weak_relationship:
            raise ManualInterventionRequired(
                (
                    f"Only weak relationships found between {left_dataset} and {right_dataset}. "
                    "Manual selection required."
                ),
                suggestions=self._to_suggestions(weak),
            )

        return weak[0]

    def _get_pair_candidates_from_metadata(
        self,
        dataset_name: str,
        left_dataset: str,
        right_dataset: str,
        relationship_factory: Callable[..., Any],
    ) -> List[Any]:
        records = self.catalog.get_inferred_relationships(dataset_name=dataset_name)
        candidates: List[Any] = []

        for record in records:
            record_left = str(record.get("left_dataset", ""))
            record_right = str(record.get("right_dataset", ""))
            if {record_left, record_right} != {left_dataset, right_dataset}:
                continue

            candidates.append(
                relationship_factory(
                    left_dataset=record_left,
                    right_dataset=record_right,
                    left_column=str(record.get("left_column", "")),
                    right_column=str(record.get("right_column", "")),
                    name_similarity=float(record.get("name_similarity", 0.0)),
                    type_score=float(record.get("type_score", 0.0)),
                    overlap_ratio=float(record.get("overlap_ratio", 0.0)),
                    confidence=float(record.get("confidence", 0.0)),
                    cardinality=str(record.get("cardinality", "unknown")),
                    decision=str(record.get("decision", "weak")),
                    feature_vector=dict(record.get("feature_vector", {})),
                    model_version=str(record.get("model_version", "unknown")),
                    feature_vector_version=str(record.get("feature_vector_version", "unknown")),
                )
            )

        return candidates

    @staticmethod
    def _relationship_key(relationship: Any) -> str:
        left_dataset = str(getattr(relationship, "left_dataset", ""))
        right_dataset = str(getattr(relationship, "right_dataset", ""))
        left_column = str(getattr(relationship, "left_column", ""))
        right_column = str(getattr(relationship, "right_column", ""))
        return f"{left_dataset}:{left_column}->{right_dataset}:{right_column}"

    def _to_suggestions(self, relationships: Sequence[Any]) -> List[JoinSuggestion]:
        ordered = sorted(relationships, key=lambda rel: float(rel.confidence), reverse=True)
        return [
            JoinSuggestion(
                relationship_key=self._relationship_key(rel),
                left_dataset=str(rel.left_dataset),
                right_dataset=str(rel.right_dataset),
                left_column=str(rel.left_column),
                right_column=str(rel.right_column),
                confidence=float(rel.confidence),
                decision=str(rel.decision),
                cardinality=str(rel.cardinality),
                model_version=str(getattr(rel, "model_version", "unknown")),
            )
            for rel in ordered
        ]
