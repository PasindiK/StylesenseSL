from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import io
import json
from pathlib import Path
import re
import uuid

import pandas as pd
import yaml


@dataclass
class DomainScore:
    domain: str
    score: float
    column_score: float
    filename_score: float
    matched_columns: list[str]
    required_coverage: float
    optional_coverage: float


class SilverToDomainLoaderService:
    """Detects best-fit Data Mesh domains for Silver datasets."""

    def __init__(self, data_root: Path):
        self.data_root = Path(data_root)
        self.silver_dir = self.data_root / "Data" / "Silver-data"
        self.domain_products_dir = self.data_root / "Data_Mesh_Domains"
        self.contracts_dir = self.data_root / "Contracts"
        self.audit_log_path = self.data_root / "monitoring" / "logs" / "silver_domain_loader_audit.json"
        self.review_decisions_path = self.data_root / "monitoring" / "logs" / "domain_review_decisions.json"
        self.review_tickets_path = self.data_root / "monitoring" / "logs" / "domain_review_tickets.json"

    def list_silver_datasets(self) -> dict:
        datasets = []
        for csv_path in self._silver_csv_files():
            columns, row_count = self._dataset_schema(csv_path)
            datasets.append(
                {
                    "dataset_name": csv_path.name,
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
        rows: list[dict] = []

        for csv_path in self._silver_csv_files():
            columns_detected, _row_count = self._dataset_schema(csv_path)
            ranked = self._rank_domains(csv_path=csv_path, dataset_columns=columns_detected, signatures=signatures)
            best = ranked[0] if ranked else None
            second_best = ranked[1] if len(ranked) > 1 else None

            confidence_score = round(best.score, 4) if best else 0.0
            action = self._action_from_confidence(confidence_score)
            candidate_domain_name = (
                self._candidate_domain_name(csv_path.name, columns_detected, ranked)
                if action == "NEW_DOMAIN_CANDIDATE_PENDING_REVIEW"
                else None
            )
            final_domain = best.domain if action == "AUTO_ASSIGN" and best else None
            explanation = self._build_explanation(
                action=action,
                dataset_name=csv_path.name,
                best=best,
                candidate_domain_name=candidate_domain_name,
            )

            row = {
                "run_id": run_id,
                "dataset_name": csv_path.name,
                "columns_detected": columns_detected,
                "best_domain": best.domain if best else None,
                "confidence_score": confidence_score,
                "second_best_domain": second_best.domain if second_best else None,
                "second_best_score": round(second_best.score, 4) if second_best else None,
                "all_domain_scores": {item.domain: round(item.score, 4) for item in ranked},
                "action": action,
                "review_required": action != "AUTO_ASSIGN",
                "candidate_domain_name": candidate_domain_name,
                "final_domain": final_domain,
                "timestamp": timestamp,
                "explanation": explanation,
            }
            rows.append(row)

        self._append_audit_rows(rows)
        return {"run_id": run_id, "timestamp": timestamp, "results": rows, "count": len(rows)}

    def get_detection_results(self, limit: int = 50) -> dict:
        limit = max(1, min(int(limit), 500))
        all_rows = self._read_audit_rows()
        return {"results": all_rows[:limit], "count": min(limit, len(all_rows)), "total": len(all_rows)}

    def submit_review_decision(
        self,
        detection_run_id: str,
        dataset_name: str,
        reviewer_action: str,
        approved_domain: str | None = None,
        reviewer_note: str | None = None,
    ) -> dict:
        detection_run_id = str(detection_run_id or "").strip()
        dataset_name = str(dataset_name or "").strip()
        reviewer_action = str(reviewer_action or "").strip().upper()
        approved_domain = str(approved_domain or "").strip() or None
        reviewer_note = str(reviewer_note or "").strip() or None

        if not detection_run_id:
            raise ValueError("detection_run_id is required.")
        if not dataset_name:
            raise ValueError("dataset_name is required.")
        if not reviewer_action:
            raise ValueError("reviewer_action is required.")

        allowed_actions = {
            "APPROVE_ASSIGNMENT",
            "CHANGE_DOMAIN",
            "VALIDATE_CANDIDATE",
            "CREATE_DOMAIN_AFTER_APPROVAL",
            "RAISE_TICKET",
            "REJECT",
        }
        if reviewer_action not in allowed_actions:
            raise ValueError(f"Unsupported reviewer_action: {reviewer_action}")

        detection_record = self._find_detection_record(detection_run_id, dataset_name)
        if detection_record is None:
            raise ValueError("No matching detection record found for provided run and dataset.")

        ticket_required = reviewer_action == "RAISE_TICKET"
        ticket_status = "OPEN" if ticket_required else "NONE"
        ticket_id = None
        if ticket_required:
            ticket_id = f"TKT-{str(uuid.uuid4())[:8].upper()}"
            self._append_ticket(
                {
                    "ticket_id": ticket_id,
                    "dataset_name": dataset_name,
                    "candidate_domain_name": detection_record.get("candidate_domain_name"),
                    "reason": reviewer_note or "Raised from Silver-to-Domain review queue.",
                    "status": "OPEN",
                    "timestamp": datetime.now().isoformat(timespec="seconds"),
                }
            )

        decision = {
            "decision_id": str(uuid.uuid4())[:10],
            "detection_run_id": detection_run_id,
            "dataset_name": dataset_name,
            "original_action": detection_record.get("action"),
            "proposed_domain": detection_record.get("best_domain"),
            "candidate_domain_name": detection_record.get("candidate_domain_name"),
            "reviewer_action": reviewer_action,
            "approved_domain": approved_domain,
            "ticket_required": ticket_required,
            "ticket_status": ticket_status,
            "ticket_id": ticket_id,
            "reviewer_note": reviewer_note,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }
        if reviewer_action == "CREATE_DOMAIN_AFTER_APPROVAL":
            if not approved_domain:
                raise ValueError("approved_domain is required for CREATE_DOMAIN_AFTER_APPROVAL.")
            creation_result = self._create_domain_after_approval(
                dataset_name=dataset_name,
                approved_domain=approved_domain,
            )
            decision["domain_creation"] = creation_result
        self._append_review_decision(decision)
        return {"success": True, "decision": decision}

    def get_review_decisions(self) -> dict:
        rows = self._read_json_rows(self.review_decisions_path)
        return {"decisions": rows, "count": len(rows)}

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

    def remove_uploaded_test_files(self) -> dict:
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
        if self.review_decisions_path.exists():
            self.review_decisions_path.unlink(missing_ok=True)
        if self.review_tickets_path.exists():
            self.review_tickets_path.unlink(missing_ok=True)
        return {
            "success": True,
            "message": "Silver-to-domain detection/review history cleared.",
        }

    def reset_demo_state(self) -> dict:
        cleanup = self.remove_uploaded_test_files()
        history = self.clear_detection_history()
        return {
            "success": True,
            "message": "Demo state reset completed.",
            "cleanup": cleanup,
            "history": history,
        }

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

    def _rank_domains(
        self,
        csv_path: Path,
        dataset_columns: list[str],
        signatures: dict[str, dict[str, set[str]]],
    ) -> list[DomainScore]:
        dataset_set = set(dataset_columns)
        ranked: list[DomainScore] = []
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

            filename_score = self._filename_score(csv_path.stem, domain)
            confidence = (0.70 * column_score) + (0.30 * filename_score)
            ranked.append(
                DomainScore(
                    domain=domain,
                    score=float(confidence),
                    column_score=float(column_score),
                    filename_score=float(filename_score),
                    matched_columns=matched,
                    required_coverage=float(required_coverage),
                    optional_coverage=float(optional_coverage),
                )
            )

        ranked.sort(key=lambda item: item.score, reverse=True)
        return ranked

    def _filename_score(self, file_stem: str, domain_name: str) -> float:
        stem_tokens = self._tokenize(file_stem)
        domain_tokens = self._tokenize(domain_name.replace("_domain", ""))
        if not stem_tokens or not domain_tokens:
            return 0.0
        overlap = stem_tokens.intersection(domain_tokens)
        if overlap:
            return 1.0
        # Small keyword bridge for common naming variants.
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

        # Prefer explicit required columns that make domain identity clear.
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

    def _tokenize(self, value: str) -> set[str]:
        return {token for token in re.split(r"[^a-z0-9]+", str(value).lower()) if token}

    def _action_from_confidence(self, confidence: float) -> str:
        if confidence >= 0.7:
            return "AUTO_ASSIGN"
        if confidence >= 0.4:
            return "PROVISIONAL_ASSIGN"
        return "NEW_DOMAIN_CANDIDATE_PENDING_REVIEW"

    def _candidate_domain_name(self, dataset_name: str, columns_detected: list[str], ranked: list[DomainScore]) -> str:
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

    def _build_explanation(
        self,
        action: str,
        dataset_name: str,
        best: DomainScore | None,
        candidate_domain_name: str | None,
    ) -> str:
        if not best:
            return f"No confident domain match could be computed for {dataset_name}."

        pretty_domain = best.domain.replace("_domain", "").replace("_", " ").title()
        if best.matched_columns:
            sample_cols = ", ".join(best.matched_columns[:3])
            match_part = f"columns {sample_cols}"
        else:
            match_part = "filename similarity"
        scoring_part = (
            f"confidence={best.score:.4f} "
            f"(column={best.column_score:.4f}, filename={best.filename_score:.4f}; "
            f"required_cov={best.required_coverage:.2f}, optional_cov={best.optional_coverage:.2f})"
        )

        if action == "AUTO_ASSIGN":
            return f"Assigned to {pretty_domain} because {match_part} matched the {pretty_domain} signature; {scoring_part}."
        if action == "PROVISIONAL_ASSIGN":
            return f"Provisionally assigned to {pretty_domain}; {match_part} partially matched the {pretty_domain} signature; {scoring_part}."
        if action == "NEW_DOMAIN_CANDIDATE_PENDING_REVIEW":
            return (
                f"Detected as NEW_DOMAIN_CANDIDATE_PENDING_REVIEW ({candidate_domain_name}); {match_part} is not strong "
                f"enough for automatic domain creation, so governance review is required; {scoring_part}."
            )
        return (
            f"Detected as NEW_DOMAIN_CANDIDATE ({candidate_domain_name}) because {match_part} was not strong enough "
            f"for reliable assignment; {scoring_part}."
        )

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

    def _find_detection_record(self, detection_run_id: str, dataset_name: str) -> dict | None:
        rows = self._read_audit_rows()
        target_dataset = dataset_name.strip().lower()
        for row in rows:
            if str(row.get("run_id") or "") != detection_run_id:
                continue
            if str(row.get("dataset_name") or "").strip().lower() != target_dataset:
                continue
            return row
        return None

    def _read_json_rows(self, path: Path) -> list[dict]:
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        return []

    def _append_review_decision(self, decision: dict) -> None:
        self.review_decisions_path.parent.mkdir(parents=True, exist_ok=True)
        rows = self._read_json_rows(self.review_decisions_path)
        rows.insert(0, decision)
        self.review_decisions_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    def _append_ticket(self, ticket: dict) -> None:
        self.review_tickets_path.parent.mkdir(parents=True, exist_ok=True)
        rows = self._read_json_rows(self.review_tickets_path)
        rows.insert(0, ticket)
        self.review_tickets_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    def _create_domain_after_approval(self, dataset_name: str, approved_domain: str) -> dict:
        normalized_domain = str(approved_domain or "").strip().lower()
        if not normalized_domain.endswith("_domain"):
            normalized_domain = f"{normalized_domain}_domain"
        source = self.silver_dir / Path(dataset_name).name
        if not source.exists():
            raise ValueError(f"Source Silver dataset not found: {dataset_name}")

        target_folder = self.domain_products_dir / normalized_domain
        target_folder.mkdir(parents=True, exist_ok=True)
        target_file = target_folder / f"{normalized_domain}.csv"
        target_file.write_bytes(source.read_bytes())
        return {
            "created": True,
            "domain": normalized_domain,
            "domain_file": str(target_file),
            "source_dataset": str(source),
        }
