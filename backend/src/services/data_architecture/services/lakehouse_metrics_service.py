"""Lakehouse metrics service for Azure Blob-backed observability APIs.

This module centralizes medallion analytics (bronze/silver/gold), storage usage,
ingestion behavior, data freshness, and seasonal tiering insights. It is designed
for API consumption only, so frontend clients never query Azure directly.
"""

from __future__ import annotations

import json
import mimetypes
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


DATA_EXTENSIONS = {".csv", ".parquet", ".json"}


class LakehouseMetricsService:
    """Compute operational lakehouse metrics from Azure Blob or local medallion files."""

    def __init__(self, base_dir: str, connection_string: Optional[str] = None) -> None:
        self.base_dir = os.path.abspath(base_dir)
        self.connection_string = connection_string or self._load_connection_string()

        self.layer_dirs: Dict[str, List[str]] = {
            "bronze": [os.path.join(self.base_dir, "medallions", "bronze")],
            "silver": [os.path.join(self.base_dir, "medallions", "silver")],
            "gold": [os.path.join(self.base_dir, "medallions", "gold")],
        }
        self.container_names = {"bronze": "bronze", "silver": "silver", "gold": "gold"}

        self._blob_service_client = None
        self._azure_error: Optional[str] = None
        if self.connection_string:
            try:
                from azure.storage.blob import BlobServiceClient  # type: ignore

                self._blob_service_client = BlobServiceClient.from_connection_string(self.connection_string)
            except Exception as exc:
                self._azure_error = str(exc)

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------

    def get_bronze_metrics(self) -> Dict[str, Any]:
        bronze_files, source, azure_error = self._list_layer_files("bronze")

        total_size = sum(item["file_size"] for item in bronze_files)
        latest_ts = self._latest_timestamp(bronze_files)
        today = datetime.now(timezone.utc).date()

        daily_groups: Dict[str, Dict[str, int]] = defaultdict(lambda: {"files": 0, "size_bytes": 0})
        files_ingested_today = 0

        for item in bronze_files:
            modified = item.get("last_modified_dt")
            if not isinstance(modified, datetime):
                continue
            day_key = modified.date().isoformat()
            daily_groups[day_key]["files"] += 1
            daily_groups[day_key]["size_bytes"] += int(item.get("file_size", 0) or 0)
            if modified.date() == today:
                files_ingested_today += 1

        daily_breakdown = [
            {
                "date": day,
                "files": values["files"],
                "size_bytes": values["size_bytes"],
            }
            for day, values in sorted(daily_groups.items())
        ]

        return {
            "source": source,
            "azure_error": azure_error,
            "bronze_file_count": len(bronze_files),
            "bronze_storage_bytes": total_size,
            "bronze_storage_gb": self._to_gb(total_size),
            "files_ingested_today": files_ingested_today,
            "latest_ingestion_timestamp": latest_ts,
            "daily_ingestion_file_counts": daily_breakdown,
        }

    def get_silver_metrics(self) -> Dict[str, Any]:
        silver_files, silver_source, silver_error = self._list_layer_files("silver")
        bronze_files, _, _ = self._list_layer_files("bronze")

        silver_datasets = sorted({item.get("dataset_name") or item.get("file_name") for item in silver_files})

        bronze_records = sum(int(item.get("records", 0) or 0) for item in bronze_files)
        silver_records = sum(int(item.get("records", 0) or 0) for item in silver_files)

        if bronze_records > 0:
            transformation_success_rate = round(min(100.0, (silver_records / bronze_records) * 100.0), 2)
        else:
            transformation_success_rate = 100.0 if silver_records > 0 else 0.0

        transformation_timestamps = sorted(
            {
                item.get("last_modified")
                for item in silver_files
                if item.get("last_modified")
            }
        )

        return {
            "source": silver_source,
            "azure_error": silver_error,
            "silver_dataset_count": len(silver_datasets),
            "transformation_timestamps": transformation_timestamps[-100:],
            "transformation_success_rate": transformation_success_rate,
            "bronze_record_estimate": bronze_records,
            "silver_record_estimate": silver_records,
        }

    def get_gold_metrics(self) -> Dict[str, Any]:
        gold_files, source, azure_error = self._list_layer_files("gold")

        analytical_tables = 0
        feature_datasets = 0
        stakeholder_views = 0

        for item in gold_files:
            dataset_label = f"{item.get('dataset_name', '')} {item.get('blob_path', '')}".lower()
            if any(token in dataset_label for token in ("stakeholder", "view", "dashboard")):
                stakeholder_views += 1
            elif any(token in dataset_label for token in ("feature", "embedding", "ml_", "model")):
                feature_datasets += 1
            else:
                analytical_tables += 1

        return {
            "source": source,
            "azure_error": azure_error,
            "gold_file_count": len(gold_files),
            "analytical_tables_count": analytical_tables,
            "feature_datasets_count": feature_datasets,
            "stakeholder_views_generated": stakeholder_views,
        }

    def get_storage_analytics(self, include_largest: bool = True) -> Dict[str, Any]:
        files_by_layer = self._collect_all_layers()
        all_files = files_by_layer["bronze"] + files_by_layer["silver"] + files_by_layer["gold"]

        tier_groups: Dict[str, Dict[str, int]] = defaultdict(lambda: {"size_bytes": 0, "file_count": 0})
        total_size = 0

        for item in all_files:
            size = int(item.get("file_size", 0) or 0)
            total_size += size
            tier = self._normalize_tier_name(item.get("access_tier"))
            tier_groups[tier]["size_bytes"] += size
            tier_groups[tier]["file_count"] += 1

        tier_usage = [
            {
                "tier": tier,
                "size_bytes": values["size_bytes"],
                "size_gb": self._to_gb(values["size_bytes"]),
                "file_count": values["file_count"],
            }
            for tier, values in sorted(tier_groups.items())
        ]

        response: Dict[str, Any] = {
            "source_by_layer": files_by_layer["source_by_layer"],
            "azure_errors": files_by_layer["azure_errors"],
            "total_size_bytes": total_size,
            "total_size_gb": self._to_gb(total_size),
            "tier_usage": tier_usage,
        }

        if include_largest:
            response["largest_datasets"] = self._largest_datasets(all_files, limit=10)

        return response

    def get_storage_growth(self) -> Dict[str, Any]:
        files_by_layer = self._collect_all_layers()
        all_files = files_by_layer["bronze"] + files_by_layer["silver"] + files_by_layer["gold"]

        daily_sizes: Dict[str, Dict[str, int]] = defaultdict(lambda: {"size_bytes": 0, "file_count": 0})

        for item in all_files:
            modified = item.get("last_modified_dt")
            if not isinstance(modified, datetime):
                continue
            day_key = modified.date().isoformat()
            daily_sizes[day_key]["size_bytes"] += int(item.get("file_size", 0) or 0)
            daily_sizes[day_key]["file_count"] += 1

        points = [
            {
                "date": day,
                "size_bytes": values["size_bytes"],
                "size_gb": self._to_gb(values["size_bytes"]),
                "file_count": values["file_count"],
            }
            for day, values in sorted(daily_sizes.items())
        ]

        return {
            "source_by_layer": files_by_layer["source_by_layer"],
            "azure_errors": files_by_layer["azure_errors"],
            "points": points,
        }

    def get_ingestion_metrics(self) -> Dict[str, Any]:
        bronze_files, source, azure_error = self._list_layer_files("bronze")

        per_minute: Dict[str, int] = defaultdict(int)
        per_hour: Dict[str, int] = defaultdict(int)
        per_day: Dict[str, int] = defaultdict(int)

        for item in bronze_files:
            modified = item.get("last_modified_dt")
            if not isinstance(modified, datetime):
                continue

            records = int(item.get("records", 0) or 0)
            minute_key = modified.strftime("%Y-%m-%d %H:%M")
            hour_key = modified.strftime("%Y-%m-%d %H:00")
            day_key = modified.strftime("%Y-%m-%d")

            per_minute[minute_key] += records
            per_hour[hour_key] += records
            per_day[day_key] += records

        records_per_minute = [
            {"timestamp": ts, "records": value}
            for ts, value in sorted(per_minute.items())[-180:]
        ]
        records_per_hour = [
            {"timestamp": ts, "records": value}
            for ts, value in sorted(per_hour.items())[-168:]
        ]
        records_per_day = [
            {"date": day, "records": value}
            for day, value in sorted(per_day.items())[-90:]
        ]

        return {
            "source": source,
            "azure_error": azure_error,
            "records_ingested_per_minute": records_per_minute,
            "records_ingested_per_hour": records_per_hour,
            "records_ingested_per_day": records_per_day,
        }

    def get_data_freshness(self) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        freshness = []

        for layer in ("bronze", "silver", "gold"):
            files, source, azure_error = self._list_layer_files(layer)
            latest_dt = self._latest_datetime(files)
            age_hours = None
            if latest_dt is not None:
                age_hours = round((now - latest_dt).total_seconds() / 3600.0, 2)

            freshness.append(
                {
                    "layer": layer,
                    "latest_update": self._iso(latest_dt),
                    "freshness_hours": age_hours,
                    "file_count": len(files),
                    "source": source,
                    "azure_error": azure_error,
                }
            )

        return {
            "generated_at": self._iso(now),
            "layers": freshness,
        }

    def get_current_season(self, simulate_season: Optional[str] = None) -> Dict[str, str]:
        season = self._resolve_season(simulate_season)
        return {"current_season": season}

    def get_seasonal_storage_analytics(self, simulate_season: Optional[str] = None) -> Dict[str, Any]:
        season = self._resolve_season(simulate_season)
        files_by_layer = self._collect_all_layers()
        all_files = files_by_layer["bronze"] + files_by_layer["silver"] + files_by_layer["gold"]

        seasonal_files = [
            item for item in all_files if self._matches_requested_season(item.get("season_tag"), season)
        ]

        tier_totals = {"HOT": 0, "WARM": 0, "COLD": 0}
        dataset_groups: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {
                "dataset": "",
                "size_bytes": 0,
                "tier": "UNKNOWN",
                "layer": "",
                "latest_modified": "",
            }
        )

        for item in seasonal_files:
            tier = self._normalize_tier_name(item.get("access_tier"))
            size = int(item.get("file_size", 0) or 0)
            if tier in tier_totals:
                tier_totals[tier] += size

            dataset_name = str(item.get("dataset_name") or item.get("file_name") or "unknown")
            group = dataset_groups[dataset_name]
            group["dataset"] = dataset_name
            group["size_bytes"] += size
            group["tier"] = tier
            group["layer"] = str(item.get("layer") or "")
            modified = str(item.get("last_modified") or "")
            if modified > group["latest_modified"]:
                group["latest_modified"] = modified

        dataset_activity = sorted(dataset_groups.values(), key=lambda row: row["size_bytes"], reverse=True)[:10]
        for row in dataset_activity:
            row["size_gb"] = self._to_gb(int(row["size_bytes"]))

        return {
            "current_season": season,
            "seasonal_mode": True,
            "source_by_layer": files_by_layer["source_by_layer"],
            "azure_errors": files_by_layer["azure_errors"],
            "dataset_count": len(seasonal_files),
            "hot_storage_bytes": tier_totals["HOT"],
            "warm_storage_bytes": tier_totals["WARM"],
            "cold_storage_bytes": tier_totals["COLD"],
            "hot_storage_gb": self._to_gb(tier_totals["HOT"]),
            "warm_storage_gb": self._to_gb(tier_totals["WARM"]),
            "cold_storage_gb": self._to_gb(tier_totals["COLD"]),
            "storage_distribution": [
                {"tier": "HOT", "size_bytes": tier_totals["HOT"], "size_gb": self._to_gb(tier_totals["HOT"])},
                {"tier": "WARM", "size_bytes": tier_totals["WARM"], "size_gb": self._to_gb(tier_totals["WARM"])},
                {"tier": "COLD", "size_bytes": tier_totals["COLD"], "size_gb": self._to_gb(tier_totals["COLD"])},
            ],
            "dataset_activity": dataset_activity,
            "highlighted_datasets": [row["dataset"] for row in dataset_activity[:5]],
            "optimization_insight": (
                f"{season} datasets are prioritized for lower latency analytics, and seasonal tiers"
                " are reflected in Hot/Warm/Cold usage."
            ),
        }

    # ---------------------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------------------

    def _collect_all_layers(self) -> Dict[str, Any]:
        source_by_layer: Dict[str, str] = {}
        azure_errors: Dict[str, Optional[str]] = {}
        files_by_layer: Dict[str, List[Dict[str, Any]]] = {}

        for layer in ("bronze", "silver", "gold"):
            files, source, error = self._list_layer_files(layer)
            files_by_layer[layer] = files
            source_by_layer[layer] = source
            azure_errors[layer] = error

        files_by_layer["source_by_layer"] = source_by_layer  # type: ignore[index]
        files_by_layer["azure_errors"] = azure_errors  # type: ignore[index]
        return files_by_layer

    def _list_layer_files(self, layer: str) -> Tuple[List[Dict[str, Any]], str, Optional[str]]:
        # Try local files first for development/testing, then Azure
        local_files = list(self._iter_local_layer_files(layer))
        if local_files:
            return local_files, "local_filesystem", None

        # Fallback to Azure if local files not found
        azure_files, azure_status, azure_error = self._list_azure_layer_blobs(layer)
        if azure_status == "success":
            return azure_files, "azure_blob", None

        # Return empty list if both fail
        return [], "unavailable", azure_error

    def _list_azure_layer_blobs(
        self,
        layer: str,
    ) -> Tuple[List[Dict[str, Any]], str, Optional[str]]:
        if self._blob_service_client is None:
            return [], "unavailable", self._azure_error

        container_name = self.container_names.get(layer, layer)
        try:
            container_client = self._blob_service_client.get_container_client(container_name)
            blobs = container_client.list_blobs(include=["metadata"])

            files: List[Dict[str, Any]] = []
            for blob in blobs:
                blob_name = str(getattr(blob, "name", "") or "")
                if not blob_name or blob_name.endswith("/"):
                    continue

                extension = Path(blob_name).suffix.lower()
                if extension not in DATA_EXTENSIONS:
                    continue

                metadata = dict(getattr(blob, "metadata", {}) or {})
                last_modified = self._parse_datetime(getattr(blob, "last_modified", None))
                size = int(getattr(blob, "size", 0) or 0)
                access_tier = (
                    getattr(blob, "blob_tier", None)
                    or getattr(blob, "access_tier", None)
                    or metadata.get("access_tier")
                    or "Hot"
                )

                content_type = None
                content_settings = getattr(blob, "content_settings", None)
                if content_settings is not None:
                    content_type = getattr(content_settings, "content_type", None)
                if not content_type:
                    content_type = mimetypes.guess_type(blob_name)[0] or "application/octet-stream"

                season_tag = self._infer_season_tag(blob_name, blob_name, metadata)
                records = self._extract_record_estimate(metadata, size, blob_name)

                files.append(
                    {
                        "layer": layer,
                        "file_name": Path(blob_name).name,
                        "dataset_name": Path(blob_name).stem,
                        "blob_path": blob_name,
                        "file_size": size,
                        "last_modified": self._iso(last_modified),
                        "last_modified_dt": last_modified,
                        "access_tier": str(access_tier),
                        "content_type": content_type,
                        "records": records,
                        "metadata": metadata,
                        "season_tag": season_tag,
                    }
                )

            return files, "success", None
        except Exception as exc:
            return [], "error", str(exc)

    def _iter_local_layer_files(self, layer: str) -> Iterable[Dict[str, Any]]:
        directories = self.layer_dirs.get(layer, [])
        now = datetime.now(timezone.utc)

        for directory in directories:
            if not os.path.exists(directory):
                continue

            for root, _, file_names in os.walk(directory):
                for file_name in file_names:
                    extension = Path(file_name).suffix.lower()
                    if extension not in DATA_EXTENSIONS:
                        continue

                    full_path = os.path.join(root, file_name)
                    if not os.path.isfile(full_path):
                        continue

                    try:
                        size = int(os.path.getsize(full_path))
                        modified_dt = datetime.fromtimestamp(os.path.getmtime(full_path), tz=timezone.utc)
                    except OSError:
                        continue

                    rel_path = os.path.relpath(full_path, self.base_dir).replace("\\", "/")
                    season_tag = self._infer_season_tag(file_name, rel_path, None)
                    yield {
                        "layer": layer,
                        "file_name": file_name,
                        "dataset_name": Path(file_name).stem,
                        "blob_path": rel_path,
                        "file_size": size,
                        "last_modified": self._iso(modified_dt),
                        "last_modified_dt": modified_dt,
                        "access_tier": self._derive_local_tier(modified_dt, now=now),
                        "content_type": mimetypes.guess_type(file_name)[0] or "application/octet-stream",
                        "records": self._estimate_local_record_count(full_path, extension, size),
                        "metadata": {"season": season_tag} if season_tag else {},
                        "season_tag": season_tag,
                    }

    def _estimate_local_record_count(self, file_path: str, extension: str, size_bytes: int) -> int:
        if extension == ".csv":
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as handle:
                    lines = sum(1 for _ in handle)
                return max(lines - 1, 0)
            except Exception:
                pass

        if extension == ".json":
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as handle:
                    payload = json.load(handle)
                if isinstance(payload, list):
                    return len(payload)
                if isinstance(payload, dict):
                    return 1
            except Exception:
                pass

        return max(1, size_bytes // 1024)

    def _extract_record_estimate(self, metadata: Dict[str, Any], size_bytes: int, name: str) -> int:
        for key in ("records", "record_count", "rows", "row_count"):
            raw_value = metadata.get(key)
            if raw_value is None:
                continue
            try:
                value = int(raw_value)
                if value >= 0:
                    return value
            except Exception:
                continue

        extension = Path(name).suffix.lower()
        if extension == ".json":
            return max(1, size_bytes // 2048)

        return max(1, size_bytes // 1024)

    def _latest_datetime(self, files: List[Dict[str, Any]]) -> Optional[datetime]:
        timestamps = [
            value
            for value in (item.get("last_modified_dt") for item in files)
            if isinstance(value, datetime)
        ]
        if not timestamps:
            return None
        return max(timestamps)

    def _latest_timestamp(self, files: List[Dict[str, Any]]) -> Optional[str]:
        latest_dt = self._latest_datetime(files)
        return self._iso(latest_dt)

    def _largest_datasets(self, files: List[Dict[str, Any]], limit: int = 10) -> List[Dict[str, Any]]:
        rows = sorted(files, key=lambda item: int(item.get("file_size", 0) or 0), reverse=True)[:limit]
        return [
            {
                "dataset": item.get("dataset_name"),
                "file_name": item.get("file_name"),
                "path": item.get("blob_path"),
                "layer": item.get("layer"),
                "size_bytes": int(item.get("file_size", 0) or 0),
                "size_gb": self._to_gb(int(item.get("file_size", 0) or 0)),
                "access_tier": self._normalize_tier_name(item.get("access_tier")),
                "last_modified": item.get("last_modified"),
            }
            for item in rows
        ]

    def _load_connection_string(self) -> Optional[str]:
        conn_str = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
        if conn_str:
            return conn_str

        candidate_env_files = [
            os.path.join(self.base_dir, ".env"),
            os.path.join(os.path.dirname(self.base_dir), ".env"),
        ]

        for env_path in candidate_env_files:
            if not os.path.exists(env_path):
                continue
            try:
                with open(env_path, "r", encoding="utf-8") as handle:
                    for raw_line in handle:
                        line = raw_line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        key, value = line.split("=", 1)
                        if key.strip() == "AZURE_STORAGE_CONNECTION_STRING":
                            return value.strip().strip('"').strip("'")
            except Exception:
                continue

        return None

    def _resolve_season(self, simulated: Optional[str] = None) -> str:
        """Resolve current season for Sri Lankan fashion retail context."""
        if simulated:
            normalized = simulated.strip().lower()
            # Sri Lankan retail seasons
            mapping = {
                "festive": "Festive",
                "monsoon": "Monsoon",
                "dry": "Dry",
                "historical": "Historical",
                # Legacy support
                "avurudu": "Festive",
                "newyear": "Festive",
            }
            if normalized in mapping:
                return mapping[normalized]
            return simulated.strip().title()

        # Determine Sri Lankan season based on month
        month = datetime.now(timezone.utc).month
        # Festive Season: January, April, December (Avurudu/New Year)
        if month in (1, 4, 12):
            return "Festive"
        # Monsoon Season: May-September
        if 5 <= month <= 9:
            return "Monsoon"
        # Dry Season: February-March, October-November
        return "Dry"

    def _matches_requested_season(self, season_tag: Optional[str], requested_season: str) -> bool:
        if not season_tag:
            return False

        tag = season_tag.strip().lower()
        requested = requested_season.strip().lower()

        # Sri Lankan season aliases
        aliases = {
            "festive": {"festive", "avurudu", "newyear", "celebration", "festival"},
            "monsoon": {"monsoon", "rainy", "wet"},
            "dry": {"dry", "summer", "hot"},
            "historical": {"historical", "archive", "past", "legacy"},
        }

        valid_tags = aliases.get(requested, {requested})
        return any(token in tag for token in valid_tags)

    def _infer_season_tag(
        self,
        file_name: str,
        path_hint: str,
        metadata: Optional[Dict[str, Any]],
    ) -> Optional[str]:
        """Infer season tag from file metadata for Sri Lankan retail context."""
        metadata = metadata or {}
        for key in ("season", "season_tag", "seasonality"):
            value = metadata.get(key)
            if value:
                return str(value).strip().lower()

        combined = f"{file_name} {path_hint}".lower()
        # Check for Sri Lankan season keywords
        for token in ("festive", "avurudu", "newyear", "monsoon", "rainy", "dry", "historical"):
            if token in combined:
                return token

        return None

    def _normalize_tier_name(self, tier: Optional[str]) -> str:
        normalized = str(tier or "").strip().upper()
        if normalized == "HOT":
            return "HOT"
        if normalized in {"COOL", "WARM"}:
            return "WARM"
        if normalized in {"ARCHIVE", "COLD"}:
            return "COLD"
        return "UNKNOWN"

    def _derive_local_tier(self, modified_dt: datetime, now: Optional[datetime] = None) -> str:
        reference = now or datetime.now(timezone.utc)
        age_days = max(0.0, (reference - modified_dt).total_seconds() / 86400.0)
        if age_days <= 14:
            return "HOT"
        if age_days <= 90:
            return "WARM"
        return "COLD"

    def _parse_datetime(self, value: Any) -> Optional[datetime]:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)

        if isinstance(value, str) and value:
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    return parsed.replace(tzinfo=timezone.utc)
                return parsed.astimezone(timezone.utc)
            except Exception:
                return None

        return None

    def _iso(self, value: Optional[datetime]) -> Optional[str]:
        if value is None:
            return None
        return value.astimezone(timezone.utc).isoformat()

    def _to_gb(self, size_bytes: int) -> float:
        return round(float(size_bytes) / (1024.0 ** 3), 4)
