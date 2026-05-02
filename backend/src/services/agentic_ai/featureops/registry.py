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
        run = {
            "run_id": str(payload.get("run_id") or uuid.uuid4().hex[:12]),
            **payload,
        }
        runs.append(run)
        self._write_json(self.drift_runs_path, runs)
        return run

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
