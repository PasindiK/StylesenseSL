"""Autonomous integration agent for continuous relationship governance.

Responsibilities:
- Monitor metadata for new or updated datasets
- Trigger relationship discovery when catalog changes are detected
- Log join usage and update behavioral features
- Retrain LR model when enough labels exist
- Detect confidence drift and flag unstable relationships
- Support manual, scheduled, and background loop execution modes
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from threading import Event, Thread
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
import logging
import time

import pandas as pd

from ..metadata.catalog import MetadataCatalog
from .virtual_integration import InferredRelationship, VirtualIntegrationLayer

logger = logging.getLogger(__name__)


@dataclass
class AgentRunReport:
    """Summary of one autonomous agent execution cycle."""

    started_at: str
    finished_at: str
    new_datasets: List[str]
    updated_datasets: List[str]
    relationships_discovered: int
    usage_updates: int
    behavioral_updates: int
    drift_flags: int
    retrained: bool
    retrained_model_version: Optional[str]
    retrained_labels: int


class AutonomousIntegrationAgent:
    """Autonomous controller that keeps integration metadata adaptive."""

    MODEL_DIR = Path(__file__).resolve().parents[2] / "models"
    MODEL_FILENAME = "relationship_model_lr_v1.pkl"

    def __init__(
        self,
        metadata_catalog: MetadataCatalog,
        dataset_loader: Optional[Callable[[str], Optional[pd.DataFrame]]] = None,
        drift_threshold: float = 0.20,
        retrain_label_threshold: int = 50,
    ):
        self.catalog = metadata_catalog
        self.integration_layer = VirtualIntegrationLayer(metadata_catalog=self.catalog)
        self.dataset_loader = dataset_loader
        self.drift_threshold = float(drift_threshold)
        self.retrain_label_threshold = int(retrain_label_threshold)

        self._last_seen_updates: Dict[str, str] = {}
        self._stop_event = Event()
        self._thread: Optional[Thread] = None

        self.MODEL_DIR.mkdir(parents=True, exist_ok=True)

    def run_once(self) -> AgentRunReport:
        """Run a full autonomous cycle once (manual trigger mode)."""
        started = datetime.now().isoformat()

        new_datasets, updated_datasets = self._detect_catalog_changes()
        discovered = self._trigger_relationship_discovery(new_datasets + updated_datasets)
        behavioral_updates = self.update_behavioral_features()
        drift_flags = self.detect_and_flag_confidence_drift(threshold=self.drift_threshold)
        retrain = self.retrain_model_if_ready(label_threshold=self.retrain_label_threshold)

        finished = datetime.now().isoformat()
        report = AgentRunReport(
            started_at=started,
            finished_at=finished,
            new_datasets=new_datasets,
            updated_datasets=updated_datasets,
            relationships_discovered=discovered,
            usage_updates=0,
            behavioral_updates=behavioral_updates,
            drift_flags=drift_flags,
            retrained=bool(retrain.get("retrained", False)),
            retrained_model_version=retrain.get("model_version"),
            retrained_labels=int(retrain.get("labels", 0)),
        )

        logger.info(
            "event=autonomous_agent.run_once "
            "new_datasets=%s updated_datasets=%s relationships_discovered=%s "
            "behavioral_updates=%s drift_flags=%s retrained=%s retrained_model_version=%s",
            len(report.new_datasets),
            len(report.updated_datasets),
            report.relationships_discovered,
            report.behavioral_updates,
            report.drift_flags,
            report.retrained,
            report.retrained_model_version,
        )
        return report

    def trigger_manual(self) -> AgentRunReport:
        """Manual trigger wrapper."""
        return self.run_once()

    def start_background_loop(self, interval_seconds: int = 300) -> None:
        """Start continuous background execution loop."""
        if self._thread and self._thread.is_alive():
            logger.info("event=autonomous_agent.loop_already_running")
            return

        self._stop_event.clear()
        self._thread = Thread(
            target=self._loop,
            kwargs={"interval_seconds": int(interval_seconds)},
            name="autonomous-integration-agent",
            daemon=True,
        )
        self._thread.start()
        logger.info("event=autonomous_agent.loop_started interval_seconds=%s", interval_seconds)

    def stop_background_loop(self, timeout_seconds: float = 2.0) -> None:
        """Stop background loop if running."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout_seconds)
        logger.info("event=autonomous_agent.loop_stopped")

    def run_scheduled(self, cycles: int, interval_seconds: int = 300) -> List[AgentRunReport]:
        """Run a fixed number of cycles (scheduled mode)."""
        reports: List[AgentRunReport] = []
        for _ in range(max(0, int(cycles))):
            reports.append(self.run_once())
            time.sleep(max(1, int(interval_seconds)))
        return reports

    def log_join_usage(
        self,
        left_dataset: str,
        right_dataset: str,
        relationship_key: Optional[str] = None,
        consumer_name: str = "integration.join_executor",
    ) -> int:
        """Record relationship usage from executed joins and refresh behavioral features.

        Returns number of relationship records updated.
        """
        now = datetime.now().isoformat()
        self.catalog.track_consumer_access(dataset_name=left_dataset, consumer_name=consumer_name)
        self.catalog.track_consumer_access(dataset_name=right_dataset, consumer_name=consumer_name)

        updates = 0
        for dataset_name in [left_dataset, right_dataset]:
            records = self.catalog.get_inferred_relationships(dataset_name=dataset_name)
            changed = False
            for record in records:
                if {str(record.get("left_dataset", "")), str(record.get("right_dataset", ""))} != {
                    left_dataset,
                    right_dataset,
                }:
                    continue
                key = str(record.get("relationship_key", ""))
                if relationship_key and key != relationship_key:
                    continue

                record["join_usage_count"] = int(record.get("join_usage_count", 0)) + 1
                record["last_used_at"] = now
                changed = True
                updates += 1

            if changed:
                self._replace_relationship_records(dataset_name=dataset_name, records=records)

        if updates > 0:
            self.update_behavioral_features()

        logger.info(
            "event=autonomous_agent.join_usage_logged left_dataset=%s right_dataset=%s updates=%s",
            left_dataset,
            right_dataset,
            updates,
        )
        return updates

    def update_behavioral_features(self) -> int:
        """Update behavioral features in relationship feature vectors."""
        now = datetime.now().isoformat()
        updated = 0

        for asset in self.catalog.list_assets(asset_type="table"):
            dataset_name = asset.name
            records = self.catalog.get_inferred_relationships(dataset_name=dataset_name)
            if not records:
                continue

            changed = False
            for record in records:
                history = list(record.get("history", []))
                usage_count = int(record.get("join_usage_count", 0))
                stability = self._compute_stability(history)

                fv = dict(record.get("feature_vector", {}))
                fv["join_usage_count"] = usage_count
                fv["history_points"] = len(history)
                fv["relationship_stability"] = stability
                fv["behavioral_updated_at"] = now

                record["feature_vector"] = fv
                record["behavioral_score"] = float(
                    min(1.0, (0.6 * stability) + (0.4 * min(1.0, usage_count / 20.0)))
                )
                changed = True
                updated += 1

            if changed:
                self._replace_relationship_records(dataset_name=dataset_name, records=records)

        logger.info("event=autonomous_agent.behavioral_features_updated relationships=%s", updated)
        return updated

    def detect_and_flag_confidence_drift(self, threshold: float = 0.20) -> int:
        """Flag unstable relationships when confidence drift is above threshold.

        threshold=0.20 means confidence movement greater than 20 percentage points.
        """
        flagged = 0
        threshold = float(threshold)

        for asset in self.catalog.list_assets(asset_type="table"):
            dataset_name = asset.name
            records = self.catalog.get_inferred_relationships(dataset_name=dataset_name)
            if not records:
                continue

            changed = False
            for record in records:
                history = list(record.get("history", []))
                if len(history) < 2:
                    continue

                first = float(history[0].get("confidence", 0.0))
                last = float(history[-1].get("confidence", 0.0))
                drift = abs(last - first)
                decision_changed = str(history[0].get("decision", "")) != str(history[-1].get("decision", ""))

                is_unstable = bool(drift > threshold or decision_changed)
                previous_flag = bool(record.get("is_unstable", False))
                record["is_unstable"] = is_unstable
                record["drift_score"] = drift
                record["unstable_reason"] = (
                    "confidence_drift" if drift > threshold else "decision_changed" if decision_changed else "stable"
                )

                if is_unstable and not previous_flag:
                    flagged += 1
                changed = True

            if changed:
                self._replace_relationship_records(dataset_name=dataset_name, records=records)

        logger.info("event=autonomous_agent.drift_detection_complete flagged=%s", flagged)
        return flagged

    def retrain_model_if_ready(self, label_threshold: int = 50) -> Dict[str, Any]:
        """Retrain LR scoring model when enough labels are available."""
        feature_vectors, labels = self._collect_training_examples()

        if len(labels) < int(label_threshold):
            return {
                "retrained": False,
                "reason": "insufficient_labels",
                "labels": len(labels),
            }

        positive = int(sum(labels))
        negative = len(labels) - positive
        if positive == 0 or negative == 0:
            return {
                "retrained": False,
                "reason": "single_class_labels",
                "labels": len(labels),
            }

        engine = self.integration_layer.discovery.scoring_engine
        new_version = f"autonomous_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        engine.model_version = new_version
        engine.fit(feature_vectors, labels, feature_order=list(engine.DEFAULT_FEATURE_ORDER), class_weight="balanced")

        target_path = self.MODEL_DIR / self.MODEL_FILENAME
        engine.save_model(str(target_path))
        engine.load_model(str(target_path))

        logger.info(
            "event=autonomous_agent.model_retrained model_version=%s labels=%s positives=%s negatives=%s path=%s",
            new_version,
            len(labels),
            positive,
            negative,
            str(target_path),
        )

        return {
            "retrained": True,
            "model_version": new_version,
            "labels": len(labels),
            "model_path": str(target_path),
        }

    def _loop(self, interval_seconds: int) -> None:
        while not self._stop_event.is_set():
            try:
                self.run_once()
            except Exception as exc:
                logger.exception("Autonomous agent loop iteration failed: %s", exc)
            self._stop_event.wait(max(1, int(interval_seconds)))

    def _detect_catalog_changes(self) -> Tuple[List[str], List[str]]:
        new_datasets: List[str] = []
        updated_datasets: List[str] = []

        assets = self.catalog.list_assets(asset_type="table")
        current: Dict[str, str] = {}
        for asset in assets:
            dataset_name = asset.name
            updated_at = asset.metadata.updated_at.isoformat()
            current[dataset_name] = updated_at

            if dataset_name not in self._last_seen_updates:
                new_datasets.append(dataset_name)
            elif self._last_seen_updates[dataset_name] != updated_at:
                updated_datasets.append(dataset_name)

        self._last_seen_updates = current
        return sorted(new_datasets), sorted(updated_datasets)

    def _trigger_relationship_discovery(self, changed_datasets: List[str]) -> int:
        if not changed_datasets:
            return 0
        if self.dataset_loader is None:
            logger.warning(
                "event=autonomous_agent.discovery_skipped reason=missing_dataset_loader changed=%s",
                len(changed_datasets),
            )
            return 0

        dataset_frames: Dict[str, pd.DataFrame] = {}
        for dataset_name in sorted(set(changed_datasets)):
            try:
                frame = self.dataset_loader(dataset_name)
            except Exception as exc:
                logger.warning("Dataset loader failed for %s: %s", dataset_name, exc)
                continue
            if frame is None or frame.empty:
                continue
            dataset_frames[dataset_name] = frame

        # Add stable context datasets for better pair discovery.
        for asset in self.catalog.list_assets(asset_type="table"):
            dataset_name = asset.name
            if dataset_name in dataset_frames:
                continue
            try:
                frame = self.dataset_loader(dataset_name)
            except Exception:
                continue
            if frame is None or frame.empty:
                continue
            dataset_frames[dataset_name] = frame

        if len(dataset_frames) < 2:
            logger.warning(
                "event=autonomous_agent.discovery_skipped reason=insufficient_datasets loaded=%s",
                len(dataset_frames),
            )
            return 0

        inferences = self.integration_layer.infer_relationships(datasets=dataset_frames, register_results=True)
        changed_set = set(changed_datasets)
        impacted = [
            rel
            for rel in inferences
            if rel.left_dataset in changed_set or rel.right_dataset in changed_set
        ]

        logger.info(
            "event=autonomous_agent.discovery_complete changed_datasets=%s total_inferences=%s impacted=%s",
            len(changed_datasets),
            len(inferences),
            len(impacted),
        )
        return len(impacted)

    def _replace_relationship_records(self, dataset_name: str, records: List[Dict[str, Any]]) -> bool:
        asset = self.catalog.get_asset(dataset_name)
        if asset is None:
            return False

        metadata = asset.metadata
        now = datetime.now().isoformat()
        metadata.properties = {
            **metadata.properties,
            "inferred_relationships": records,
            "inferred_relationships_last_updated": now,
            "last_updated": now,
        }
        metadata.updated_at = datetime.now()
        return self.catalog.update_asset_metadata(dataset_name, metadata)

    def _collect_training_examples(self) -> Tuple[List[List[float]], List[int]]:
        vectors: List[List[float]] = []
        labels: List[int] = []
        seen: Set[str] = set()

        for asset in self.catalog.list_assets(asset_type="table"):
            for record in self.catalog.get_inferred_relationships(asset.name):
                key = str(record.get("relationship_key", ""))
                if not key or key in seen:
                    continue

                label = self._extract_label(record)
                if label is None:
                    continue

                feature_vector = dict(record.get("feature_vector", {}))
                row = [
                    float(feature_vector.get("name_similarity", record.get("name_similarity", 0.0))),
                    float(feature_vector.get("type_score", record.get("type_score", 0.0))),
                    float(feature_vector.get("overlap_ratio", record.get("overlap_ratio", 0.0))),
                ]
                vectors.append(row)
                labels.append(int(label))
                seen.add(key)

        return vectors, labels

    @staticmethod
    def _extract_label(record: Dict[str, Any]) -> Optional[int]:
        for key in ["label", "manual_label", "confirmed_label"]:
            if key in record:
                value = record.get(key)
                if isinstance(value, bool):
                    return int(value)
                if isinstance(value, (int, float)):
                    return int(1 if float(value) > 0 else 0)
                text = str(value).strip().lower()
                if text in {"1", "true", "yes", "positive", "strong"}:
                    return 1
                if text in {"0", "false", "no", "negative", "weak"}:
                    return 0

        # Pseudo-label fallback from decision bands.
        decision = str(record.get("decision", "")).lower()
        if decision == "strong":
            return 1
        if decision == "weak":
            return 0
        return None

    @staticmethod
    def _compute_stability(history: List[Dict[str, Any]]) -> float:
        if len(history) < 2:
            return 1.0
        first = float(history[0].get("confidence", 0.0))
        last = float(history[-1].get("confidence", 0.0))
        drift = abs(last - first)
        return float(max(0.0, 1.0 - drift))
