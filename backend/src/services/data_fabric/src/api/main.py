"""API main application."""

from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import asdict
import json
import math
import shutil
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
import pandas as pd

from configs.settings import get_settings
from .routes import ingestion, preprocessing, validation, metadata, ml, health
from .middleware import AuthMiddleware
from src.metadata.catalog import MetadataCatalog

logger = logging.getLogger(__name__)

settings = get_settings()


def _data_fabric_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _agent_last_run_path() -> Path:
    return _data_fabric_root() / "processed-data" / "agent_last_run.json"


def _json_safe(value: Any) -> Any:
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


def _load_catalog() -> MetadataCatalog:
    db_path = _data_fabric_root() / "src" / "metadata" / "metadata_catalog.db"
    return MetadataCatalog(db_path=str(db_path))


def _normalize_relationship(record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "relationship_key": str(record.get("relationship_key", "")),
        "left_dataset": str(record.get("left_dataset", "")),
        "right_dataset": str(record.get("right_dataset", "")),
        "left_column": str(record.get("left_column", "")),
        "right_column": str(record.get("right_column", "")),
        "confidence": float(record.get("confidence", 0.0)),
        "decision": str(record.get("decision", "weak")),
        "cardinality": str(record.get("cardinality", "unknown")),
        "model_version": str(record.get("model_version", "unknown")),
        "feature_vector_version": str(record.get("feature_vector_version", "unknown")),
        "feature_vector": record.get("feature_vector", {}),
        "counterpart_dataset": record.get("counterpart_dataset"),
        "is_unstable": bool(record.get("is_unstable", False)),
        "drift_score": float(record.get("drift_score", 0.0)),
        "join_usage_count": int(record.get("join_usage_count", 0)),
        "last_scored_at": record.get("last_scored_at"),
        "last_used_at": record.get("last_used_at"),
        "history_points": len(list(record.get("history", []))),
    }


def _collect_unique_relationships(catalog: MetadataCatalog) -> List[Dict[str, Any]]:
    seen = set()
    rows: List[Dict[str, Any]] = []
    for asset in catalog.list_assets(asset_type="table"):
        for rel in catalog.get_inferred_relationships(asset.name):
            key = str(rel.get("relationship_key", "")).strip()
            if not key or key in seen:
                continue
            seen.add(key)
            rows.append(dict(rel))
    return rows


def _merge_candidates(
    catalog: MetadataCatalog,
    limit: Optional[int] = None,
    include_reason: bool = False,
) -> List[Dict[str, Any]]:
    pair_best: Dict[str, Dict[str, Any]] = {}
    rel_by_key: Dict[str, Dict[str, Any]] = {}
    for rel in _collect_unique_relationships(catalog):
        relationship_key = str(rel.get("relationship_key", "")).strip()
        if relationship_key:
            rel_by_key[relationship_key] = rel

        left = str(rel.get("left_dataset", "")).strip()
        right = str(rel.get("right_dataset", "")).strip()
        if not left or not right or left == right:
            continue
        a, b = (left, right) if left < right else (right, left)
        pair_key = f"{a}::{b}"
        confidence = float(rel.get("confidence", 0.0))
        current = pair_best.get(pair_key)
        if current is None or confidence > float(current.get("best_confidence", 0.0)):
            pair_best[pair_key] = {
                "left_dataset": a,
                "right_dataset": b,
                "best_confidence": confidence,
                "best_decision": str(rel.get("decision", "weak")),
                "relationship_key": relationship_key,
            }

    candidates = sorted(pair_best.values(), key=lambda x: float(x.get("best_confidence", 0.0)), reverse=True)
    if isinstance(limit, int) and limit > 0:
        candidates = candidates[:limit]

    if include_reason:
        for candidate in candidates:
            rel = rel_by_key.get(str(candidate.get("relationship_key", "")), {})
            fv = dict(rel.get("feature_vector", {}) or {})
            name_similarity = float(fv.get("name_similarity", rel.get("name_similarity", 0.0)) or 0.0)
            overlap_ratio = float(fv.get("overlap_ratio", rel.get("overlap_ratio", 0.0)) or 0.0)
            type_score = float(fv.get("type_score", rel.get("type_score", 0.0)) or 0.0)
            candidate["signals"] = {
                "name_similarity": round(name_similarity, 4),
                "overlap_ratio": round(overlap_ratio, 4),
                "type_score": round(type_score, 4),
                "confidence_source": str(fv.get("confidence_source", "unknown")),
            }
            candidate["reason"] = (
                f"name_similarity={name_similarity:.3f}, overlap_ratio={overlap_ratio:.3f}, type_score={type_score:.3f}"
            )

    return candidates


def _compute_drift_changes(catalog: MetadataCatalog, limit: int = 5) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for rel in _collect_unique_relationships(catalog):
        history = list(rel.get("history", []))
        if len(history) < 2:
            continue

        before = float(history[-2].get("confidence", 0.0))
        after = float(history[-1].get("confidence", 0.0))
        delta = after - before
        rows.append(
            {
                "relationship_key": str(rel.get("relationship_key", "")),
                "left_dataset": str(rel.get("left_dataset", "")),
                "right_dataset": str(rel.get("right_dataset", "")),
                "left_column": str(rel.get("left_column", "")),
                "right_column": str(rel.get("right_column", "")),
                "before_confidence": before,
                "after_confidence": after,
                "delta": delta,
                "abs_delta": abs(delta),
                "decision": str(rel.get("decision", "weak")),
                "drift_score": float(rel.get("drift_score", 0.0)),
                "last_scored_at": rel.get("last_scored_at"),
            }
        )

    rows.sort(key=lambda item: float(item.get("abs_delta", 0.0)), reverse=True)
    return rows[: max(1, int(limit))]


def _save_agent_last_run(source: str, report: Dict[str, Any]) -> None:
    path = _agent_last_run_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": source,
        "saved_at": pd.Timestamp.utcnow().isoformat(),
        "report": report,
    }
    path.write_text(json.dumps(_json_safe(payload), indent=2), encoding="utf-8")


def _load_agent_last_run() -> Optional[Dict[str, Any]]:
    path = _agent_last_run_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _read_table_for_dataset(catalog: MetadataCatalog, dataset_name: str) -> pd.DataFrame:
    asset = catalog.get_asset(dataset_name)
    file_path = None
    if asset is not None:
        file_path = asset.location
        if not file_path and asset.metadata.properties:
            file_path = asset.metadata.properties.get("file_path")

    if file_path and str(file_path).startswith("virtual://"):
        file_path = None

    candidate_paths: List[Path] = []
    if file_path:
        candidate_paths.append(Path(file_path))

    raw_path = _data_fabric_root() / "data" / "raw" / f"{dataset_name}.csv"
    candidate_paths.append(raw_path)

    for path in candidate_paths:
        if not path.exists() or not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix == ".csv":
            return pd.read_csv(path)
        if suffix in {".tsv", ".txt"}:
            return pd.read_csv(path, sep="\t")
        if suffix in {".xls", ".xlsx"}:
            return pd.read_excel(path)
        if suffix == ".json":
            return pd.read_json(path)

    raise FileNotFoundError(f"No readable source file found for dataset '{dataset_name}'")


def _load_tabular_file(file_path: Path) -> pd.DataFrame:
    suffix = file_path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(file_path)
    if suffix in {".tsv", ".txt"}:
        return pd.read_csv(file_path, sep="\t")
    if suffix in {".xls", ".xlsx"}:
        return pd.read_excel(file_path)
    if suffix == ".json":
        return pd.read_json(file_path)
    raise HTTPException(status_code=400, detail=f"Unsupported file type: {file_path.suffix}")


def _run_data_fabric_intake(
    file_path: Path,
    dataset_name: Optional[str],
    auto_join_if_single: bool,
    how: str,
    max_reference_datasets: Optional[int] = None,
) -> Dict[str, Any]:
    from src.integration.autonomous_agent import AutonomousIntegrationAgent
    from src.integration.virtual_integration import VirtualIntegrationLayer

    intake_dataset = (dataset_name or file_path.stem).strip()
    if not intake_dataset:
        raise HTTPException(status_code=400, detail="dataset_name could not be determined")

    df_new = _load_tabular_file(file_path)
    schema = {str(col): str(dtype) for col, dtype in df_new.dtypes.items()}
    catalog = _load_catalog()

    catalog.upsert_dataset(
        dataset_name=intake_dataset,
        domain="unknown",
        schema=schema,
        row_count=int(len(df_new)),
        producer_pipeline="integration.autonomous_intake",
        validation_status="warning",
        quality_score=0.0,
        description=f"Intake dataset from {file_path.name}",
        owner="integration",
        source_system=file_path.suffix.lstrip(".") or "file",
        location=str(file_path),
        tags=["intake"],
        properties={
            "file_path": str(file_path),
            "loaded_at": pd.Timestamp.utcnow().isoformat(),
            "last_updated": pd.Timestamp.utcnow().isoformat(),
            "producer_pipeline": "integration.autonomous_intake",
        },
    )

    datasets: Dict[str, pd.DataFrame] = {intake_dataset: df_new}
    existing_assets = [a.name for a in catalog.list_assets(asset_type="table") if a.name != intake_dataset]
    if isinstance(max_reference_datasets, int) and max_reference_datasets > 0:
        existing_assets = existing_assets[:max_reference_datasets]

    for name in existing_assets:
        try:
            datasets[name] = _read_table_for_dataset(catalog, name)
        except Exception:
            continue

    integration = VirtualIntegrationLayer(metadata_catalog=catalog)
    if len(datasets) >= 2:
        integration.infer_relationships(datasets=datasets, register_results=True)

    raw_suggestions = catalog.get_inferred_relationships(intake_dataset)
    suggestions = [_normalize_relationship(row) for row in raw_suggestions]
    suggestions.sort(key=lambda item: float(item.get("confidence", 0.0)), reverse=True)

    good_matches = [s for s in suggestions if str(s.get("decision", "weak")).lower() != "weak"]
    bad_matches = [s for s in suggestions if str(s.get("decision", "weak")).lower() == "weak"]

    why_joined = ""
    why_not_auto_joined = ""
    join_rows: Optional[int] = None
    join_preview: List[Dict[str, Any]] = []
    selected_relationship: Optional[Dict[str, Any]] = None

    if auto_join_if_single and len(good_matches) == 1:
        selected_relationship = good_matches[0]
        left_name = str(selected_relationship.get("left_dataset", "")).strip()
        right_name = str(selected_relationship.get("right_dataset", "")).strip()

        try:
            if left_name in datasets and right_name in datasets:
                joined_df, rel = integration.join_on_demand(
                    datasets=datasets,
                    left_dataset=left_name,
                    right_dataset=right_name,
                    how=how,
                    selected_relationship_key=str(selected_relationship.get("relationship_key", "")),
                    allow_weak_relationship=False,
                )
                join_rows = int(len(joined_df))
                join_preview = joined_df.head(25).replace({pd.NA: None}).to_dict(orient="records")
                why_joined = (
                    f"Auto-joined {left_name} and {right_name} using "
                    f"{rel.left_column}->{rel.right_column} (confidence={float(rel.confidence):.3f}, decision={rel.decision})."
                )
            else:
                why_not_auto_joined = "Unable to auto-join: source data for one of the selected datasets is unavailable."
        except Exception as exc:
            why_not_auto_joined = f"Auto-join skipped due to execution error: {exc}"
    elif auto_join_if_single and len(good_matches) == 0:
        why_not_auto_joined = "No non-weak relationship candidates were found."
    elif auto_join_if_single and len(good_matches) > 1:
        why_not_auto_joined = "Multiple non-weak candidates found; manual confirmation is required."

    agent = AutonomousIntegrationAgent(metadata_catalog=catalog)
    report = asdict(agent.run_once())
    _save_agent_last_run(source="intake", report=report)

    return _json_safe(
        {
            "status": "ok",
            "dataset_name": intake_dataset,
            "good_match_count": len(good_matches),
            "bad_match_count": len(bad_matches),
            "why_joined": why_joined,
            "why_not_auto_joined": why_not_auto_joined,
            "selected_relationship": selected_relationship,
            "selected_signals": {
                str(s.get("relationship_key", "")): dict(s.get("feature_vector", {}) or {})
                for s in suggestions[:10]
            },
            "join_rows": join_rows,
            "join_preview": join_preview,
            "suggestions": suggestions[:20],
            "agent_updates": {
                "usage_updates": 0,
                "behavioral_updates": int(report.get("behavioral_updates", 0)),
                "drift_flags": int(report.get("drift_flags", 0)),
            },
        }
    )


def create_app() -> FastAPI:
    """Create and configure FastAPI application.

    Returns:
        Configured FastAPI app
    """
    app = FastAPI(
        title=settings.api_title,
        version="1.0.0",
        description="Data Fabric RESTful API Service",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routes
    app.include_router(health.router, prefix="/api/health", tags=["Health"])
    app.include_router(ingestion.router, prefix="/api/ingestion", tags=["Ingestion"])
    app.include_router(preprocessing.router, prefix="/api/preprocessing", tags=["Preprocessing"])
    app.include_router(validation.router, prefix="/api/validation", tags=["Validation"])
    app.include_router(metadata.router, prefix="/api/metadata", tags=["Metadata"])
    app.include_router(ml.router, prefix="/api/ml", tags=["ML"])

    # Global exception handler
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request, exc):
        """Handle HTTP exceptions."""
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.detail},
        )

    @app.on_event("startup")
    async def startup_event():
        """Startup event."""
        logger.info("Data Fabric API starting up")

    @app.on_event("shutdown")
    async def shutdown_event():
        """Shutdown event."""
        logger.info("Data Fabric API shutting down")

    @app.get("/api/data-fabric/overview")
    async def data_fabric_overview():
        """Dashboard overview from metadata catalog."""
        catalog = _load_catalog()
        assets = catalog.list_assets(asset_type="table")

        datasets: List[Dict[str, Any]] = []
        relationships: List[Dict[str, Any]] = []
        seen_relationship_keys = set()

        for asset in assets:
            md = asset.metadata
            datasets.append(
                {
                    "dataset_name": asset.name,
                    "row_count": int(md.row_count),
                    "column_count": int(md.column_count),
                    "domain": str(md.domain),
                    "quality_score": float(md.quality_score),
                    "updated_at": md.updated_at.isoformat(),
                    "usage_count": int(md.usage_count),
                    "location": asset.location,
                }
            )

            for rel in catalog.get_inferred_relationships(asset.name):
                key = str(rel.get("relationship_key", ""))
                if not key or key in seen_relationship_keys:
                    continue
                seen_relationship_keys.add(key)
                relationships.append(_normalize_relationship(rel))

        relationships.sort(key=lambda item: float(item.get("confidence", 0.0)), reverse=True)

        decision_counts = {"strong": 0, "probable": 0, "weak": 0}
        unstable_count = 0
        for rel in relationships:
            decision = str(rel.get("decision", "weak")).lower()
            if decision in decision_counts:
                decision_counts[decision] += 1
            if rel.get("is_unstable"):
                unstable_count += 1

        metrics_path = _data_fabric_root() / "models" / "relationship_metrics_v1.json"
        metrics: Dict[str, Any] = {}
        if metrics_path.exists():
            try:
                metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
            except Exception:
                metrics = {}

        model_info = {
            "model_mode": "ensemble",
            "model_version": str(relationships[0].get("model_version", "unknown")) if relationships else "unknown",
            "feature_vector_version": str(relationships[0].get("feature_vector_version", "unknown")) if relationships else "unknown",
            "ensemble_ready": False,
            "ensemble_reason": "Standalone API running metadata-driven overview.",
            "lr_loaded": False,
            "secondary_model_loaded": False,
            "secondary_model_label": "RF",
            "lr_weight": 0.3,
            "secondary_weight": 0.7,
            "test_metrics": {},
        }

        return _json_safe(
            {
                "kpis": {
                    "dataset_count": len(datasets),
                    "relationship_count": len(relationships),
                    "strong_count": decision_counts["strong"],
                    "probable_count": decision_counts["probable"],
                    "weak_count": decision_counts["weak"],
                    "unstable_count": unstable_count,
                },
                "model": model_info,
                "datasets": sorted(datasets, key=lambda item: item["dataset_name"]),
                "relationships": relationships,
                "metrics": metrics,
                "last_refreshed": pd.Timestamp.utcnow().isoformat(),
            }
        )

    @app.get("/api/data-fabric/lineage")
    async def data_fabric_lineage():
        """Lineage graph from metadata catalog relationships."""
        catalog = _load_catalog()
        assets = catalog.list_assets(asset_type="table")

        nodes = [
            {
                "id": asset.name,
                "label": asset.name,
                "domain": str(asset.metadata.domain),
                "quality_score": float(asset.metadata.quality_score),
            }
            for asset in assets
        ]

        edges_set = set()
        edges: List[Dict[str, str]] = []
        for rel in _collect_unique_relationships(catalog):
            left = str(rel.get("left_dataset", "")).strip()
            right = str(rel.get("right_dataset", "")).strip()
            if not left or not right:
                continue
            key = (left, right)
            if key in edges_set:
                continue
            edges_set.add(key)
            edges.append({"source": left, "target": right})

        return {
            "nodes": sorted(nodes, key=lambda n: n["id"]),
            "edges": sorted(edges, key=lambda e: (e["source"], e["target"])),
            "merge_candidates": _merge_candidates(catalog),
        }

    @app.get("/api/data-fabric/logs")
    async def data_fabric_logs(limit: int = 200):
        """Operational logs synthesized from relationship score history."""
        catalog = _load_catalog()
        events: List[Dict[str, Any]] = []
        seen = set()

        for asset in catalog.list_assets(asset_type="table"):
            for rel in catalog.get_inferred_relationships(asset.name):
                key = str(rel.get("relationship_key", ""))
                if not key or key in seen:
                    continue
                seen.add(key)

                history = list(rel.get("history", []))
                for item in history:
                    events.append(
                        {
                            "timestamp": item.get("timestamp"),
                            "event": "relationship_scored",
                            "dataset_pair": f"{rel.get('left_dataset')}:{rel.get('right_dataset')}",
                            "relationship_key": key,
                            "confidence": float(item.get("confidence", 0.0)),
                            "decision": str(item.get("decision", "weak")),
                        }
                    )

                if rel.get("is_unstable"):
                    events.append(
                        {
                            "timestamp": rel.get("last_scored_at"),
                            "event": "relationship_unstable",
                            "dataset_pair": f"{rel.get('left_dataset')}:{rel.get('right_dataset')}",
                            "relationship_key": key,
                            "confidence": float(rel.get("confidence", 0.0)),
                            "decision": str(rel.get("decision", "weak")),
                            "drift_score": float(rel.get("drift_score", 0.0)),
                        }
                    )

        events.sort(key=lambda e: str(e.get("timestamp", "")), reverse=True)
        return {"events": events[: max(1, min(int(limit), 1000))]}

    @app.get("/api/data-fabric/join-options")
    async def data_fabric_join_options(left_dataset: str, right_dataset: str):
        """Return ranked relationship suggestions and intervention mode for a dataset pair."""
        catalog = _load_catalog()
        records = catalog.get_inferred_relationships(left_dataset)

        suggestions = [
            _normalize_relationship(r)
            for r in records
            if {str(r.get("left_dataset", "")), str(r.get("right_dataset", ""))}
            == {left_dataset, right_dataset}
        ]
        suggestions.sort(key=lambda item: float(item.get("confidence", 0.0)), reverse=True)

        non_weak = [s for s in suggestions if str(s.get("decision", "weak")).lower() != "weak"]
        if not suggestions:
            mode = "no_relationship"
        elif len(non_weak) > 1:
            mode = "manual_required_multiple"
        elif len(non_weak) == 1:
            mode = "auto_ready"
        else:
            mode = "manual_required_weak"

        return {
            "left_dataset": left_dataset,
            "right_dataset": right_dataset,
            "mode": mode,
            "suggestions": suggestions,
        }

    @app.get("/api/data-fabric/agent/status")
    async def data_fabric_agent_status():
        """Return panel-facing transparency status for the autonomous integration agent."""
        catalog = _load_catalog()
        relationships = _collect_unique_relationships(catalog)

        ensemble_count = 0
        static_count = 0
        behavioral_updates = 0
        for rel in relationships:
            fv = dict(rel.get("feature_vector", {}) or {})
            models_used = dict(fv.get("models_used", {}) or {})
            has_lr = isinstance(models_used.get("LR"), (int, float))
            has_secondary = any(k != "LR" and isinstance(v, (int, float)) for k, v in models_used.items())
            if has_lr and has_secondary:
                ensemble_count += 1
            else:
                static_count += 1
            if isinstance(fv.get("behavioral_updated_at"), str):
                behavioral_updates += 1

        return _json_safe(
            {
                "agent_active": behavioral_updates > 0,
                "last_run": _load_agent_last_run(),
                "coverage": {
                    "ensemble": ensemble_count,
                    "static": static_count,
                    "behavioral_updates": behavioral_updates,
                    "total_relationships": len(relationships),
                },
                "drift_changes": _compute_drift_changes(catalog, limit=5),
                "merge_suggestions": _merge_candidates(catalog, limit=5, include_reason=True),
                "generated_at": pd.Timestamp.utcnow().isoformat(),
            }
        )

    @app.post("/api/data-fabric/agent/run-now")
    async def data_fabric_agent_run_now(request: Request):
        """Run autonomous agent immediately and persist last-run report."""
        from src.integration.autonomous_agent import AutonomousIntegrationAgent

        source = "manual"
        try:
            body = await request.json()
            source = str(body.get("source", source)).strip() or source
        except Exception:
            pass

        catalog = _load_catalog()
        agent = AutonomousIntegrationAgent(metadata_catalog=catalog)
        report = asdict(agent.run_once())
        _save_agent_last_run(source=source, report=report)

        return _json_safe(
            {
                "status": "ok",
                "source": source,
                "report": report,
                "saved_at": pd.Timestamp.utcnow().isoformat(),
            }
        )

    @app.post("/api/data-fabric/intake")
    async def data_fabric_intake(request: Request):
        """Process newly arrived file by path, infer relationships, and optionally auto-join."""
        body = await request.json()
        file_path_raw = str(body.get("file_path", "")).strip()
        dataset_name = str(body.get("dataset_name", "")).strip() or None
        auto_join_if_single = bool(body.get("auto_join_if_single", True))
        how = str(body.get("how", "inner"))
        max_reference_datasets = body.get("max_reference_datasets")

        if not file_path_raw:
            raise HTTPException(status_code=400, detail="file_path is required")

        file_path = Path(file_path_raw)
        if not file_path.exists() or not file_path.is_file():
            raise HTTPException(status_code=404, detail=f"File not found: {file_path_raw}")

        return _run_data_fabric_intake(
            file_path=file_path,
            dataset_name=dataset_name,
            auto_join_if_single=auto_join_if_single,
            how=how,
            max_reference_datasets=(int(max_reference_datasets) if max_reference_datasets is not None else None),
        )

    @app.post("/api/data-fabric/intake-upload")
    async def data_fabric_intake_upload(
        file: UploadFile = File(...),
        dataset_name: Optional[str] = Form(default=None),
        auto_join_if_single: bool = Form(default=True),
        how: str = Form(default="inner"),
        max_reference_datasets: Optional[int] = Form(default=None),
    ):
        """Process uploaded file for Data Fabric intake workflow (drag/drop or file picker)."""
        upload_dir = _data_fabric_root() / "data" / "raw" / "intake_uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)

        original = Path(file.filename or "uploaded_file.csv")
        safe_name = f"{uuid4().hex}_{original.name}"
        saved_path = upload_dir / safe_name

        with saved_path.open("wb") as output:
            shutil.copyfileobj(file.file, output)

        return _run_data_fabric_intake(
            file_path=saved_path,
            dataset_name=(dataset_name or "").strip() or original.stem,
            auto_join_if_single=auto_join_if_single,
            how=how,
            max_reference_datasets=max_reference_datasets,
        )

    return app


app = create_app()
