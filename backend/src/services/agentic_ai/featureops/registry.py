from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional


class FeatureOpsDatasetRegistry:
    """File-backed registry for dataset families, versions, drift runs, and release outputs."""

    def __init__(self, root: Path):
        self.root = root
        self.semantic_root = self.root / "semantic_baselines"
        self.root.mkdir(parents=True, exist_ok=True)
        self.semantic_root.mkdir(parents=True, exist_ok=True)
        self.families_path = self.root / "dataset_families.json"
        self.drift_runs_path = self.root / "drift_runs.json"
        self.release_registry_path = self.root / "release_registry.json"

    def _read_json(self, path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default

    def _write_json(self, path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    @staticmethod
    def _slugify(value: str) -> str:
        cleaned = re.sub(r"[^a-z0-9]+", "_", value.strip().lower())
        return cleaned.strip("_") or f"family_{uuid.uuid4().hex[:8]}"

    @staticmethod
    def _dataset_signature(payload: Dict[str, Any]) -> str:
        rows = payload.get("dataset_rows")
        if isinstance(rows, list) and rows:
            normalized_rows = []
            for row in rows:
                if isinstance(row, dict):
                    normalized_row = {}
                    for key in sorted(row.keys(), key=str):
                        value = row.get(key)
                        if value is None:
                            normalized_value = None
                        elif isinstance(value, bool):
                            normalized_value = value
                        elif isinstance(value, (int, float)):
                            normalized_value = str(value)
                        else:
                            normalized_value = str(value).strip()
                        normalized_row[str(key)] = normalized_value
                    normalized_rows.append(normalized_row)
                else:
                    normalized_rows.append(row)
            canonical_rows = sorted(
                json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
                for row in normalized_rows
            )
            return json.dumps(canonical_rows, separators=(",", ":"), ensure_ascii=True)

        fallback = {
            "row_count": payload.get("row_count"),
            "column_count": payload.get("column_count"),
            "column_names": payload.get("column_names") or [],
            "dataset_fingerprint": payload.get("dataset_fingerprint") or {},
        }
        return json.dumps(fallback, sort_keys=True, separators=(",", ":"), ensure_ascii=True)

    def _find_duplicate_version(self, family_id: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        candidate_signature = self._dataset_signature(payload)
        for version in self.list_versions(family_id):
            if self._dataset_signature(version) == candidate_signature:
                return version
        return None

    def list_families(self) -> List[Dict[str, Any]]:
        families = self._read_json(self.families_path, [])
        if not isinstance(families, list):
            return []
        return sorted(
            families,
            key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""),
            reverse=True,
        )

    def get_family(self, family_id: str) -> Optional[Dict[str, Any]]:
        return next((family for family in self.list_families() if family.get("family_id") == family_id), None)

    def get_version_payload(self, family_id: str, version_number: int) -> Optional[Dict[str, Any]]:
        family = self.get_family(family_id)
        if not family:
            return None
        family_slug = self._slugify(str(family.get("family_name") or family_id))
        version_path = self.semantic_root / family_slug / f"v{version_number}.json"
        return self._read_json(version_path, None)

    def save_new_family_baseline(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        families = self.list_families()
        family_name = str(payload.get("family_name") or payload.get("dataset_name") or "Unnamed Dataset Family")
        family_id = self._slugify(family_name)
        if any(str(item.get("family_id")) == family_id for item in families):
            raise ValueError("Dataset family already exists. Add this upload as a new version instead.")
        for family in families:
            duplicate_version = self._find_duplicate_version(str(family.get("family_id") or ""), payload)
            if duplicate_version:
                raise ValueError(
                    "This exact dataset has already been uploaded "
                    f"as {family.get('family_name') or family.get('family_id')} "
                    f"v{duplicate_version.get('version_number')}."
                )
        now = str(payload.get("saved_at") or payload.get("created_at"))
        family = {
            "family_id": family_id,
            "family_name": family_name,
            "created_at": now,
            "updated_at": now,
            "description": str(payload.get("description") or ""),
            "versions": [1],
            "latest_version": 1,
            "approved_baseline_version": 1,
            "version_count": 1,
            "baseline_status": "ACTIVE",
        }
        families.append(family)
        self._write_json(self.families_path, families)

        family_slug = self._slugify(family_name)
        version_path = self.semantic_root / family_slug / "v1.json"
        version_payload = {
            "version_id": f"{family_id}_v1",
            "dataset_family_id": family_id,
            "version_number": 1,
            **payload,
        }
        self._write_json(version_path, version_payload)
        self._append_release_registry(version_payload)
        return family

    def add_version(self, family_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        families = self.list_families()
        family = next((item for item in families if item.get("family_id") == family_id), None)
        if not family:
            raise ValueError("Dataset family not found.")

        duplicate_version = self._find_duplicate_version(family_id, payload)
        if duplicate_version:
            raise ValueError(
                f"This exact dataset has already been uploaded as version v{duplicate_version.get('version_number')}."
            )

        next_version = int(family.get("latest_version") or 0) + 1
        family["latest_version"] = next_version
        family["updated_at"] = str(payload.get("saved_at") or payload.get("created_at") or family.get("updated_at"))
        versions = list(family.get("versions") or [])
        versions.append(next_version)
        family["versions"] = sorted(set(int(value) for value in versions))
        family["version_count"] = len(family["versions"])
        self._write_json(self.families_path, families)

        family_slug = self._slugify(str(family.get("family_name") or family_id))
        version_path = self.semantic_root / family_slug / f"v{next_version}.json"
        version_payload = {
            "version_id": f"{family_id}_v{next_version}",
            "dataset_family_id": family_id,
            "version_number": next_version,
            **payload,
        }
        self._write_json(version_path, version_payload)
        self._append_release_registry(version_payload)
        return {
            "family_id": family_id,
            "family_name": family.get("family_name"),
            "version_number": next_version,
        }

    def list_versions(self, family_id: str) -> List[Dict[str, Any]]:
        family = self.get_family(family_id)
        if not family:
            return []
        versions: List[Dict[str, Any]] = []
        for version_number in family.get("versions") or []:
            payload = self.get_version_payload(family_id, int(version_number))
            if payload:
                versions.append(payload)
        return versions

    def set_approved_baseline(self, family_id: str, version_number: int) -> Dict[str, Any]:
        families = self.list_families()
        family = next((item for item in families if item.get("family_id") == family_id), None)
        if not family:
            raise ValueError("Dataset family not found.")

        if int(version_number) not in [int(value) for value in family.get("versions") or []]:
            raise ValueError("Dataset version not found.")

        family["approved_baseline_version"] = int(version_number)
        family["updated_at"] = family.get("updated_at")
        self._write_json(self.families_path, families)
        return family

    def list_drift_runs(self) -> List[Dict[str, Any]]:
        runs = self._read_json(self.drift_runs_path, [])
        return runs if isinstance(runs, list) else []

    def record_drift_run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        runs = self.list_drift_runs()
        candidate_signature = self._dataset_signature(payload)
        for index, existing in enumerate(runs):
            if self._dataset_signature(existing) != candidate_signature:
                continue

            updated = dict(existing)
            if payload.get("family_id"):
                updated["family_id"] = payload.get("family_id")
            if payload.get("version_id"):
                updated["version_id"] = payload.get("version_id")
            if payload.get("version_number") is not None:
                updated["version_number"] = payload.get("version_number")
            if payload.get("dataset_name"):
                updated["dataset_name"] = payload.get("dataset_name")
            if payload.get("dataset_rows"):
                updated["dataset_rows"] = payload.get("dataset_rows")
            if payload.get("dataset_fingerprint"):
                updated["dataset_fingerprint"] = payload.get("dataset_fingerprint")
            if payload.get("internal_drift_results"):
                updated["internal_drift_results"] = payload.get("internal_drift_results")
            if payload.get("external_drift_results") is not None:
                updated["external_drift_results"] = payload.get("external_drift_results")
            if payload.get("release_results"):
                updated["release_results"] = payload.get("release_results")

            runs[index] = updated
            self._write_json(self.drift_runs_path, runs)
            return updated

        run = {
            "run_id": str(payload.get("run_id") or uuid.uuid4().hex[:12]),
            **payload,
        }
        runs.append(run)
        self._write_json(self.drift_runs_path, runs)
        return run

    def delete_version(self, family_id: str, version_number: int) -> Dict[str, Any]:
        families = self.list_families()
        family = next((item for item in families if item.get("family_id") == family_id), None)
        if not family:
            raise ValueError("Dataset family not found.")

        versions = [int(value) for value in family.get("versions") or []]
        if int(version_number) not in versions:
            raise ValueError("Dataset version not found.")

        family_slug = self._slugify(str(family.get("family_name") or family_id))
        version_path = self.semantic_root / family_slug / f"v{version_number}.json"
        if version_path.exists():
            version_path.unlink()

        remaining_versions = [value for value in versions if value != int(version_number)]
        if not remaining_versions:
            families = [item for item in families if item.get("family_id") != family_id]
            family_dir = self.semantic_root / family_slug
            if family_dir.exists():
                for child in family_dir.glob("*"):
                    if child.is_file():
                        child.unlink()
                try:
                    family_dir.rmdir()
                except OSError:
                    pass
        else:
            family["versions"] = remaining_versions
            family["latest_version"] = max(remaining_versions)
            family["version_count"] = len(remaining_versions)
            approved = int(family.get("approved_baseline_version") or remaining_versions[0])
            family["approved_baseline_version"] = approved if approved in remaining_versions else min(remaining_versions)

        self._write_json(self.families_path, families)

        release_registry = self._read_json(self.release_registry_path, [])
        if isinstance(release_registry, list):
            release_registry = [
                row for row in release_registry
                if not (
                    str(row.get("dataset_family_id")) == family_id
                    and int(row.get("version_number") or -1) == int(version_number)
                )
            ]
            self._write_json(self.release_registry_path, release_registry)

        drift_runs = self.list_drift_runs()
        drift_runs = [
            run for run in drift_runs
            if not (
                str(run.get("family_id") or "") == family_id
                and (
                    str(run.get("version_id") or "") == f"{family_id}_v{version_number}"
                    or int(run.get("version_number") or -1) == int(version_number)
                )
            )
        ]
        self._write_json(self.drift_runs_path, drift_runs)

        return {
            "family_id": family_id,
            "deleted_version": int(version_number),
            "remaining_versions": remaining_versions,
            "family_deleted": not remaining_versions,
        }

    def delete_family(self, family_id: str) -> Dict[str, Any]:
        family = self.get_family(family_id)
        if not family:
            raise ValueError("Dataset family not found.")

        versions = [int(value) for value in family.get("versions") or []]
        family_slug = self._slugify(str(family.get("family_name") or family_id))
        family_dir = self.semantic_root / family_slug
        if family_dir.exists():
            for child in family_dir.glob("*"):
                if child.is_file():
                    child.unlink()
            try:
                family_dir.rmdir()
            except OSError:
                pass

        families = [item for item in self.list_families() if item.get("family_id") != family_id]
        self._write_json(self.families_path, families)

        release_registry = self._read_json(self.release_registry_path, [])
        if isinstance(release_registry, list):
            release_registry = [
                row for row in release_registry
                if str(row.get("dataset_family_id")) != family_id
            ]
            self._write_json(self.release_registry_path, release_registry)

        drift_runs = self.list_drift_runs()
        drift_runs = [
            run for run in drift_runs
            if str(run.get("family_id") or "") != family_id
        ]
        self._write_json(self.drift_runs_path, drift_runs)

        return {
            "family_id": family_id,
            "deleted_versions": versions,
            "family_deleted": True,
        }

    def delete_drift_run(self, run_id: str) -> Dict[str, Any]:
        runs = self.list_drift_runs()
        remaining = [run for run in runs if str(run.get("run_id")) != run_id]
        if len(remaining) == len(runs):
            raise ValueError("Upload history record not found.")
        self._write_json(self.drift_runs_path, remaining)
        return {"run_id": run_id}

    def _append_release_registry(self, payload: Dict[str, Any]) -> None:
        registry = self._read_json(self.release_registry_path, [])
        registry.append(
            {
                "dataset_family_id": payload.get("dataset_family_id"),
                "version_id": payload.get("version_id"),
                "version_number": payload.get("version_number"),
                "dataset_name": payload.get("dataset_name"),
                "created_at": payload.get("created_at"),
                "release_results": payload.get("release_results") or [],
            }
        )
        self._write_json(self.release_registry_path, registry)
