from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import io
import json
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

import pandas as pd
import yaml
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

SYSTEM_DOMAINS = frozenset(
    {
        "sales_domain",
        "users_domain",
        "product_domain",
        "shop_domain",
        "interaction_domain",
        "engagement_domain",
        "user_preferences_domain",
    }
)

# Canonical Silver CSV files retained after demo reset (allowlist — not suffix rules).
CORE_SILVER_CSV_ALLOWLIST = frozenset(
    {
        "interactions_clean.csv",
        "products_clean.csv",
        "shops_clean.csv",
        "transactions_clean.csv",
        "trends_clean.csv",
        "users_clean.csv",
        "users_preferences_clean.csv",
    }
)

# Human-readable labels for policy reason codes (UI / audit).
REASON_CODE_DISPLAY: dict[str, str] = {
    "CONTRACT_FIRST_GOVERNANCE_MATCH": "Contract-first governance match",
    "HYBRID_SCORE_AND_MARGIN_OK": "Hybrid trust score and margin OK",
    "LOW_SCORE_NEW_DOMAIN": "Low fit — new domain candidate",
    "LOW_COMPOSITE_AMBIGUOUS": "Low composite — ambiguous fit",
    "LOW_MARGIN_AMBIGUOUS": "Low leader margin — ambiguous",
    "SCORE_BAND_PROVISIONAL": "Provisional score band",
    "FALLBACK_REVIEW": "Fallback human review",
    "GOVERNANCE_RISK_HIGH": "Governance risk high",
    "NO_CONTRACTS": "No contracts available",
    "CREATED_DOMAIN_REGISTRY": "Created-domain registry routing",
}


@dataclass
class DomainRankParts:
    domain: str
    contract_coverage_score: float
    filename_score: float
    column_score: float
    required_coverage: float
    optional_coverage: float
    matched_columns: list[str]


class SilverToDomainLoaderService:
    """
    Feedback-augmented lexical profile similarity + contract coverage for
    Silver-layer dataset admission into Data Mesh domain products.
    """

    def __init__(self, data_root: Path):
        self.data_root = Path(data_root)
        self.silver_dir = self.data_root / "Data" / "Silver-data"
        self.contracts_dir = self.data_root / "Contracts"
        self.domain_products_dir = self.data_root / "Data_Mesh_Domains"
        self.logs_dir = self.data_root / "monitoring" / "logs"
        self.audit_log_path = self.logs_dir / "silver_domain_loader_audit.json"
        self.domain_memory_path = self.logs_dir / "domain_memory_bank.json"
        self.created_domain_registry_path = self.logs_dir / "created_domain_registry.json"
        self.review_decisions_path = self.logs_dir / "domain_review_decisions.json"
        self.review_tickets_path = self.logs_dir / "domain_review_tickets.json"
        self.materialization_log_path = self.logs_dir / "domain_admission_materialization.json"
        self.demo_manifest_path = self.logs_dir / "demo_loaded_files.json"
        self.test_upload_dir = self.data_root / "Data" / "Test-upload-data"

    def _dataset_origin_for_name(self, dataset_name: str) -> str:
        """CORE = canonical Silver files; DEMO = listed in demo_loaded_files.json manifest; else UPLOADED."""
        name = str(dataset_name or "")
        if name in CORE_SILVER_CSV_ALLOWLIST:
            return "CORE"
        for m in self._read_demo_manifest():
            if isinstance(m, dict) and str(m.get("dataset_name") or "") == name:
                return "DEMO"
        return "UPLOADED"

    def _dataset_origin_display(self, origin: str) -> str:
        return {"CORE": "Core", "DEMO": "Demo", "UPLOADED": "Upload"}.get(str(origin), str(origin or "—"))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def list_silver_datasets(self) -> dict:
        datasets = []
        for csv_path in self._silver_csv_files():
            columns, row_count = self._dataset_schema(csv_path)
            origin = self._dataset_origin_for_name(csv_path.name)
            datasets.append(
                {
                    "dataset_name": csv_path.name,
                    "dataset_origin": origin,
                    "dataset_origin_display": self._dataset_origin_display(origin),
                    "columns": columns,
                    "row_count": row_count,
                    "timestamp": datetime.fromtimestamp(csv_path.stat().st_mtime).isoformat(timespec="seconds"),
                }
            )
        return {"datasets": datasets, "count": len(datasets)}

    def run_domain_detection(self) -> dict:
        run_id = str(uuid.uuid4())[:10]
        timestamp = datetime.now().isoformat(timespec="seconds")
        signatures = self._domain_signatures()
        self._merge_created_domain_signatures(signatures)
        domain_profile_texts = self._build_domain_profile_texts(signatures)
        memory_entries = self._read_memory_bank()

        rows: list[dict] = []
        for csv_path in self._silver_csv_files():
            row = self._evaluate_dataset(
                csv_path=csv_path,
                run_id=run_id,
                timestamp=timestamp,
                signatures=signatures,
                domain_profile_texts=domain_profile_texts,
                memory_entries=memory_entries,
            )
            rows.append(row)

        self._append_audit_rows(rows)
        for row in rows:
            self._enrich_admission_row(row)
        return {"run_id": run_id, "timestamp": timestamp, "results": rows, "count": len(rows)}

    def get_detection_results(self, limit: int = 50) -> dict:
        limit = max(1, min(int(limit), 500))
        all_rows = self._read_audit_rows()
        page = all_rows[:limit]
        for row in page:
            self._enrich_admission_row(row)
        return {"results": page, "count": min(limit, len(all_rows)), "total": len(all_rows)}

    def get_materialization_records(self, limit: int = 200) -> dict[str, Any]:
        limit = max(1, min(int(limit), 1000))
        rows = self._read_materialization_log()
        rows_sorted = sorted(
            [r for r in rows if isinstance(r, dict)],
            key=lambda x: str(x.get("timestamp") or ""),
            reverse=True,
        )
        page = rows_sorted[:limit]
        return {"records": page, "count": len(page), "total": len(rows_sorted)}

    def apply_domain_admission(self, passport_id: str, dataset_name: str, target_domain: str) -> dict[str, Any]:
        pid = str(passport_id or "").strip()
        ds = str(dataset_name or "").strip()
        td_raw = str(target_domain or "").strip()
        if not pid or not ds or not td_raw:
            raise ValueError("passport_id, dataset_name, and target_domain are required.")

        target_norm = self._normalize_domain_name(td_raw)
        source = self.silver_dir / ds
        if not source.is_file():
            raise ValueError(f"Silver dataset not found: {ds}")

        if self._dataset_origin_for_name(ds) == "CORE":
            raise ValueError(
                "Canonical core Silver datasets are already governed by the domain pipeline. "
                "Apply is only for uploads or demo-loaded datasets."
            )

        audit_row = self._find_audit_row_by_passport(pid, ds)
        if not audit_row:
            raise ValueError("No admission record matches this passport_id for the given dataset.")

        best = str(audit_row.get("best_domain") or "")
        best_norm = self._normalize_domain_name(best)
        if best_norm != target_norm:
            # Allow reviewer-approved domain overrides (e.g., CHANGE_DOMAIN).
            if not self._review_allows_materialization(ds, target_norm):
                raise ValueError("target_domain does not match the admission suggestion for this passport.")

        decision = str(audit_row.get("admission_decision") or audit_row.get("action") or "")
        allowed_direct = {"AUTO_LOAD_ELIGIBLE", "AUTO_ASSIGN_CREATED_DOMAIN"}
        if decision not in allowed_direct:
            if not self._review_allows_materialization(ds, target_norm):
                raise ValueError(
                    "This admission requires reviewer approval before loading into a domain product."
                )

        pp = audit_row.get("admission_passport") or {}
        passport_ref = str(pp.get("passport_id") or pid)

        dest_dir = self._resolve_domain_product_dir(target_norm)
        dest_file = dest_dir / f"{target_norm}.csv"
        ts = datetime.now().isoformat(timespec="seconds")
        mid = str(uuid.uuid4())[:14]

        try:
            shutil.copy2(source, dest_file)
            loading_status = "LOADED_TO_DOMAIN"
            message = "Dataset loaded into domain product."
        except OSError as exc:
            loading_status = "LOAD_FAILED"
            message = f"Copy failed: {exc}"
            self._append_materialization_record(
                {
                    "materialization_id": mid,
                    "passport_id": passport_ref,
                    "dataset_name": ds,
                    "source_path": str(source.resolve()),
                    "target_domain": target_norm,
                    "target_path": str(dest_file.resolve()),
                    "loading_status": loading_status,
                    "timestamp": ts,
                    "triggered_by": "dashboard_apply",
                    "error": str(exc),
                }
            )
            raise ValueError(message) from exc

        self._append_materialization_record(
            {
                "materialization_id": mid,
                "passport_id": passport_ref,
                "dataset_name": ds,
                "source_path": str(source.resolve()),
                "target_domain": target_norm,
                "target_path": str(dest_file.resolve()),
                "loading_status": loading_status,
                "timestamp": ts,
                "triggered_by": "dashboard_apply",
            }
        )

        return {
            "success": True,
            "message": message,
            "loading_status": loading_status,
            "target_path": str(dest_file.resolve()),
            "materialization_id": mid,
        }

    def get_domain_memory_bank(self) -> dict:
        entries = self._read_memory_bank()
        by_domain: dict[str, list[dict]] = {}
        for item in entries:
            if not isinstance(item, dict):
                continue
            d = str(item.get("domain_name") or "").strip().lower()
            if not d:
                continue
            by_domain.setdefault(d, []).append(item)

        summary = []
        for domain, items in sorted(by_domain.items()):
            approved = [x for x in items if str(x.get("reviewer_action") or "").upper() in {"APPROVE", "APPROVE_PROVISIONAL", "CHANGE_DOMAIN", "VALIDATE_CANDIDATE", "CREATE_DOMAIN_AFTER_APPROVAL"}]
            latest_ts = max((str(x.get("timestamp") or "") for x in items), default="")
            summary.append(
                {
                    "domain_name": domain,
                    "memory_count": len(items),
                    "approved_dataset_count": len(approved),
                    "latest_memory_update": latest_ts,
                }
            )

        return {"entries": entries, "summary_by_domain": summary, "count": len(entries)}

    def upload_silver_dataset(self, filename: str, raw_bytes: bytes) -> dict:
        name = Path(str(filename or "")).name
        if not name:
            raise ValueError("File name is missing.")
        if not name.lower().endswith(".csv"):
            raise ValueError("Invalid file type. Please upload a .csv file.")
        if not raw_bytes or len(raw_bytes.strip()) == 0:
            raise ValueError("Uploaded file is empty.")

        try:
            df = pd.read_csv(io.BytesIO(raw_bytes))
        except Exception as exc:
            raise ValueError(f"Invalid CSV file: {exc}")

        columns = [str(col).strip() for col in list(df.columns)]
        if not columns or any(col == "" or col.lower().startswith("unnamed:") for col in columns):
            raise ValueError("CSV must include a valid header row with column names.")

        self.silver_dir.mkdir(parents=True, exist_ok=True)
        save_path = self.silver_dir / name
        save_path.write_bytes(raw_bytes)

        return {
            "success": True,
            "message": "Dataset uploaded successfully",
            "dataset_name": name,
            "row_count": int(len(df)),
            "column_count": int(len(columns)),
            "columns": columns,
        }

    def list_demo_source_files(self) -> dict[str, Any]:
        """CSV files available under Data/Test-upload-data for the demo loader."""
        self.test_upload_dir.mkdir(parents=True, exist_ok=True)
        names = sorted({p.name for p in self.test_upload_dir.glob("*.csv") if p.is_file()})
        return {"files": names, "count": len(names), "source_dir": str(self.test_upload_dir.resolve())}

    def load_demo_dataset(self, dataset_name: str, demo_type: str = "demo_load") -> dict[str, Any]:
        """Copy a CSV from Test-upload-data into Silver-data and record the demo manifest."""
        name = Path(str(dataset_name or "")).name
        if not name.lower().endswith(".csv"):
            raise ValueError("dataset_name must be a .csv file.")
        src = self.test_upload_dir / name
        if not src.is_file():
            raise ValueError(f"Demo file not found in Test-upload-data: {name}")

        self.silver_dir.mkdir(parents=True, exist_ok=True)
        dest = self.silver_dir / name
        shutil.copy2(src, dest)
        ts = datetime.now().isoformat(timespec="seconds")
        entry = {
            "dataset_name": name,
            "source_path": str(src.resolve()),
            "target_path": str(dest.resolve()),
            "loaded_at": ts,
            "demo_type": str(demo_type or "demo_load").strip() or "demo_load",
        }
        manifest = self._read_demo_manifest()
        manifest = [m for m in manifest if isinstance(m, dict) and str(m.get("dataset_name")) != name]
        manifest.append(entry)
        self._write_demo_manifest(manifest)

        return {
            "success": True,
            "message": "Demo dataset copied into Silver-data.",
            "dataset_name": name,
            "target_path": str(dest.resolve()),
            "manifest_entry": entry,
        }

    def remove_uploaded_test_files(self) -> dict:
        """Legacy: remove *_test.csv only. Prefer reset_demo_state() allowlist cleanup."""
        self.silver_dir.mkdir(parents=True, exist_ok=True)
        removed: list[str] = []
        for path in self.silver_dir.glob("*_test.csv"):
            if path.is_file():
                path.unlink(missing_ok=True)
                removed.append(path.name)
        return {
            "success": True,
            "message": "Uploaded test files removed from Silver-data.",
            "removed_files": sorted(removed),
            "removed_count": len(removed),
        }

    def clear_detection_history(self) -> dict:
        if self.audit_log_path.exists():
            self.audit_log_path.unlink(missing_ok=True)
        return {"success": True, "message": "Silver-to-domain detection history cleared."}

    def reset_demo_state(self) -> dict[str, Any]:
        """
        Full demo reset: keep only CORE_SILVER_CSV_ALLOWLIST in Silver-data; clear admission logs,
        materialization, memory, review decisions, tickets, demo manifest; retire loader-created domains.
        """
        self.silver_dir.mkdir(parents=True, exist_ok=True)
        removed_files: list[str] = []
        for path in self.silver_dir.glob("*.csv"):
            if path.name not in CORE_SILVER_CSV_ALLOWLIST:
                path.unlink(missing_ok=True)
                removed_files.append(path.name)

        preserved_files = sorted(
            [p.name for p in self.silver_dir.glob("*.csv") if p.is_file() and p.name in CORE_SILVER_CSV_ALLOWLIST]
        )

        cleared_logs: list[str] = []

        def _clear(path: Path, label: str) -> None:
            if path.exists():
                path.unlink(missing_ok=True)
            cleared_logs.append(label)

        _clear(self.audit_log_path, "silver_domain_loader_audit.json")
        _clear(self.materialization_log_path, "domain_admission_materialization.json")
        _clear(self.domain_memory_path, "domain_memory_bank.json")
        _clear(self.review_decisions_path, "domain_review_decisions.json")
        _clear(self.review_tickets_path, "domain_review_tickets.json")
        _clear(self.demo_manifest_path, "demo_loaded_files.json")

        retired_domains = self._retire_loader_created_domains_on_demo_reset()

        return {
            "success": True,
            "message": "Demo state reset successfully",
            "removed_files": sorted(removed_files),
            "preserved_files": preserved_files,
            "cleared_logs": cleared_logs,
            "retired_created_domains": retired_domains,
        }

    def _retire_loader_created_domains_on_demo_reset(self) -> list[str]:
        """Mark non-system loader registry domains DELETED (does not remove contracts or system domains)."""
        reg = self._read_created_registry()
        retired: list[str] = []
        now = datetime.now().isoformat(timespec="seconds")
        for item in reg:
            if not isinstance(item, dict):
                continue
            if item.get("is_system_domain") is True:
                continue
            dom = str(item.get("domain_name") or "").strip().lower()
            if dom and dom in SYSTEM_DOMAINS:
                continue
            if str(item.get("status")) == "ACTIVE":
                item["status"] = "DELETED"
                item["deleted_at"] = now
                item["deleted_reason"] = "demo_reset"
                retired.append(str(item.get("domain_name")))
        self._write_created_registry(reg)
        return retired

    def _read_demo_manifest(self) -> list[dict]:
        if not self.demo_manifest_path.exists():
            return []
        try:
            data = json.loads(self.demo_manifest_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        return data if isinstance(data, list) else []

    def _write_demo_manifest(self, rows: list[dict]) -> None:
        self.demo_manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.demo_manifest_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    def submit_review_decision(self, payload: dict[str, Any]) -> dict:
        dataset_name = str(payload.get("dataset_name") or "").strip()
        detection_run_id = str(payload.get("detection_run_id") or "").strip()
        reviewer_action = str(payload.get("reviewer_action") or "").strip().upper()
        approved_domain = self._normalize_domain_name(str(payload.get("approved_domain") or "").strip())
        candidate_domain_name = str(payload.get("candidate_domain_name") or "").strip()
        reviewer_note = str(payload.get("reviewer_note") or "").strip()

        if not dataset_name:
            raise ValueError("dataset_name is required.")

        csv_path = self.silver_dir / dataset_name
        if not csv_path.is_file():
            raise ValueError(f"Silver dataset not found: {dataset_name}")

        df = pd.read_csv(csv_path)
        cols = [str(c).strip().lower() for c in df.columns]
        dataset_profile_text = self._build_dataset_profile_text(csv_path.name, df, cols)

        decision_type = reviewer_action
        memory_domain = approved_domain or self._normalize_domain_name(candidate_domain_name)

        positive_actions = {
            "APPROVE",
            "APPROVE_PROVISIONAL",
            "CHANGE_DOMAIN",
            "VALIDATE_CANDIDATE",
            "CREATE_DOMAIN_AFTER_APPROVAL",
        }
        negative_actions = {"REJECT", "REJECT_PROVISIONAL", "REJECT_CANDIDATE"}

        if reviewer_action in positive_actions:
            if reviewer_action == "CREATE_DOMAIN_AFTER_APPROVAL":
                target = self._normalize_domain_name(candidate_domain_name or approved_domain)
                if not target:
                    raise ValueError("candidate_domain_name is required for domain creation.")
                if target in SYSTEM_DOMAINS:
                    raise ValueError("Cannot create a domain that conflicts with a system domain name.")
                self._create_domain_folder(target, csv_path)
                self._upsert_created_domain_registry(
                    domain_name=target,
                    source_dataset_name=dataset_name,
                    source_columns=cols,
                    detection_run_id=detection_run_id,
                )
                memory_domain = target

            if memory_domain:
                self._append_memory_bank(
                    {
                        "memory_id": str(uuid.uuid4())[:12],
                        "domain_name": memory_domain,
                        "dataset_name": dataset_name,
                        "dataset_profile_text": dataset_profile_text,
                        "reviewer_action": reviewer_action,
                        "approved_domain": memory_domain,
                        "decision_type": decision_type,
                        "timestamp": datetime.now().isoformat(timespec="seconds"),
                        "source": "review_decision",
                    }
                )

        elif reviewer_action in negative_actions:
            reject_domain = approved_domain or memory_domain or candidate_domain_name
            if not reject_domain:
                reject_domain = str(payload.get("rejected_domain") or "").strip()
            reject_domain = self._normalize_domain_name(reject_domain) if reject_domain else ""
            self._append_memory_bank(
                {
                    "memory_id": str(uuid.uuid4())[:12],
                    "domain_name": reject_domain or "unknown",
                    "dataset_name": dataset_name,
                    "dataset_profile_text": dataset_profile_text,
                    "reviewer_action": "REJECT",
                    "approved_domain": reject_domain or "",
                    "decision_type": decision_type,
                    "timestamp": datetime.now().isoformat(timespec="seconds"),
                    "source": "review_decision",
                }
            )

        ticket_id: str | None = None
        if reviewer_action == "RAISE_TICKET":
            ticket_id = str(uuid.uuid4())[:12]
            self._append_ticket(
                {
                    "ticket_id": ticket_id,
                    "dataset_name": dataset_name,
                    "candidate_domain_name": candidate_domain_name,
                    "reason": reviewer_note or "Governance review requested.",
                    "status": "OPEN",
                    "timestamp": datetime.now().isoformat(timespec="seconds"),
                }
            )

        decision_status = self._review_outcome_status(reviewer_action)
        ts_decision = datetime.now().isoformat(timespec="seconds")
        decision_record = {
            "decision_id": str(uuid.uuid4())[:12],
            "detection_run_id": detection_run_id,
            "dataset_name": dataset_name,
            "reviewer_action": reviewer_action,
            "approved_domain": approved_domain,
            "candidate_domain_name": candidate_domain_name,
            "reviewer_note": reviewer_note,
            "timestamp": ts_decision,
            "decision_status": decision_status,
            "ticket_id": ticket_id,
        }
        self._append_review_decision(decision_record)

        return {
            "success": True,
            "message": "Review decision recorded.",
            "decision": decision_record,
            "decision_status": decision_status,
            "ticket_id": ticket_id,
        }

    def get_review_decisions(self) -> dict:
        if not self.review_decisions_path.exists():
            return {"decisions": [], "count": 0}
        try:
            data = json.loads(self.review_decisions_path.read_text(encoding="utf-8"))
        except Exception:
            return {"decisions": [], "count": 0}
        rows = data if isinstance(data, list) else []
        return {"decisions": rows, "count": len(rows)}

    def list_created_domains(self) -> dict:
        reg = self._read_created_registry()
        active = [x for x in reg if isinstance(x, dict) and str(x.get("status") or "") == "ACTIVE"]
        return {"domains": active, "count": len(active)}

    def delete_created_domain(self, domain_name: str) -> dict:
        normalized = self._normalize_domain_name(domain_name)
        if not normalized:
            raise ValueError("domain_name is required.")
        if normalized in SYSTEM_DOMAINS:
            raise ValueError("System domains cannot be deleted.")

        reg = self._read_created_registry()
        found = False
        for entry in reg:
            if str(entry.get("domain_name") or "").lower() != normalized:
                continue
            if entry.get("is_system_domain") is True:
                raise ValueError("System-marked registry domains cannot be deleted.")
            if entry.get("status") == "ACTIVE":
                entry["status"] = "DELETED"
                entry["deleted_at"] = datetime.now().isoformat(timespec="seconds")
                found = True
        if found:
            self.created_domain_registry_path.parent.mkdir(parents=True, exist_ok=True)
            self.created_domain_registry_path.write_text(json.dumps(reg, indent=2), encoding="utf-8")
        return {"success": True, "message": f"Created domain '{normalized}' marked DELETED in registry.", "domain_name": normalized}

    def _review_outcome_status(self, reviewer_action: str) -> str:
        m = {
            "APPROVE": "APPROVED",
            "APPROVE_PROVISIONAL": "APPROVED",
            "CHANGE_DOMAIN": "CHANGED",
            "REJECT": "REJECTED",
            "REJECT_PROVISIONAL": "REJECTED",
            "REJECT_CANDIDATE": "REJECTED",
            "VALIDATE_CANDIDATE": "APPROVED",
            "CREATE_DOMAIN_AFTER_APPROVAL": "DOMAIN_CREATED",
            "MARK_ORPHAN_CANDIDATE": "ORPHAN_CANDIDATE",
            "RAISE_TICKET": "TICKET_OPENED",
        }
        return m.get(str(reviewer_action or "").strip().upper(), "RECORDED")

    # ------------------------------------------------------------------
    # Core evaluation
    # ------------------------------------------------------------------
    def _fallback_row_no_contracts(
        self,
        csv_path: Path,
        run_id: str,
        timestamp: str,
        columns_detected: list[str],
        df: pd.DataFrame,
    ) -> dict:
        dataset_profile_text = self._build_dataset_profile_text(csv_path.name, df, columns_detected)
        gov = self._governance_risk_preview(df)
        fp_origin = self._dataset_origin_for_name(csv_path.name)
        admission_decision = "GOVERNANCE_TICKET_RECOMMENDED" if gov == "HIGH" else "NEW_DOMAIN_CANDIDATE"
        passport = {
            "passport_id": str(uuid.uuid4())[:12],
            "dataset_name": csv_path.name,
            "dataset_origin": fp_origin,
            "dataset_origin_display": self._dataset_origin_display(fp_origin),
            "dataset_profile_text": dataset_profile_text,
            "suggested_domain": None,
            "semantic_best_domain": None,
            "semantic_similarity_score": 0.0,
            "semantic_similarity_for_suggested_domain": 0.0,
            "contract_coverage_score": 0.0,
            "memory_feedback_score": 0.5,
            "filename_score": 0.0,
            "final_admission_score": 0.0,
            "contract_gate": "FAILED",
            "contract_gate_detail": "No domain contracts available to evaluate column fit.",
            "primary_reason_code": "NO_CONTRACTS",
            "trust_eligibility_note": None,
            "second_best_domain": None,
            "second_best_score": None,
            "semantic_second_best_domain": None,
            "semantic_second_best_score": None,
            "ambiguity_gap": 0.0,
            "matched_memory_entries": [],
            "governance_risk_preview": gov,
            "recommended_action": admission_decision,
            "admission_decision": admission_decision,
            "review_required": True,
            "explanation": "No domain contracts available to score against; admission deferred.",
            "timestamp": timestamp,
            "policy_reason_codes": ["NO_CONTRACTS"],
            "lexical_similarity_note": "Lexical / statistical TF-IDF similarity over profiles (not deep semantic AI).",
            "memory_display_mode": "no_bank",
            "memory_score_for_display": None,
        }
        out_row = {
            "run_id": run_id,
            "dataset_name": csv_path.name,
            "dataset_origin": fp_origin,
            "dataset_origin_display": self._dataset_origin_display(fp_origin),
            "dataset_profile_text": dataset_profile_text,
            "columns_detected": columns_detected,
            "best_domain": None,
            "confidence_score": 0.0,
            "semantic_similarity_score": 0.0,
            "semantic_similarity_for_suggested_domain": 0.0,
            "contract_coverage_score": 0.0,
            "memory_feedback_score": 0.5,
            "filename_score": 0.0,
            "final_admission_score": 0.0,
            "policy_reason_codes": passport.get("policy_reason_codes"),
            "contract_gate": "FAILED",
            "contract_gate_detail": passport.get("contract_gate_detail"),
            "primary_reason_code": "NO_CONTRACTS",
            "trust_eligibility_note": None,
            "second_best_domain": None,
            "second_best_score": None,
            "semantic_best_domain": None,
            "semantic_second_best_domain": None,
            "semantic_second_best_score": None,
            "semantic_ambiguity_gap": 0.0,
            "all_domain_scores": {},
            "all_semantic_scores": {},
            "action": admission_decision,
            "admission_decision": admission_decision,
            "review_required": True,
            "candidate_domain_name": self._candidate_domain_name(csv_path.name, columns_detected, []),
            "final_domain": None,
            "timestamp": timestamp,
            "explanation": passport["explanation"],
            "governance_risk_preview": gov,
            "admission_passport": passport,
            "recommended_action": admission_decision,
            "memory_display_mode": "no_bank",
            "memory_score_for_display": None,
            "memory_signal_active": False,
        }
        self._enrich_admission_row(out_row)
        return out_row

    def _evaluate_dataset(
        self,
        csv_path: Path,
        run_id: str,
        timestamp: str,
        signatures: dict[str, dict[str, set[str]]],
        domain_profile_texts: dict[str, str],
        memory_entries: list[dict],
    ) -> dict:
        df = pd.read_csv(csv_path)
        columns_detected = [str(c).strip().lower() for c in df.columns]
        origin = self._dataset_origin_for_name(csv_path.name)

        created_match = self._match_created_domain_for_dataset(csv_path.name)
        if created_match:
            passport = self._build_created_domain_passport(
                csv_path=csv_path,
                dataset_profile_text=self._build_dataset_profile_text(csv_path.name, df, columns_detected),
                domain_name=created_match["domain_name"],
                timestamp=timestamp,
                registry_entry=created_match,
            )
            dom = created_match["domain_name"]
            return self._audit_row_from_passport(
                run_id=run_id,
                csv_path=csv_path,
                columns_detected=columns_detected,
                passport=passport,
                admission_decision="AUTO_ASSIGN_CREATED_DOMAIN",
                review_required=False,
                candidate_domain_name=None,
                ranked_final={dom: 0.95},
                semantic_sims={dom: 0.95},
                extra_explanation="Assigned via governed created-domain registry and prior approval workflow.",
            )

        ranked_parts = self._rank_domain_contract_parts(csv_path, columns_detected, signatures)
        if not ranked_parts or not domain_profile_texts:
            return self._fallback_row_no_contracts(
                csv_path=csv_path,
                run_id=run_id,
                timestamp=timestamp,
                columns_detected=columns_detected,
                df=df,
            )

        sem_sims = self._semantic_similarities(
            self._build_dataset_profile_text(csv_path.name, df, columns_detected),
            domain_profile_texts,
        )

        memory_by_domain = self._memory_feedback_scores(
            dataset_profile=self._build_dataset_profile_text(csv_path.name, df, columns_detected),
            memory_entries=memory_entries,
            domains=list(domain_profile_texts.keys()),
        )

        final_scores: dict[str, float] = {}
        detail_by_domain: dict[str, dict[str, float]] = {}
        for part in ranked_parts:
            sem = float(sem_sims.get(part.domain, 0.0))
            mem_raw = float(memory_by_domain.get(part.domain, 0.5))
            mem_t = self._memory_for_trust_composite(mem_raw, memory_entries, part.domain)
            fin = (
                0.45 * part.contract_coverage_score
                + 0.25 * sem
                + 0.15 * mem_t
                + 0.15 * part.filename_score
            )
            fin = max(0.0, min(1.0, float(fin)))
            final_scores[part.domain] = fin
            detail_by_domain[part.domain] = {
                "semantic_similarity": sem,
                "contract_coverage_score": part.contract_coverage_score,
                "memory_feedback_score_raw": mem_raw,
                "memory_feedback_score_trust": mem_t,
                "memory_feedback_score": mem_raw,
                "filename_score": part.filename_score,
                "final_admission_score": fin,
            }

        sorted_final = sorted(final_scores.items(), key=lambda x: x[1], reverse=True)
        best_domain = sorted_final[0][0] if sorted_final else None
        second_domain = sorted_final[1][0] if len(sorted_final) > 1 else None
        best_final = sorted_final[0][1] if sorted_final else 0.0
        second_final = sorted_final[1][1] if len(sorted_final) > 1 else 0.0

        sorted_sem = sorted(sem_sims.items(), key=lambda x: x[1], reverse=True)
        sem_best = sorted_sem[0][0] if sorted_sem else None
        sem_best_score = float(sorted_sem[0][1]) if sorted_sem else 0.0
        sem_second = sorted_sem[1][0] if len(sorted_sem) > 1 else None
        sem_second_score = float(sorted_sem[1][1]) if len(sorted_sem) > 1 else 0.0
        sem_gap = max(0.0, sem_best_score - sem_second_score)

        best_parts = next((p for p in ranked_parts if p.domain == best_domain), ranked_parts[0] if ranked_parts else None)
        required_ok = bool(best_parts and best_parts.required_coverage >= 0.35)

        sorted_by_contract = sorted(ranked_parts, key=lambda p: p.contract_coverage_score, reverse=True)
        contract_leader_gap = 1.0
        if len(sorted_by_contract) > 1:
            contract_leader_gap = float(
                sorted_by_contract[0].contract_coverage_score - sorted_by_contract[1].contract_coverage_score
            )

        gov_risk = self._governance_risk_preview(df)

        admission_decision, reason_codes = self._resolve_admission_policy(
            final_score_best=best_final,
            semantic_gap=sem_gap,
            required_coverage_ok=required_ok,
            governance_risk=gov_risk,
            contract_coverage_best=float(best_parts.contract_coverage_score) if best_parts else 0.0,
            required_coverage_best=float(best_parts.required_coverage) if best_parts else 0.0,
            contract_leader_gap=contract_leader_gap,
        )

        cg_code, cg_detail = self._contract_gate_eval(
            float(best_parts.contract_coverage_score) if best_parts else 0.0,
            float(best_parts.required_coverage) if best_parts else 0.0,
            gov_risk,
        )
        sem_for_suggested = float(detail_by_domain.get(best_domain or "", {}).get("semantic_similarity", 0.0))
        prc = self._primary_reason_code(reason_codes)
        trust_note = self._trust_eligibility_note(admission_decision, best_final, reason_codes, sem_for_suggested)

        matched_memory = self._matched_memory_entries_for_dataset(
            dataset_profile=self._build_dataset_profile_text(csv_path.name, df, columns_detected),
            memory_entries=memory_entries,
            top_domain=best_domain or "",
        )

        explanation = self._build_passport_explanation(
            admission_decision=admission_decision,
            reason_codes=reason_codes,
            best_domain=best_domain,
            detail=detail_by_domain.get(best_domain or "", {}),
            semantic_best=sem_best,
            sem_gap=sem_gap,
            gov_risk=gov_risk,
            contract_cov=float(best_parts.contract_coverage_score) if best_parts else 0.0,
            req_cov=float(best_parts.required_coverage) if best_parts else 0.0,
            contract_gap=contract_leader_gap,
        )
        explanation = (
            explanation
            + f" Admission trust score blends contract-primary signals "
            f"(45% contract coverage, 25% lexical similarity for this domain, 15% memory, 15% filename). "
            f"Contract gate={cg_code}. "
            + (f"{trust_note} " if trust_note else "")
        )

        passport_id = str(uuid.uuid4())[:12]
        dataset_profile_text = self._build_dataset_profile_text(csv_path.name, df, columns_detected)

        mem_raw = float(detail_by_domain.get(best_domain or "", {}).get("memory_feedback_score", 0.5))
        mem_ui = self._memory_display_fields(
            memory_entries=memory_entries,
            best_domain=best_domain or "",
            memory_score=mem_raw,
            matched_memory=matched_memory,
        )

        passport: dict[str, Any] = {
            "passport_id": passport_id,
            "dataset_name": csv_path.name,
            "dataset_origin": origin,
            "dataset_origin_display": self._dataset_origin_display(origin),
            "dataset_profile_text": dataset_profile_text,
            "suggested_domain": best_domain,
            "required_coverage": round(float(best_parts.required_coverage), 4) if best_parts else 0.0,
            "contract_leader_gap": round(contract_leader_gap, 4),
            "semantic_best_domain": sem_best,
            "semantic_similarity_score": round(sem_best_score, 4),
            "semantic_similarity_for_suggested_domain": round(sem_for_suggested, 4),
            "contract_coverage_score": round(detail_by_domain.get(best_domain or "", {}).get("contract_coverage_score", 0.0), 4),
            "memory_feedback_score": round(mem_raw, 4),
            "filename_score": round(detail_by_domain.get(best_domain or "", {}).get("filename_score", 0.0), 4),
            "final_admission_score": round(best_final, 4),
            "contract_gate": cg_code,
            "contract_gate_detail": cg_detail,
            "primary_reason_code": prc,
            "trust_eligibility_note": trust_note,
            "second_best_domain": second_domain,
            "second_best_score": round(second_final, 4),
            "semantic_second_best_domain": sem_second,
            "semantic_second_best_score": round(sem_second_score, 4),
            "ambiguity_gap": round(sem_gap, 4),
            "matched_memory_entries": matched_memory,
            "governance_risk_preview": gov_risk,
            "recommended_action": admission_decision,
            "admission_decision": admission_decision,
            "review_required": admission_decision
            in {"HUMAN_REVIEW_REQUIRED", "NEW_DOMAIN_CANDIDATE", "GOVERNANCE_TICKET_RECOMMENDED"},
            "explanation": explanation,
            "timestamp": timestamp,
            "policy_reason_codes": reason_codes,
            "lexical_similarity_note": "Lexical / statistical TF-IDF similarity over profiles (not deep semantic AI).",
            "memory_display_mode": mem_ui["mode"],
            "memory_score_for_display": mem_ui.get("score_for_display"),
        }

        review_required = passport["review_required"]
        if admission_decision == "NEW_DOMAIN_CANDIDATE":
            candidate_name = self._candidate_domain_name(csv_path.name, columns_detected, ranked_parts)
        else:
            candidate_name = None

        final_domain = best_domain if admission_decision == "AUTO_LOAD_ELIGIBLE" else None

        row = {
            "run_id": run_id,
            "dataset_name": csv_path.name,
            "dataset_origin": origin,
            "dataset_origin_display": self._dataset_origin_display(origin),
            "dataset_profile_text": dataset_profile_text,
            "columns_detected": columns_detected,
            "best_domain": best_domain,
            "confidence_score": round(best_final, 4),
            "semantic_similarity_score": round(sem_best_score, 4),
            "semantic_similarity_for_suggested_domain": round(sem_for_suggested, 4),
            "contract_coverage_score": passport["contract_coverage_score"],
            "memory_feedback_score": passport["memory_feedback_score"],
            "filename_score": passport["filename_score"],
            "final_admission_score": round(best_final, 4),
            "policy_reason_codes": reason_codes,
            "contract_gate": cg_code,
            "contract_gate_detail": cg_detail,
            "primary_reason_code": prc,
            "trust_eligibility_note": trust_note,
            "second_best_domain": second_domain,
            "second_best_score": round(second_final, 4),
            "semantic_best_domain": sem_best,
            "semantic_second_best_domain": sem_second,
            "semantic_second_best_score": round(sem_second_score, 4),
            "semantic_ambiguity_gap": round(sem_gap, 4),
            "all_domain_scores": {k: round(v, 4) for k, v in final_scores.items()},
            "all_semantic_scores": {k: round(float(v), 4) for k, v in sem_sims.items()},
            "action": admission_decision,
            "admission_decision": admission_decision,
            "review_required": review_required,
            "candidate_domain_name": candidate_name,
            "final_domain": final_domain,
            "timestamp": timestamp,
            "explanation": explanation,
            "governance_risk_preview": gov_risk,
            "admission_passport": passport,
            "recommended_action": admission_decision,
            "memory_display_mode": mem_ui["mode"],
            "memory_score_for_display": mem_ui.get("score_for_display"),
            "required_coverage": round(float(best_parts.required_coverage), 4) if best_parts else None,
            "contract_leader_gap": round(contract_leader_gap, 4),
            "memory_signal_active": mem_ui["mode"] == "scored",
        }
        self._enrich_admission_row(row)
        return row

    def _audit_row_from_passport(
        self,
        run_id: str,
        csv_path: Path,
        columns_detected: list[str],
        passport: dict[str, Any],
        admission_decision: str,
        review_required: bool,
        candidate_domain_name: str | None,
        ranked_final: dict[str, float],
        semantic_sims: dict[str, float],
        extra_explanation: str,
    ) -> dict:
        ts = passport.get("timestamp") or datetime.now().isoformat(timespec="seconds")
        explanation = str(passport.get("explanation") or "") + " " + extra_explanation
        best = passport.get("suggested_domain")
        conf = float(passport.get("final_admission_score") or 0.95)
        out = {
            "run_id": run_id,
            "dataset_name": csv_path.name,
            "dataset_profile_text": passport.get("dataset_profile_text"),
            "columns_detected": columns_detected,
            "best_domain": best,
            "confidence_score": conf,
            "semantic_similarity_score": passport.get("semantic_similarity_score"),
            "semantic_similarity_for_suggested_domain": passport.get("semantic_similarity_for_suggested_domain"),
            "contract_coverage_score": passport.get("contract_coverage_score"),
            "memory_feedback_score": passport.get("memory_feedback_score"),
            "filename_score": passport.get("filename_score"),
            "final_admission_score": conf,
            "dataset_origin": passport.get("dataset_origin"),
            "dataset_origin_display": passport.get("dataset_origin_display"),
            "policy_reason_codes": passport.get("policy_reason_codes"),
            "contract_gate": passport.get("contract_gate"),
            "contract_gate_detail": passport.get("contract_gate_detail"),
            "primary_reason_code": passport.get("primary_reason_code"),
            "trust_eligibility_note": passport.get("trust_eligibility_note"),
            "second_best_domain": passport.get("second_best_domain"),
            "second_best_score": passport.get("second_best_score"),
            "semantic_best_domain": passport.get("semantic_best_domain"),
            "semantic_second_best_domain": passport.get("semantic_second_best_domain"),
            "semantic_second_best_score": passport.get("semantic_second_best_score"),
            "semantic_ambiguity_gap": passport.get("ambiguity_gap"),
            "all_domain_scores": ranked_final,
            "all_semantic_scores": semantic_sims,
            "action": admission_decision,
            "admission_decision": admission_decision,
            "review_required": review_required,
            "candidate_domain_name": candidate_domain_name,
            "final_domain": best,
            "timestamp": ts,
            "explanation": explanation.strip(),
            "governance_risk_preview": passport.get("governance_risk_preview"),
            "admission_passport": passport,
            "recommended_action": admission_decision,
            "memory_display_mode": passport.get("memory_display_mode"),
            "memory_score_for_display": passport.get("memory_score_for_display"),
            "required_coverage": passport.get("required_coverage"),
            "contract_leader_gap": passport.get("contract_leader_gap"),
            "memory_signal_active": passport.get("memory_display_mode") in {"scored", "registry"},
        }
        self._enrich_admission_row(out)
        return out

    def _build_created_domain_passport(
        self,
        csv_path: Path,
        dataset_profile_text: str,
        domain_name: str,
        timestamp: str,
        registry_entry: dict[str, Any],
    ) -> dict[str, Any]:
        cr_origin = self._dataset_origin_for_name(csv_path.name)
        return {
            "passport_id": str(uuid.uuid4())[:12],
            "dataset_name": csv_path.name,
            "dataset_origin": cr_origin,
            "dataset_origin_display": self._dataset_origin_display(cr_origin),
            "dataset_profile_text": dataset_profile_text,
            "suggested_domain": domain_name,
            "required_coverage": 1.0,
            "contract_leader_gap": 1.0,
            "semantic_best_domain": domain_name,
            "semantic_similarity_score": 0.95,
            "semantic_similarity_for_suggested_domain": 0.95,
            "contract_coverage_score": 0.95,
            "memory_feedback_score": 1.0,
            "filename_score": 0.95,
            "final_admission_score": 0.95,
            "contract_gate": "PASSED",
            "contract_gate_detail": "Routed via governed created-domain registry; prior approval applies.",
            "primary_reason_code": "CREATED_DOMAIN_REGISTRY",
            "trust_eligibility_note": None,
            "second_best_domain": None,
            "second_best_score": None,
            "semantic_second_best_domain": None,
            "semantic_second_best_score": None,
            "ambiguity_gap": 1.0,
            "matched_memory_entries": [],
            "governance_risk_preview": "LOW",
            "recommended_action": "AUTO_ASSIGN_CREATED_DOMAIN",
            "admission_decision": "AUTO_ASSIGN_CREATED_DOMAIN",
            "review_required": False,
            "memory_display_mode": "registry",
            "memory_score_for_display": None,
            "explanation": (
                f"Routed to approved created domain '{domain_name}' via registry "
                f"(source_dataset={registry_entry.get('source_dataset_name')})."
            ),
            "timestamp": timestamp,
            "policy_reason_codes": ["CREATED_DOMAIN_REGISTRY"],
            "lexical_similarity_note": "Registry match overrides lexical scoring.",
        }

    # ------------------------------------------------------------------
    # Policy
    # ------------------------------------------------------------------
    def _resolve_admission_policy(
        self,
        final_score_best: float,
        semantic_gap: float,
        required_coverage_ok: bool,
        governance_risk: str,
        contract_coverage_best: float,
        required_coverage_best: float,
        contract_leader_gap: float,
    ) -> tuple[str, list[str]]:
        if governance_risk == "HIGH":
            return "GOVERNANCE_TICKET_RECOMMENDED", ["GOVERNANCE_RISK_HIGH"]

        margin_ok = semantic_gap >= 0.10 or contract_leader_gap >= 0.10

        # Contract-first: strong governance fit for known domains (TF-IDF must not veto alone).
        if (
            contract_coverage_best >= 0.75
            and required_coverage_best >= 0.70
            and governance_risk != "HIGH"
            and margin_ok
        ):
            return "AUTO_LOAD_ELIGIBLE", ["CONTRACT_FIRST_GOVERNANCE_MATCH"]

        if final_score_best < 0.40:
            # Very weak fit to all domains → possible new domain; else ambiguous → human review.
            if contract_coverage_best < 0.28 and required_coverage_best < 0.35:
                return "NEW_DOMAIN_CANDIDATE", ["LOW_SCORE_NEW_DOMAIN"]
            return "HUMAN_REVIEW_REQUIRED", ["LOW_COMPOSITE_AMBIGUOUS"]

        if not margin_ok:
            return "HUMAN_REVIEW_REQUIRED", ["LOW_MARGIN_AMBIGUOUS"]

        if 0.40 <= final_score_best < 0.70:
            return "HUMAN_REVIEW_REQUIRED", ["SCORE_BAND_PROVISIONAL"]

        if final_score_best >= 0.70 and margin_ok and required_coverage_ok:
            return "AUTO_LOAD_ELIGIBLE", ["HYBRID_SCORE_AND_MARGIN_OK"]

        return "HUMAN_REVIEW_REQUIRED", ["FALLBACK_REVIEW"]

    def _domain_has_reviewer_memory_for_domain(self, memory_entries: list[dict], domain: str) -> bool:
        dom = (domain or "").strip().lower()
        if not dom:
            return False
        for m in memory_entries:
            if not isinstance(m, dict):
                continue
            if str(m.get("domain_name") or "").strip().lower() != dom:
                continue
            if str(m.get("reviewer_action") or "").upper() == "REJECT":
                continue
            return True
        return False

    def _memory_for_trust_composite(self, mem_raw: float, memory_entries: list[dict], domain: str) -> float:
        """When no reviewer memory exists for a domain, avoid treating 0.5 as a penalty in the trust blend."""
        if self._domain_has_reviewer_memory_for_domain(memory_entries, domain):
            return float(mem_raw)
        return 0.78

    def _contract_gate_eval(self, contract_cov: float, required_cov: float, governance_risk: str) -> tuple[str, str]:
        """PASSED / REVIEW / FAILED for UI — independent of auto-load policy thresholds."""
        if governance_risk == "HIGH":
            return "REVIEW", "Governance risk is elevated; contract signals are evaluated alongside risk controls."
        if contract_cov >= 0.75 and required_cov >= 0.70:
            return "PASSED", "Strong alignment with required and optional contract columns for the suggested domain."
        if contract_cov < 0.35 or required_cov < 0.30:
            return "FAILED", "Insufficient overlap with the domain contract (coverage or required columns)."
        return "REVIEW", "Partial contract alignment; confirm with lexical similarity and reviewer memory."

    def _primary_reason_code(self, reason_codes: list[str]) -> str:
        if reason_codes:
            return str(reason_codes[0])
        return "UNKNOWN"

    def _reason_code_display(self, code: str | None) -> str:
        c = str(code or "")
        if not c:
            return "—"
        return REASON_CODE_DISPLAY.get(c, c.replace("_", " ").title())

    def _trust_eligibility_note(
        self,
        admission_decision: str,
        trust_score: float,
        reason_codes: list[str],
        semantic_for_suggested: float,
    ) -> str | None:
        """Explains AUTO_LOAD_ELIGIBLE when trust score is < 70% (viva-defensible)."""
        if admission_decision != "AUTO_LOAD_ELIGIBLE":
            return None
        if trust_score >= 0.70:
            return None
        codes = set(reason_codes or [])
        if "CONTRACT_FIRST_GOVERNANCE_MATCH" in codes:
            return (
                "Eligible because contract gate passed strongly, although semantic similarity is moderate."
            )
        if semantic_for_suggested < 0.42:
            return (
                "Eligible because contract gate passed strongly, although lexical profile similarity is moderate."
            )
        return (
            "Eligible under admission policy: trust score is below 70% but margins and governance checks passed."
        )

    def _memory_display_fields(
        self,
        memory_entries: list[dict],
        best_domain: str,
        memory_score: float,
        matched_memory: list[dict],
    ) -> dict[str, Any]:
        """UI hints: avoid showing neutral 50% when no reviewer memory applies."""
        if not memory_entries:
            return {"mode": "no_bank", "score_for_display": None}
        dom = (best_domain or "").strip().lower()
        has_domain_row = any(
            isinstance(m, dict) and str(m.get("domain_name") or "").strip().lower() == dom for m in memory_entries
        )
        if matched_memory or has_domain_row:
            return {"mode": "scored", "score_for_display": round(float(memory_score), 4)}
        return {"mode": "neutral", "score_for_display": None}

    def _governance_risk_preview(self, df: pd.DataFrame) -> str:
        if df is None or len(df) == 0:
            return "HIGH"
        n = len(df)
        null_rate = float(df.isnull().values.mean()) if len(df.columns) else 0.0
        # Softer thresholds so typical Silver products are not all HIGH for viva demos.
        if null_rate > 0.40:
            return "HIGH"
        if n <= 2 or null_rate > 0.25:
            return "HIGH"
        if n < 12 or null_rate > 0.12:
            return "MEDIUM"
        return "LOW"

    # ------------------------------------------------------------------
    # Profiles & similarity
    # ------------------------------------------------------------------
    def _build_dataset_profile_text(self, dataset_name: str, df: pd.DataFrame, columns: list[str]) -> str:
        parts = [f"dataset:{dataset_name}", "columns:" + ",".join(columns)]
        dtypes = [str(df[c].dtype) for c in df.columns[: min(40, len(df.columns))]]
        parts.append("dtypes:" + ",".join(dtypes))
        parts.append("schema_summary:" + self._schema_summary(df))
        parts.append("samples:" + self._safe_sample_summary(df))
        return " ".join(parts)

    def _schema_summary(self, df: pd.DataFrame) -> str:
        pieces = []
        for col in list(df.columns)[:25]:
            s = df[col]
            nn = s.notna().sum()
            pieces.append(f"{col}[non_null={int(nn)}]")
        return ";".join(pieces)

    def _safe_sample_summary(self, df: pd.DataFrame) -> str:
        snippets: list[str] = []
        for col in list(df.columns)[:12]:
            series = df[col].dropna()
            if series.empty:
                continue
            head = series.head(50)
            nuniq = head.nunique()
            if pd.api.types.is_numeric_dtype(series):
                snippets.append(f"{col}:num_min={float(series.min()):.4g},max={float(series.max()):.4g}")
            elif nuniq <= 6:
                vals = [self._redact_token(str(v)) for v in head.unique()[:6]]
                snippets.append(f"{col}:cats={','.join(vals)}")
            else:
                snippets.append(f"{col}:n_unique<={int(nuniq)}")
        return ";".join(snippets)[:1200]

    def _redact_token(self, value: str) -> str:
        v = value.strip()
        if "@" in v and "." in v:
            return "[EMAIL]"
        if len(v) > 32:
            return v[:29] + "..."
        return v

    def _build_domain_profile_texts(self, signatures: dict[str, dict[str, set[str]]]) -> dict[str, str]:
        memory = self._read_memory_bank()
        approved_names: dict[str, list[str]] = {}
        for m in memory:
            if not isinstance(m, dict):
                continue
            if str(m.get("reviewer_action") or "").upper() == "REJECT":
                continue
            d = str(m.get("domain_name") or "").strip().lower()
            ds = str(m.get("dataset_name") or "").strip()
            if d and ds:
                approved_names.setdefault(d, []).append(ds)

        profiles: dict[str, str] = {}
        for domain, sig in signatures.items():
            cols = sorted(sig.get("all", set()))
            contract_cols = "contract_columns:" + ",".join(cols)
            schema_bits: list[str] = []
            domain_csv = self.domain_products_dir / domain / f"{domain}.csv"
            if domain_csv.is_file():
                try:
                    ddf = pd.read_csv(domain_csv, nrows=80)
                    schema_bits.append("product_schema_columns:" + ",".join([str(c).strip().lower() for c in ddf.columns]))
                except Exception:
                    pass
            mem_ds = approved_names.get(domain, [])
            mem_part = "approved_dataset_names:" + ",".join(mem_ds[-15:])
            text = f"domain:{domain} {contract_cols} {' '.join(schema_bits)} {mem_part}"
            profiles[domain] = text
        return profiles

    def _semantic_similarities(self, dataset_profile: str, domain_profile_texts: dict[str, str]) -> dict[str, float]:
        if not domain_profile_texts:
            return {}
        domains = list(domain_profile_texts.keys())
        texts = [dataset_profile] + [domain_profile_texts[d] for d in domains]
        vectorizer = TfidfVectorizer(max_features=4096, ngram_range=(1, 2), lowercase=True, min_df=1)
        try:
            matrix = vectorizer.fit_transform(texts)
        except ValueError:
            return {d: 0.0 for d in domains}
        sims = cosine_similarity(matrix[0:1], matrix[1:])[0]
        return {domains[i]: max(0.0, min(1.0, float(sims[i]))) for i in range(len(domains))}

    def _memory_feedback_scores(self, dataset_profile: str, memory_entries: list[dict], domains: list[str]) -> dict[str, float]:
        scores: dict[str, float] = {}
        for d in domains:
            pos_profiles = [
                str(m.get("dataset_profile_text") or "")
                for m in memory_entries
                if isinstance(m, dict)
                and str(m.get("domain_name") or "").strip().lower() == d
                and str(m.get("reviewer_action") or "").upper() != "REJECT"
            ]
            neg_profiles = [
                str(m.get("dataset_profile_text") or "")
                for m in memory_entries
                if isinstance(m, dict)
                and str(m.get("domain_name") or "").strip().lower() == d
                and str(m.get("reviewer_action") or "").upper() == "REJECT"
            ]
            pos_sim = self._max_profile_similarity(dataset_profile, pos_profiles) if pos_profiles else 0.0
            neg_sim = self._max_profile_similarity(dataset_profile, neg_profiles) if neg_profiles else 0.0
            raw = 0.5 + 0.5 * pos_sim - 0.5 * neg_sim
            scores[d] = max(0.0, min(1.0, raw))
        return scores

    def _max_profile_similarity(self, query: str, profiles: list[str]) -> float:
        if not profiles:
            return 0.0
        texts = [query] + profiles
        vectorizer = TfidfVectorizer(max_features=2048, ngram_range=(1, 2), lowercase=True, min_df=1)
        try:
            matrix = vectorizer.fit_transform(texts)
        except ValueError:
            return 0.0
        sims = cosine_similarity(matrix[0:1], matrix[1:])[0]
        return max(float(x) for x in sims) if len(sims) else 0.0

    def _matched_memory_entries_for_dataset(
        self,
        dataset_profile: str,
        memory_entries: list[dict],
        top_domain: str,
    ) -> list[dict]:
        matched: list[dict] = []
        for m in memory_entries:
            if not isinstance(m, dict):
                continue
            mp = str(m.get("dataset_profile_text") or "")
            if not mp:
                continue
            sim = self._max_profile_similarity(dataset_profile, [mp])
            if sim >= 0.08:
                matched.append(
                    {
                        "domain_name": m.get("domain_name"),
                        "dataset_name": m.get("dataset_name"),
                        "reviewer_action": m.get("reviewer_action"),
                        "similarity_score": round(float(sim), 4),
                    }
                )
        matched.sort(key=lambda x: float(x.get("similarity_score") or 0), reverse=True)
        return matched[:12]

    # ------------------------------------------------------------------
    # Contracts / ranking
    # ------------------------------------------------------------------
    def _rank_domain_contract_parts(
        self,
        csv_path: Path,
        dataset_columns: list[str],
        signatures: dict[str, dict[str, set[str]]],
    ) -> list[DomainRankParts]:
        dataset_set = set(dataset_columns)
        ranked: list[DomainRankParts] = []
        for domain, signature in signatures.items():
            domain_columns = signature.get("all", set())
            required = signature.get("required", set())
            optional = signature.get("optional", set())
            if not domain_columns:
                continue
            matched = sorted(dataset_set.intersection(domain_columns))
            req_match_count = len(dataset_set.intersection(required))
            opt_match_count = len(dataset_set.intersection(optional))
            required_coverage = req_match_count / max(1, len(required))
            optional_coverage = opt_match_count / max(1, len(optional)) if optional else required_coverage
            raw_column_score = (0.75 * required_coverage) + (0.25 * optional_coverage)
            unmatched_dataset_cols = max(0, len(dataset_set) - len(matched))
            noise_penalty = min(0.25, unmatched_dataset_cols * 0.03)
            column_score = max(0.0, raw_column_score - noise_penalty)
            contract_coverage_score = max(0.0, min(1.0, column_score))
            filename_score = self._filename_score(csv_path.stem, domain)
            ranked.append(
                DomainRankParts(
                    domain=domain,
                    contract_coverage_score=contract_coverage_score,
                    filename_score=float(filename_score),
                    column_score=float(column_score),
                    required_coverage=float(required_coverage),
                    optional_coverage=float(optional_coverage),
                    matched_columns=matched,
                )
            )
        ranked.sort(key=lambda item: item.contract_coverage_score, reverse=True)
        return ranked

    def _merge_created_domain_signatures(self, signatures: dict[str, dict[str, set[str]]]) -> None:
        for entry in self._active_created_domains():
            name = str(entry.get("domain_name") or "").strip().lower()
            cols = entry.get("source_columns") or []
            if not name or not isinstance(cols, list):
                continue
            col_set = {str(c).strip().lower() for c in cols if str(c).strip()}
            signatures[name] = {
                "required": set(col_set),
                "optional": set(),
                "all": set(col_set),
            }

    def _match_created_domain_for_dataset(self, dataset_name: str) -> dict[str, Any] | None:
        for entry in self._active_created_domains():
            if str(entry.get("source_dataset_name") or "").strip() == dataset_name:
                return entry
        return None

    def _filename_score(self, file_stem: str, domain_name: str) -> float:
        stem_tokens = self._tokenize(file_stem)
        domain_tokens = self._tokenize(domain_name.replace("_domain", ""))
        if not stem_tokens or not domain_tokens:
            return 0.0
        overlap = stem_tokens.intersection(domain_tokens)
        if overlap:
            return 1.0
        aliases = {
            "sales_domain": {"transaction", "transactions", "orders", "order"},
            "users_domain": {"users", "user", "customer", "customers"},
            "product_domain": {"product", "products", "catalog", "inventory"},
            "shop_domain": {"shop", "shops", "store", "stores"},
            "engagement_domain": {"trend", "trends", "engagement"},
            "interaction_domain": {"interaction", "interactions", "event", "events", "activity"},
            "user_preferences_domain": {"preference", "preferences", "user_preferences"},
        }
        domain_aliases = aliases.get(domain_name, set())
        return 0.6 if stem_tokens.intersection(domain_aliases) else 0.0

    def _required_columns(self, domain_name: str, columns: list[str]) -> set[str]:
        column_set = set(columns)
        explicit: dict[str, set[str]] = {
            "sales": {"transaction_id", "user_id", "product_id", "transaction_date"},
            "users": {"user_id", "email", "signup_ts"},
            "product": {"product_id", "shop_id", "category", "price_lkr"},
            "shop": {"shop_id", "shop_name", "location"},
            "interaction": {"interaction_id", "user_id", "product_id", "interaction_ts"},
            "engagement": {"trend_id", "trend_name", "trend_score"},
            "preferences": {"preference_id", "user_id", "updated_ts"},
        }
        for key, req_cols in explicit.items():
            if key in domain_name:
                matched_explicit = req_cols.intersection(column_set)
                if matched_explicit:
                    return matched_explicit
        id_cols = sorted([col for col in columns if col.endswith("_id")])
        time_cols = sorted([col for col in columns if any(token in col for token in ("date", "_ts", "time"))])
        selected: list[str] = []
        selected.extend(id_cols[:3])
        selected.extend([col for col in time_cols if col not in selected][:1])
        if not selected:
            selected = columns[: min(4, len(columns))]
        return set(selected)

    def _candidate_domain_name(self, dataset_name: str, columns_detected: list[str], ranked: list[DomainRankParts]) -> str:
        stop_words = {"clean", "silver", "data", "dataset", "raw", "v1", "v2", "csv", "test"}
        ordered_tokens = [token for token in re.split(r"[^a-z0-9]+", Path(dataset_name).stem.lower()) if token]
        filename_tokens = [token for token in ordered_tokens if token not in stop_words]
        if filename_tokens:
            return f"candidate_{filename_tokens[0]}"
        if ranked and ranked[0].matched_columns:
            strongest = ranked[0].matched_columns[0]
            strongest_token = self._tokenize(strongest)
            if strongest_token:
                return f"candidate_{sorted(strongest_token)[0]}"
        if columns_detected:
            fallback = self._tokenize(columns_detected[0])
            if fallback:
                return f"candidate_{sorted(fallback)[0]}"
        return "candidate_new_domain"

    def _build_passport_explanation(
        self,
        admission_decision: str,
        reason_codes: list[str],
        best_domain: str | None,
        detail: dict[str, float],
        semantic_best: str | None,
        sem_gap: float,
        gov_risk: str,
        contract_cov: float,
        req_cov: float,
        contract_gap: float,
    ) -> str:
        parts = [
            f"Decision={admission_decision}; governance_risk={gov_risk}; "
            f"codes={','.join(reason_codes)}.",
            f"Top domain ({best_domain}): contract_coverage={contract_cov:.3f}, required_coverage={req_cov:.3f}, "
            f"contract_leader_gap={contract_gap:.3f}.",
            f"Trust inputs: lexical_similarity(suggested)={detail.get('semantic_similarity', 0):.3f}, "
            f"memory_feedback={detail.get('memory_feedback_score', 0):.3f}, "
            f"filename={detail.get('filename_score', 0):.3f}; trust_score={detail.get('final_admission_score', 0):.3f}.",
            f"Lexical best={semantic_best}; lexical_margin={sem_gap:.3f}. "
            "Contracts govern eligibility; lexical similarity is supportive TF-IDF evidence.",
        ]
        return " ".join(parts)

    # ------------------------------------------------------------------
    # Storage helpers
    # ------------------------------------------------------------------
    def _silver_csv_files(self) -> list[Path]:
        if not self.silver_dir.exists():
            return []
        return sorted([path for path in self.silver_dir.glob("*.csv") if path.is_file()], key=lambda p: p.name.lower())

    def _domain_signatures(self) -> dict[str, dict[str, set[str]]]:
        signatures: dict[str, dict[str, set[str]]] = {}
        if not self.contracts_dir.exists():
            return signatures
        for contract_file in self.contracts_dir.glob("*.yml"):
            domain = contract_file.stem.lower()
            columns = self._contract_columns(contract_file)
            if columns:
                required = self._required_columns(domain_name=domain, columns=columns)
                optional = set(columns) - required
                signatures[domain] = {
                    "required": required,
                    "optional": optional,
                    "all": set(columns),
                }
        return signatures

    def _contract_columns(self, contract_file: Path) -> list[str]:
        try:
            payload = yaml.safe_load(contract_file.read_text(encoding="utf-8")) or {}
        except Exception:
            return []
        schema = payload.get("schema") if isinstance(payload, dict) else None
        if not isinstance(schema, list):
            return []
        cols = []
        for item in schema:
            if isinstance(item, dict) and item.get("column"):
                cols.append(str(item.get("column")).strip().lower())
        return cols

    def _dataset_schema(self, csv_path: Path) -> tuple[list[str], int]:
        try:
            df = pd.read_csv(csv_path)
        except Exception:
            return [], 0
        cols = [str(col).strip().lower() for col in list(df.columns)]
        return cols, int(len(df))

    def _read_audit_rows(self) -> list[dict]:
        if not self.audit_log_path.exists():
            return []
        try:
            payload = json.loads(self.audit_log_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        return []

    def _append_audit_rows(self, new_rows: list[dict]) -> None:
        self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        existing = self._read_audit_rows()
        combined = list(new_rows) + existing
        self.audit_log_path.write_text(json.dumps(combined, indent=2), encoding="utf-8")

    def _read_memory_bank(self) -> list[dict]:
        if not self.domain_memory_path.exists():
            return []
        try:
            data = json.loads(self.domain_memory_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        return data if isinstance(data, list) else []

    def _append_memory_bank(self, record: dict[str, Any]) -> None:
        rows = self._read_memory_bank()
        rows.append(record)
        self.domain_memory_path.parent.mkdir(parents=True, exist_ok=True)
        self.domain_memory_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    def _clear_memory_bank(self) -> bool:
        if self.domain_memory_path.exists():
            self.domain_memory_path.unlink(missing_ok=True)
            return True
        return False

    def _append_review_decision(self, record: dict[str, Any]) -> None:
        rows: list[dict] = []
        if self.review_decisions_path.exists():
            try:
                payload = json.loads(self.review_decisions_path.read_text(encoding="utf-8"))
                if isinstance(payload, list):
                    rows = payload
            except Exception:
                rows = []
        rows.append(record)
        self.review_decisions_path.parent.mkdir(parents=True, exist_ok=True)
        self.review_decisions_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    def _append_ticket(self, record: dict[str, Any]) -> None:
        rows: list[dict] = []
        if self.review_tickets_path.exists():
            try:
                payload = json.loads(self.review_tickets_path.read_text(encoding="utf-8"))
                if isinstance(payload, list):
                    rows = payload
            except Exception:
                rows = []
        rows.append(record)
        self.review_tickets_path.parent.mkdir(parents=True, exist_ok=True)
        self.review_tickets_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    def _read_created_registry(self) -> list[dict]:
        if not self.created_domain_registry_path.exists():
            return []
        try:
            data = json.loads(self.created_domain_registry_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        return data if isinstance(data, list) else []

    def _write_created_registry(self, rows: list[dict]) -> None:
        self.created_domain_registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.created_domain_registry_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    def _active_created_domains(self) -> list[dict]:
        return [x for x in self._read_created_registry() if isinstance(x, dict) and x.get("status") == "ACTIVE"]

    def _upsert_created_domain_registry(
        self,
        domain_name: str,
        source_dataset_name: str,
        source_columns: list[str],
        detection_run_id: str,
    ) -> None:
        reg = self._read_created_registry()
        now = datetime.now().isoformat(timespec="seconds")
        entry = {
            "domain_id": str(uuid.uuid4())[:12],
            "domain_name": domain_name,
            "source_dataset_name": source_dataset_name,
            "source_columns": source_columns,
            "created_from_candidate": True,
            "detection_run_id": detection_run_id,
            "status": "ACTIVE",
            "created_at": now,
            "deleted_at": None,
            "created_by": "silver_to_domain_loader",
            "is_system_domain": False,
        }
        replaced = False
        for i, item in enumerate(reg):
            if isinstance(item, dict) and str(item.get("domain_name") or "").lower() == domain_name.lower():
                reg[i] = {**item, **entry, "status": "ACTIVE"}
                replaced = True
                break
        if not replaced:
            reg.append(entry)
        self._write_created_registry(reg)

    def _create_domain_folder(self, domain_name: str, source_csv: Path) -> None:
        folder = self.domain_products_dir / domain_name
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"{domain_name}.csv"
        target.write_bytes(source_csv.read_bytes())

    def _normalize_domain_name(self, value: str) -> str:
        raw = str(value or "").strip().lower()
        if not raw:
            return ""
        return raw if raw.endswith("_domain") else f"{raw}_domain"

    def _read_materialization_log(self) -> list[dict]:
        if not self.materialization_log_path.exists():
            return []
        try:
            data = json.loads(self.materialization_log_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        return data if isinstance(data, list) else []

    def _append_materialization_record(self, record: dict[str, Any]) -> None:
        rows = self._read_materialization_log()
        rows.append(record)
        self.materialization_log_path.parent.mkdir(parents=True, exist_ok=True)
        self.materialization_log_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    def _latest_loading_status(self, dataset_name: str, target_domain: str) -> str:
        if not dataset_name or not target_domain:
            return "NOT_LOADED"
        nt = self._normalize_domain_name(target_domain).lower()
        matched = [
            r
            for r in self._read_materialization_log()
            if isinstance(r, dict)
            and str(r.get("dataset_name") or "") == dataset_name
            and self._normalize_domain_name(str(r.get("target_domain") or "")).lower() == nt
        ]
        if not matched:
            return "NOT_LOADED"
        matched.sort(key=lambda x: str(x.get("timestamp") or ""), reverse=True)
        return str(matched[0].get("loading_status") or "NOT_LOADED")

    def _loading_status_display(self, code: str) -> str:
        labels = {
            "NOT_LOADED": "Not loaded",
            "LOADED_TO_DOMAIN": "Loaded to domain",
            "LOAD_FAILED": "Load failed",
            "ALREADY_GOVERNED": "Already governed",
        }
        return labels.get(str(code), str(code))

    def _admission_decision_display(self, decision: str | None) -> str:
        d = str(decision or "")
        mapping = {
            "AUTO_LOAD_ELIGIBLE": "Eligible for domain loading",
            "AUTO_ASSIGN_CREATED_DOMAIN": "Eligible (created domain)",
            "HUMAN_REVIEW_REQUIRED": "Human review required",
            "NEW_DOMAIN_CANDIDATE": "New domain candidate",
            "GOVERNANCE_TICKET_RECOMMENDED": "Governance ticket recommended",
        }
        return mapping.get(d, d or "—")

    def _find_audit_row_by_passport(self, passport_id: str, dataset_name: str) -> dict | None:
        for row in self._read_audit_rows():
            if not isinstance(row, dict):
                continue
            if str(row.get("dataset_name") or "") != dataset_name:
                continue
            pp = row.get("admission_passport") if isinstance(row.get("admission_passport"), dict) else {}
            if str(pp.get("passport_id") or "") == str(passport_id):
                return row
        return None

    def _read_review_decisions_flat(self) -> list[dict]:
        if not self.review_decisions_path.exists():
            return []
        try:
            data = json.loads(self.review_decisions_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        return data if isinstance(data, list) else []

    def _review_allows_materialization(self, dataset_name: str, target_domain: str) -> bool:
        nt = self._normalize_domain_name(target_domain).lower()
        positive = {
            "APPROVE",
            "APPROVE_PROVISIONAL",
            "CHANGE_DOMAIN",
            "VALIDATE_CANDIDATE",
            "CREATE_DOMAIN_AFTER_APPROVAL",
        }
        for r in reversed(self._read_review_decisions_flat()):
            if not isinstance(r, dict):
                continue
            if str(r.get("dataset_name") or "") != dataset_name:
                continue
            action = str(r.get("reviewer_action") or "").upper()
            if action not in positive:
                continue
            ap = self._normalize_domain_name(str(r.get("approved_domain") or "")).lower()
            if ap == nt:
                return True
        return False

    def _can_apply_materialization(self, row: dict) -> bool:
        if row.get("dataset_origin") == "CORE":
            return False
        if row.get("loading_status") in {"LOADED_TO_DOMAIN", "ALREADY_GOVERNED"}:
            return False
        decision = str(row.get("admission_decision") or row.get("action") or "")
        dataset = str(row.get("dataset_name") or "")
        target = str(row.get("best_domain") or "")
        if not target:
            return False
        if decision in {"AUTO_LOAD_ELIGIBLE", "AUTO_ASSIGN_CREATED_DOMAIN"}:
            return True
        if decision in {"HUMAN_REVIEW_REQUIRED", "NEW_DOMAIN_CANDIDATE", "GOVERNANCE_TICKET_RECOMMENDED"}:
            return self._review_allows_materialization(dataset, target)
        return False

    def _resolve_domain_product_dir(self, domain_name: str) -> Path:
        norm = self._normalize_domain_name(domain_name)
        if not norm:
            raise ValueError("Invalid domain name.")
        base = self.domain_products_dir
        base.mkdir(parents=True, exist_ok=True)
        for child in base.iterdir():
            if child.is_dir() and child.name.lower() == norm.lower():
                return child
        out = base / norm
        out.mkdir(parents=True, exist_ok=True)
        return out

    def _enrich_admission_row(self, row: dict) -> None:
        decision = str(row.get("admission_decision") or row.get("action") or "")
        dataset = str(row.get("dataset_name") or "")
        target = str(row.get("best_domain") or "")
        pp = row.get("admission_passport") if isinstance(row.get("admission_passport"), dict) else {}
        origin = row.get("dataset_origin") or pp.get("dataset_origin") or self._dataset_origin_for_name(dataset)
        row["dataset_origin"] = origin
        row["dataset_origin_display"] = self._dataset_origin_display(origin)

        ls_raw = self._latest_loading_status(dataset, target)
        if origin == "CORE":
            row["loading_status"] = "ALREADY_GOVERNED"
            row["loading_status_display"] = self._loading_status_display("ALREADY_GOVERNED")
        else:
            row["loading_status"] = ls_raw
            row["loading_status_display"] = self._loading_status_display(ls_raw)
        row["admission_decision_display"] = self._admission_decision_display(decision)
        row["can_apply_to_domain"] = self._can_apply_materialization(dict(row))

        cg = row.get("contract_gate") or pp.get("contract_gate")
        if not cg:
            cc = float(row.get("contract_coverage_score") if row.get("contract_coverage_score") is not None else pp.get("contract_coverage_score") or 0)
            rc_val = row.get("required_coverage")
            if rc_val is None:
                rc_val = pp.get("required_coverage")
            rc_val = float(rc_val or 0)
            gr = str(row.get("governance_risk_preview") or pp.get("governance_risk_preview") or "LOW")
            cg, _detail_infer = self._contract_gate_eval(cc, rc_val, gr)
        row["contract_gate"] = cg
        gate_labels = {"PASSED": "Passed", "REVIEW": "Review", "FAILED": "Failed"}
        row["contract_gate_display"] = gate_labels.get(str(cg or ""), str(cg or "—"))

        rcodes = row.get("policy_reason_codes")
        if not isinstance(rcodes, list):
            rcodes = pp.get("policy_reason_codes") if isinstance(pp.get("policy_reason_codes"), list) else []
        prc = row.get("primary_reason_code") or pp.get("primary_reason_code")
        if not prc:
            prc = self._primary_reason_code(rcodes)
        row["primary_reason_code"] = prc
        row["primary_reason_code_display"] = self._reason_code_display(prc)

        trust = float(row.get("final_admission_score") if row.get("final_admission_score") is not None else row.get("confidence_score") or 0)
        sem_sug = row.get("semantic_similarity_for_suggested_domain")
        if sem_sug is None:
            sem_sug = pp.get("semantic_similarity_for_suggested_domain")
        if sem_sug is None:
            sem_sug = row.get("semantic_similarity_score") if row.get("semantic_similarity_score") is not None else pp.get("semantic_similarity_score")
        sem_sug = float(sem_sug or 0)
        tn = row.get("trust_eligibility_note")
        if tn is None and isinstance(pp, dict):
            tn = pp.get("trust_eligibility_note")
        if tn is None and decision == "AUTO_LOAD_ELIGIBLE":
            tn = self._trust_eligibility_note(decision, trust, rcodes if isinstance(rcodes, list) else [], sem_sug)
        row["trust_eligibility_note"] = tn

    def _tokenize(self, value: str) -> set[str]:
        return {token for token in re.split(r"[^a-z0-9]+", str(value).lower()) if token}
