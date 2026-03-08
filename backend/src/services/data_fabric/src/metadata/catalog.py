"""Production-style metadata catalog for Data Fabric.

This module provides:
- Dataset governance metadata registration and updates
- Consumer tracking and automated usage monitoring
- Lineage tracking (upstream/downstream)
- Query APIs for discoverability and operations
- Dataset health monitoring and stale/failure detection
- SQLite persistence with thread-safe updates
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Dict, List, Optional
import json
import logging
import sqlite3
import uuid

logger = logging.getLogger(__name__)


@dataclass
class DatasetMetadata:
    """Metadata for a dataset.

    Includes compatibility fields used by existing ingestion/validation code and
    governance fields required by the Metadata Catalog module.
    """

    name: str
    description: str
    owner: str
    source_system: str
    schema: Dict[str, str]
    row_count: int
    column_count: int
    created_at: datetime
    updated_at: datetime
    tags: List[str] = field(default_factory=list)
    properties: Dict[str, Any] = field(default_factory=dict)
    quality_score: float = 0.0

    domain: str = "unknown"
    producer_pipeline: str = "unknown"
    validation_status: str = "warning"
    usage_count: int = 0
    last_accessed: Optional[datetime] = None

    @property
    def last_updated(self) -> datetime:
        """Alias for governance naming consistency."""
        return self.updated_at

    def to_dict(self) -> Dict[str, Any]:
        """Convert metadata to dictionary."""
        return {
            "name": self.name,
            "dataset_name": self.name,
            "description": self.description,
            "owner": self.owner,
            "source_system": self.source_system,
            "domain": self.domain,
            "schema": self.schema,
            "row_count": self.row_count,
            "column_count": self.column_count,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "last_updated": self.updated_at.isoformat(),
            "producer_pipeline": self.producer_pipeline,
            "validation_status": self.validation_status,
            "quality_score": self.quality_score,
            "tags": self.tags,
            "properties": self.properties,
            "usage_count": self.usage_count,
            "last_accessed": self.last_accessed.isoformat() if self.last_accessed else None,
        }


@dataclass
class DataAsset:
    """A data asset in the catalog."""

    asset_id: str
    name: str
    asset_type: str
    location: str
    metadata: DatasetMetadata
    access_level: str = "internal"
    retention_days: int = 365


class MetadataCatalog:
    """Central metadata catalog with SQLite persistence and governance APIs."""

    def __init__(self, db_path: Optional[str] = None):
        """Initialize metadata catalog.

        Args:
            db_path: Optional path to SQLite DB file.
                     Defaults to src/metadata/metadata_catalog.db
        """
        default_db = Path(__file__).resolve().parent / "metadata_catalog.db"
        self.db_path = str(Path(db_path) if db_path else default_db)
        self.lock = RLock()
        self._initialize_database()
        self._log_event("metadata_catalog.initialized", db_path=self.db_path)

    def _log_event(self, event: str, **fields: Any) -> None:
        """Structured logging helper."""
        payload = " ".join([f"{k}={v}" for k, v in sorted(fields.items())])
        logger.info(f"event={event} {payload}".strip())

    def _connect(self) -> sqlite3.Connection:
        """Create SQLite connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _initialize_database(self) -> None:
        """Create catalog tables if not present."""
        with self.lock:
            conn = self._connect()
            try:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS datasets (
                        dataset_name TEXT PRIMARY KEY,
                        domain TEXT NOT NULL,
                        schema_json TEXT NOT NULL,
                        row_count INTEGER NOT NULL,
                        column_count INTEGER NOT NULL,
                        created_at TEXT NOT NULL,
                        last_updated TEXT NOT NULL,
                        producer_pipeline TEXT NOT NULL,
                        validation_status TEXT NOT NULL,
                        quality_score REAL,
                        description TEXT,
                        owner TEXT,
                        source_system TEXT,
                        tags_json TEXT,
                        properties_json TEXT,
                        asset_type TEXT NOT NULL,
                        location TEXT,
                        access_level TEXT NOT NULL,
                        retention_days INTEGER NOT NULL,
                        usage_count INTEGER NOT NULL DEFAULT 0,
                        last_accessed TEXT
                    );

                    CREATE TABLE IF NOT EXISTS dataset_consumers (
                        dataset_name TEXT NOT NULL,
                        consumer_name TEXT NOT NULL,
                        usage_count INTEGER NOT NULL DEFAULT 0,
                        last_accessed TEXT,
                        PRIMARY KEY (dataset_name, consumer_name),
                        FOREIGN KEY(dataset_name) REFERENCES datasets(dataset_name)
                    );

                    CREATE TABLE IF NOT EXISTS lineage (
                        upstream_dataset TEXT NOT NULL,
                        downstream_dataset TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        PRIMARY KEY (upstream_dataset, downstream_dataset)
                    );
                    """
                )
                conn.commit()
            finally:
                conn.close()

    def _to_iso(self, value: Optional[datetime]) -> Optional[str]:
        return value.isoformat() if value else None

    def _from_iso(self, value: Optional[str]) -> Optional[datetime]:
        return datetime.fromisoformat(value) if value else None

    def _row_to_asset(self, row: sqlite3.Row) -> DataAsset:
        """Convert dataset row to DataAsset."""
        properties = json.loads(row["properties_json"] or "{}")
        tags = json.loads(row["tags_json"] or "[]")
        schema = json.loads(row["schema_json"] or "{}")
        metadata = DatasetMetadata(
            name=row["dataset_name"],
            description=row["description"] or "",
            owner=row["owner"] or "unknown",
            source_system=row["source_system"] or "unknown",
            schema=schema,
            row_count=int(row["row_count"]),
            column_count=int(row["column_count"]),
            created_at=self._from_iso(row["created_at"]) or datetime.now(),
            updated_at=self._from_iso(row["last_updated"]) or datetime.now(),
            tags=tags,
            properties=properties,
            quality_score=float(row["quality_score"] if row["quality_score"] is not None else 0.0),
            domain=row["domain"] or "unknown",
            producer_pipeline=row["producer_pipeline"] or "unknown",
            validation_status=row["validation_status"] or "warning",
            usage_count=int(row["usage_count"] or 0),
            last_accessed=self._from_iso(row["last_accessed"]),
        )
        return DataAsset(
            asset_id=row["dataset_name"],
            name=row["dataset_name"],
            asset_type=row["asset_type"],
            location=row["location"] or "",
            metadata=metadata,
            access_level=row["access_level"],
            retention_days=int(row["retention_days"]),
        )

    def _upsert_asset(self, asset: DataAsset) -> None:
        """Insert or update an asset in persistent store."""
        md = asset.metadata
        now = datetime.now()
        created_at = md.created_at
        last_updated = md.updated_at if md.updated_at else now
        domain = (
            (md.properties.get("domain") if md.properties else None)
            or md.domain
            or "unknown"
        )
        producer_pipeline = (
            (md.properties.get("producer_pipeline") if md.properties else None)
            or md.producer_pipeline
            or "unknown"
        )
        validation_status = (
            (md.properties.get("validation_status") if md.properties else None)
            or md.validation_status
            or "warning"
        )

        with self.lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO datasets (
                        dataset_name, domain, schema_json, row_count, column_count,
                        created_at, last_updated, producer_pipeline,
                        validation_status, quality_score, description, owner,
                        source_system, tags_json, properties_json, asset_type,
                        location, access_level, retention_days, usage_count, last_accessed
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(dataset_name) DO UPDATE SET
                        domain=excluded.domain,
                        schema_json=excluded.schema_json,
                        row_count=excluded.row_count,
                        column_count=excluded.column_count,
                        last_updated=excluded.last_updated,
                        producer_pipeline=excluded.producer_pipeline,
                        validation_status=excluded.validation_status,
                        quality_score=excluded.quality_score,
                        description=excluded.description,
                        owner=excluded.owner,
                        source_system=excluded.source_system,
                        tags_json=excluded.tags_json,
                        properties_json=excluded.properties_json,
                        asset_type=excluded.asset_type,
                        location=excluded.location,
                        access_level=excluded.access_level,
                        retention_days=excluded.retention_days,
                        usage_count=excluded.usage_count,
                        last_accessed=excluded.last_accessed
                    """,
                    (
                        asset.asset_id,
                        domain,
                        json.dumps(md.schema),
                        int(md.row_count),
                        int(md.column_count),
                        self._to_iso(created_at),
                        self._to_iso(last_updated),
                        producer_pipeline,
                        validation_status,
                        float(md.quality_score) if md.quality_score is not None else None,
                        md.description,
                        md.owner,
                        md.source_system,
                        json.dumps(md.tags),
                        json.dumps(md.properties),
                        asset.asset_type,
                        asset.location,
                        asset.access_level,
                        int(asset.retention_days),
                        int(md.usage_count),
                        self._to_iso(md.last_accessed),
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def register_asset(self, asset: DataAsset) -> bool:
        """Register a new data asset.

        Returns False if already present (compatibility behavior), True otherwise.
        """
        existing = self.get_asset(asset.asset_id)
        if existing is not None:
            self._log_event("metadata_catalog.asset_exists", dataset_name=asset.asset_id)
            return False

        self._upsert_asset(asset)
        self._log_event("metadata_catalog.asset_registered", dataset_name=asset.asset_id)
        return True

    def upsert_dataset(
        self,
        dataset_name: str,
        domain: str,
        schema: Dict[str, str],
        row_count: int,
        producer_pipeline: str,
        validation_status: str = "warning",
        quality_score: Optional[float] = None,
        description: str = "",
        owner: str = "ingestion",
        source_system: str = "unknown",
        location: str = "",
        tags: Optional[List[str]] = None,
        properties: Optional[Dict[str, Any]] = None,
    ) -> DataAsset:
        """Register or update dataset metadata (pipeline automation entrypoint)."""
        now = datetime.now()
        existing = self.get_asset(dataset_name)
        created_at = existing.metadata.created_at if existing else now
        tags = tags or []
        properties = properties or {}

        metadata = DatasetMetadata(
            name=dataset_name,
            description=description,
            owner=owner,
            source_system=source_system,
            schema=schema,
            row_count=row_count,
            column_count=len(schema),
            created_at=created_at,
            updated_at=now,
            tags=tags,
            properties=properties,
            quality_score=float(quality_score if quality_score is not None else (existing.metadata.quality_score if existing else 0.0)),
            domain=domain,
            producer_pipeline=producer_pipeline,
            validation_status=validation_status,
            usage_count=existing.metadata.usage_count if existing else 0,
            last_accessed=existing.metadata.last_accessed if existing else None,
        )

        asset = DataAsset(
            asset_id=dataset_name,
            name=dataset_name,
            asset_type="table",
            location=location,
            metadata=metadata,
        )
        self._upsert_asset(asset)
        self._log_event(
            "metadata_catalog.dataset_upserted",
            dataset_name=dataset_name,
            domain=domain,
            producer_pipeline=producer_pipeline,
            validation_status=validation_status,
        )
        return asset

    def get_asset(self, asset_id: str) -> Optional[DataAsset]:
        """Get asset by ID/dataset_name."""
        with self.lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT * FROM datasets WHERE dataset_name = ?", (asset_id,)
                ).fetchone()
                return self._row_to_asset(row) if row else None
            finally:
                conn.close()

    def get_dataset(self, dataset_name: str) -> Optional[Dict[str, Any]]:
        """Get dataset metadata as dictionary."""
        asset = self.get_asset(dataset_name)
        if asset is None:
            return None

        consumers = self._get_consumers(dataset_name)
        lineage = self._get_lineage(dataset_name)
        result = asset.metadata.to_dict()
        result["consumers"] = consumers
        result["upstream_datasets"] = lineage["upstream_datasets"]
        result["downstream_datasets"] = lineage["downstream_datasets"]
        return result

    def update_asset_metadata(self, asset_id: str, metadata: DatasetMetadata) -> bool:
        """Update asset metadata (compatibility method)."""
        existing = self.get_asset(asset_id)
        if existing is None:
            self._log_event("metadata_catalog.asset_not_found", dataset_name=asset_id)
            return False

        metadata.updated_at = datetime.now()
        existing.metadata = metadata
        self._upsert_asset(existing)
        self._log_event("metadata_catalog.asset_updated", dataset_name=asset_id)
        return True

    @staticmethod
    def _build_relationship_key(relationship: Dict[str, Any]) -> str:
        left_dataset = str(relationship.get("left_dataset", ""))
        right_dataset = str(relationship.get("right_dataset", ""))
        left_column = str(relationship.get("left_column", ""))
        right_column = str(relationship.get("right_column", ""))
        return f"{left_dataset}:{left_column}->{right_dataset}:{right_column}"

    @staticmethod
    def _history_entry(relationship: Dict[str, Any], timestamp: str) -> Dict[str, Any]:
        return {
            "timestamp": timestamp,
            "confidence": float(relationship.get("confidence", 0.0)),
            "decision": str(relationship.get("decision", "weak")),
            "cardinality": str(relationship.get("cardinality", "unknown")),
            "model_version": str(relationship.get("model_version", "unknown")),
            "feature_vector_version": str(relationship.get("feature_vector_version", "unknown")),
        }

    def upsert_inferred_relationship(
        self,
        dataset_name: str,
        relationship: Dict[str, Any],
        counterpart_dataset: Optional[str] = None,
    ) -> bool:
        """Insert or update an inferred relationship with timestamped history.

        Stored per dataset under:
        metadata.properties['inferred_relationships']
        """
        asset = self.get_asset(dataset_name)
        if asset is None:
            self._log_event(
                "metadata_catalog.relationship_upsert_skipped",
                dataset_name=dataset_name,
                reason="asset_not_found",
            )
            return False

        metadata = asset.metadata
        records = list(metadata.properties.get("inferred_relationships", []))

        now = datetime.now().isoformat()
        dedup_key = str(relationship.get("relationship_key") or self._build_relationship_key(relationship))
        history_item = self._history_entry(relationship, now)

        index = next(
            (i for i, item in enumerate(records) if str(item.get("relationship_key", "")) == dedup_key),
            -1,
        )

        if index >= 0:
            existing = dict(records[index])
            history = list(existing.get("history", []))
            history.append(history_item)

            existing.update(
                {
                    "left_dataset": relationship.get("left_dataset"),
                    "right_dataset": relationship.get("right_dataset"),
                    "left_column": relationship.get("left_column"),
                    "right_column": relationship.get("right_column"),
                    "confidence": float(relationship.get("confidence", 0.0)),
                    "decision": str(relationship.get("decision", "weak")),
                    "cardinality": str(relationship.get("cardinality", "unknown")),
                    "model_version": str(relationship.get("model_version", "unknown")),
                    "feature_vector_version": str(relationship.get("feature_vector_version", "unknown")),
                    "feature_vector": relationship.get("feature_vector", {}),
                    "counterpart_dataset": counterpart_dataset or existing.get("counterpart_dataset"),
                    "history": history,
                    "last_scored_at": now,
                }
            )
            records[index] = existing
            action = "updated"
            relationship_id = str(existing.get("relationship_id", ""))
        else:
            record = {
                "relationship_id": str(uuid.uuid4()),
                "relationship_key": dedup_key,
                "left_dataset": relationship.get("left_dataset"),
                "right_dataset": relationship.get("right_dataset"),
                "left_column": relationship.get("left_column"),
                "right_column": relationship.get("right_column"),
                "confidence": float(relationship.get("confidence", 0.0)),
                "decision": str(relationship.get("decision", "weak")),
                "cardinality": str(relationship.get("cardinality", "unknown")),
                "model_version": str(relationship.get("model_version", "unknown")),
                "feature_vector_version": str(relationship.get("feature_vector_version", "unknown")),
                "feature_vector": relationship.get("feature_vector", {}),
                "counterpart_dataset": counterpart_dataset,
                "history": [history_item],
                "created_at": now,
                "last_scored_at": now,
            }
            records.append(record)
            action = "created"
            relationship_id = record["relationship_id"]

        metadata.properties = {
            **metadata.properties,
            "inferred_relationships": records,
            "inferred_relationships_last_updated": now,
            "last_updated": now,
        }
        metadata.updated_at = datetime.now()

        updated = self.update_asset_metadata(dataset_name, metadata)
        if updated:
            self._log_event(
                "metadata_catalog.relationship_upserted",
                dataset_name=dataset_name,
                relationship_id=relationship_id,
                relationship_key=dedup_key,
                action=action,
                decision=str(relationship.get("decision", "weak")),
                confidence=float(relationship.get("confidence", 0.0)),
            )
        return updated

    def get_inferred_relationships(
        self,
        dataset_name: str,
        decision_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return inferred relationships for a dataset from metadata properties."""
        asset = self.get_asset(dataset_name)
        if asset is None:
            return []

        records = list(asset.metadata.properties.get("inferred_relationships", []))
        if decision_filter is None:
            return records

        decision_norm = str(decision_filter).lower()
        return [
            record
            for record in records
            if str(record.get("decision", "")).lower() == decision_norm
        ]

    def get_relationship_history(
        self,
        dataset_name: str,
        relationship_key: str,
    ) -> List[Dict[str, Any]]:
        """Return timestamped history for one relationship."""
        relationships = self.get_inferred_relationships(dataset_name)
        for record in relationships:
            if str(record.get("relationship_key", "")) == relationship_key:
                return list(record.get("history", []))
        return []

    def analyze_relationship_drift(
        self,
        dataset_name: str,
        relationship_key: str,
    ) -> Dict[str, Any]:
        """Simple confidence/decision drift summary from history."""
        history = self.get_relationship_history(dataset_name, relationship_key)
        if len(history) < 2:
            return {
                "relationship_key": relationship_key,
                "has_drift": False,
                "reason": "insufficient_history",
                "history_points": len(history),
            }

        first = history[0]
        last = history[-1]
        first_conf = float(first.get("confidence", 0.0))
        last_conf = float(last.get("confidence", 0.0))
        confidence_delta = last_conf - first_conf
        decision_changed = str(first.get("decision", "")) != str(last.get("decision", ""))

        return {
            "relationship_key": relationship_key,
            "has_drift": bool(abs(confidence_delta) >= 0.05 or decision_changed),
            "history_points": len(history),
            "first_timestamp": first.get("timestamp"),
            "last_timestamp": last.get("timestamp"),
            "first_confidence": first_conf,
            "last_confidence": last_conf,
            "confidence_delta": confidence_delta,
            "first_decision": first.get("decision"),
            "last_decision": last.get("decision"),
            "decision_changed": decision_changed,
        }

    def list_assets(
        self,
        asset_type: Optional[str] = None,
        access_level: Optional[str] = None,
    ) -> List[DataAsset]:
        """List assets with optional filtering."""
        where = []
        params: List[Any] = []
        if asset_type:
            where.append("asset_type = ?")
            params.append(asset_type)
        if access_level:
            where.append("access_level = ?")
            params.append(access_level)

        query = "SELECT * FROM datasets"
        if where:
            query += " WHERE " + " AND ".join(where)
        query += " ORDER BY dataset_name"

        with self.lock:
            conn = self._connect()
            try:
                rows = conn.execute(query, params).fetchall()
                return [self._row_to_asset(row) for row in rows]
            finally:
                conn.close()

    def search_by_name(self, pattern: str) -> List[DataAsset]:
        """Search assets by name pattern."""
        like_pattern = f"%{pattern.lower()}%"
        with self.lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT * FROM datasets WHERE LOWER(dataset_name) LIKE ? ORDER BY dataset_name",
                    (like_pattern,),
                ).fetchall()
                return [self._row_to_asset(row) for row in rows]
            finally:
                conn.close()

    def search_by_tag(self, tag: str) -> List[DataAsset]:
        """Search assets by tag."""
        tag_lower = tag.lower()
        matched: List[DataAsset] = []
        for asset in self.list_assets():
            tags_lower = [t.lower() for t in asset.metadata.tags]
            if tag_lower in tags_lower:
                matched.append(asset)
        return matched

    def search_by_owner(self, owner: str) -> List[DataAsset]:
        """Search assets by owner."""
        with self.lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT * FROM datasets WHERE owner = ? ORDER BY dataset_name",
                    (owner,),
                ).fetchall()
                return [self._row_to_asset(row) for row in rows]
            finally:
                conn.close()

    def get_datasets_by_domain(self, domain: str) -> List[Dict[str, Any]]:
        """Get datasets for a business domain."""
        with self.lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT dataset_name FROM datasets WHERE domain = ? ORDER BY dataset_name",
                    (domain,),
                ).fetchall()
            finally:
                conn.close()
        return [self.get_dataset(row["dataset_name"]) for row in rows]

    def get_datasets_by_producer(self, producer_pipeline: str) -> List[Dict[str, Any]]:
        """Get datasets produced by a specific pipeline."""
        with self.lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT dataset_name FROM datasets WHERE producer_pipeline = ? ORDER BY dataset_name",
                    (producer_pipeline,),
                ).fetchall()
            finally:
                conn.close()
        return [self.get_dataset(row["dataset_name"]) for row in rows]

    def _get_consumers(self, dataset_name: str) -> List[str]:
        with self.lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT consumer_name FROM dataset_consumers WHERE dataset_name = ? ORDER BY consumer_name",
                    (dataset_name,),
                ).fetchall()
                return [row["consumer_name"] for row in rows]
            finally:
                conn.close()

    def get_datasets_by_consumer(self, consumer_name: str) -> List[Dict[str, Any]]:
        """Get datasets used by a specific consumer (model/dashboard/pipeline)."""
        with self.lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT dataset_name FROM dataset_consumers WHERE consumer_name = ? ORDER BY dataset_name",
                    (consumer_name,),
                ).fetchall()
            finally:
                conn.close()
        return [self.get_dataset(row["dataset_name"]) for row in rows]

    def track_consumer_access(self, dataset_name: str, consumer_name: str) -> bool:
        """Track consumer usage (automated monitoring)."""
        now = datetime.now().isoformat()
        with self.lock:
            conn = self._connect()
            try:
                exists = conn.execute(
                    "SELECT 1 FROM datasets WHERE dataset_name = ?", (dataset_name,)
                ).fetchone()
                if not exists:
                    self._log_event(
                        "metadata_catalog.consumer_tracking_skipped",
                        dataset_name=dataset_name,
                        consumer_name=consumer_name,
                        reason="dataset_not_found",
                    )
                    return False

                conn.execute(
                    """
                    INSERT INTO dataset_consumers (dataset_name, consumer_name, usage_count, last_accessed)
                    VALUES (?, ?, 1, ?)
                    ON CONFLICT(dataset_name, consumer_name) DO UPDATE SET
                        usage_count = usage_count + 1,
                        last_accessed = excluded.last_accessed
                    """,
                    (dataset_name, consumer_name, now),
                )

                conn.execute(
                    """
                    UPDATE datasets
                    SET usage_count = usage_count + 1,
                        last_accessed = ?,
                        last_updated = ?
                    WHERE dataset_name = ?
                    """,
                    (now, now, dataset_name),
                )
                conn.commit()
            finally:
                conn.close()

        self._log_event(
            "metadata_catalog.consumer_tracked",
            dataset_name=dataset_name,
            consumer_name=consumer_name,
            last_accessed=now,
        )
        return True

    def load_dataset_with_tracking(
        self,
        dataset_name: str,
        consumer_name: str,
        loader_fn: Optional[Callable[[str], Any]] = None,
    ) -> Any:
        """Wrapped dataset loader that automatically updates usage monitoring."""
        self.track_consumer_access(dataset_name=dataset_name, consumer_name=consumer_name)
        if loader_fn is None:
            return self.get_dataset(dataset_name)
        return loader_fn(dataset_name)

    def register_lineage(self, input_datasets: List[str], output_dataset: str) -> None:
        """Register lineage edges from upstream input datasets to output dataset."""
        now = datetime.now().isoformat()
        with self.lock:
            conn = self._connect()
            try:
                for upstream in input_datasets:
                    conn.execute(
                        """
                        INSERT INTO lineage (upstream_dataset, downstream_dataset, created_at)
                        VALUES (?, ?, ?)
                        ON CONFLICT(upstream_dataset, downstream_dataset) DO NOTHING
                        """,
                        (upstream, output_dataset, now),
                    )
                conn.commit()
            finally:
                conn.close()

        self._log_event(
            "metadata_catalog.lineage_registered",
            output_dataset=output_dataset,
            upstream_count=len(input_datasets),
        )

    def _get_lineage(self, dataset_name: str) -> Dict[str, List[str]]:
        with self.lock:
            conn = self._connect()
            try:
                upstream = conn.execute(
                    "SELECT upstream_dataset FROM lineage WHERE downstream_dataset = ? ORDER BY upstream_dataset",
                    (dataset_name,),
                ).fetchall()
                downstream = conn.execute(
                    "SELECT downstream_dataset FROM lineage WHERE upstream_dataset = ? ORDER BY downstream_dataset",
                    (dataset_name,),
                ).fetchall()
            finally:
                conn.close()

        return {
            "upstream_datasets": [row["upstream_dataset"] for row in upstream],
            "downstream_datasets": [row["downstream_dataset"] for row in downstream],
        }

    def get_downstream_dependencies(self, dataset_name: str) -> List[str]:
        """Return transitive downstream dependency list (impact analysis)."""
        visited = set()
        queue = [dataset_name]
        while queue:
            current = queue.pop(0)
            lineage = self._get_lineage(current)
            for child in lineage["downstream_datasets"]:
                if child not in visited:
                    visited.add(child)
                    queue.append(child)
        return sorted(list(visited))

    def list_stale_datasets(self, threshold_days: int) -> List[Dict[str, Any]]:
        """List datasets not updated within threshold_days."""
        cutoff = (datetime.now() - timedelta(days=threshold_days)).isoformat()
        with self.lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT dataset_name FROM datasets WHERE last_updated < ? ORDER BY dataset_name",
                    (cutoff,),
                ).fetchall()
            finally:
                conn.close()
        return [self.get_dataset(row["dataset_name"]) for row in rows]

    def list_failed_validation_datasets(self) -> List[Dict[str, Any]]:
        """List datasets with failed validation."""
        with self.lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    """
                    SELECT dataset_name
                    FROM datasets
                    WHERE LOWER(validation_status) = 'failed'
                    ORDER BY dataset_name
                    """
                ).fetchall()
            finally:
                conn.close()
        return [self.get_dataset(row["dataset_name"]) for row in rows]

    def _compute_dataset_health(self, dataset: Dict[str, Any], stale_days: int) -> str:
        """Compute per-dataset health state."""
        last_updated = self._from_iso(dataset.get("last_updated"))
        is_stale = bool(last_updated and last_updated < (datetime.now() - timedelta(days=stale_days)))
        validation_status = str(dataset.get("validation_status", "warning")).lower()
        quality_score = float(dataset.get("quality_score") or 0.0)

        if is_stale:
            return "Stale"
        if validation_status == "failed" or quality_score < 50:
            return "Failed"
        if validation_status == "warning" or quality_score < 80:
            return "Warning"
        return "Healthy"

    def generate_catalog_health_report(self, stale_threshold_days: int = 30) -> Dict[str, Any]:
        """Generate catalog-wide health summary."""
        datasets = [self.get_dataset(asset.asset_id) for asset in self.list_assets()]
        datasets = [d for d in datasets if d is not None]

        health_counts = {"Healthy": 0, "Warning": 0, "Failed": 0, "Stale": 0}
        detailed = []
        for dataset in datasets:
            health = self._compute_dataset_health(dataset, stale_days=stale_threshold_days)
            health_counts[health] += 1
            detailed.append({
                "dataset_name": dataset["dataset_name"],
                "health": health,
                "validation_status": dataset.get("validation_status"),
                "quality_score": dataset.get("quality_score"),
                "last_updated": dataset.get("last_updated"),
            })

        return {
            "generated_at": datetime.now().isoformat(),
            "total_datasets": len(datasets),
            "health_counts": health_counts,
            "stale_threshold_days": stale_threshold_days,
            "datasets": sorted(detailed, key=lambda item: (item["health"], item["dataset_name"])),
        }

    def export_catalog_summary(self, output_path: Optional[str] = None) -> Dict[str, Any]:
        """Export catalog summary dictionary and optionally write JSON file."""
        datasets = [self.get_dataset(asset.asset_id) for asset in self.list_assets()]
        datasets = [d for d in datasets if d is not None]
        summary = {
            "exported_at": datetime.now().isoformat(),
            "total_assets": len(datasets),
            "datasets": datasets,
            "health": self.generate_catalog_health_report(),
        }

        if output_path:
            out = Path(output_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
            self._log_event("metadata_catalog.summary_exported", output_path=str(out), total_assets=len(datasets))

        return summary

    def get_statistics(self) -> Dict[str, Any]:
        """Get catalog statistics (compatibility method)."""
        assets = self.list_assets()
        total_rows = sum(asset.metadata.row_count for asset in assets)
        avg_quality = (
            sum(asset.metadata.quality_score for asset in assets) / len(assets)
            if assets else 0.0
        )
        by_type: Dict[str, int] = {}
        by_access: Dict[str, int] = {}
        for asset in assets:
            by_type[asset.asset_type] = by_type.get(asset.asset_type, 0) + 1
            by_access[asset.access_level] = by_access.get(asset.access_level, 0) + 1

        return {
            "total_assets": len(assets),
            "assets_by_type": by_type,
            "assets_by_access_level": by_access,
            "total_rows": total_rows,
            "avg_quality_score": avg_quality,
        }
