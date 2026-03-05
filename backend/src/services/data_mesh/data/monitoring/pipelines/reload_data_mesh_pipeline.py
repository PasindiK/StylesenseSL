"""Data Mesh reload pipeline.

Refactors the notebook-based domain reload process into a reusable local pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import os
import shutil
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

import pandas as pd


@dataclass
class DomainExecutionResult:
    """Execution result for one domain copy step."""

    timestamp: str
    run_id: str
    domain: str
    rows_processed: int
    start_time: str
    end_time: str
    execution_time_seconds: float
    status: str
    error: Optional[str]

    def to_dict(self) -> Dict[str, object]:
        return {
            "timestamp": self.timestamp,
            "run_id": self.run_id,
            "domain": self.domain,
            "rows_processed": self.rows_processed,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "execution_time_seconds": self.execution_time_seconds,
            "status": self.status,
            "error": self.error,
        }


class DataMeshReloadPipeline:
    """Reload Data Mesh domain CSVs from silver layer and write execution logs."""

    def __init__(
        self,
        silver_path: Optional[Path] = None,
        domain_path: Optional[Path] = None,
        log_path: Optional[Path] = None,
    ) -> None:
        base_data_dir = Path(__file__).resolve().parents[2]
        self.silver_path = silver_path or base_data_dir / "Data" / "Silver-data"
        self.domain_path = domain_path or base_data_dir / "Data_Mesh_Domains"
        self.log_path = log_path or base_data_dir / "monitoring" / "logs" / "pipeline_log.json"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

        self.mapping = {
            "users_clean.csv": "users_domain/users_domain.csv",
            "products_clean.csv": "product_domain/product_domain.csv",
            "shops_clean.csv": "shop_domain/shop_domain.csv",
            "transactions_clean.csv": "sales_domain/sales_domain.csv",
            "trends_clean.csv": "engagement_domain/engagement_domain.csv",
            "users_preferences_clean.csv": "user_preferences_domain/user_preferences_domain.csv",
            "interactions_clean.csv": "Interaction_domain/interaction_domain.csv",
        }

    def run_once(self, progress_callback: Optional[Callable[[Dict[str, object]], None]] = None) -> Dict[str, object]:
        """Execute one full reload cycle and append per-domain logs to JSON."""
        run_id = datetime.now().strftime("%Y%m%d%H%M%S")
        run_timestamp = datetime.now().isoformat(timespec="seconds")
        results: List[DomainExecutionResult] = []
        total_domains = len(self.mapping)
        completed_domains = 0
        rows_processed_cumulative = 0

        for source_file, destination_relative in self.mapping.items():
            source_path = self.silver_path / source_file
            destination_path = self.domain_path / destination_relative
            domain_name = destination_relative.split("/")[0]
            started = datetime.now()
            started_epoch = time.perf_counter()

            if not source_path.exists():
                finished = datetime.now()
                results.append(
                    DomainExecutionResult(
                        timestamp=run_timestamp,
                        run_id=run_id,
                        domain=domain_name,
                        rows_processed=0,
                        start_time=started.isoformat(timespec="seconds"),
                        end_time=finished.isoformat(timespec="seconds"),
                        execution_time_seconds=round(time.perf_counter() - started_epoch, 4),
                        status="FAILED",
                        error=f"Missing source file: {source_path}",
                    )
                )
                completed_domains += 1
                if progress_callback:
                    progress_callback(
                        {
                            "run_id": run_id,
                            "domain": domain_name,
                            "status": "FAILED",
                            "rows_processed_cumulative": rows_processed_cumulative,
                            "domains_completed": completed_domains,
                            "total_domains": total_domains,
                            "progress_percent": round((completed_domains / total_domains) * 100, 2),
                        }
                    )
                continue

            try:
                df = pd.read_csv(source_path)
                destination_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, destination_path)
                os.utime(destination_path, None)
                finished = datetime.now()
                results.append(
                    DomainExecutionResult(
                        timestamp=run_timestamp,
                        run_id=run_id,
                        domain=domain_name,
                        rows_processed=int(len(df)),
                        start_time=started.isoformat(timespec="seconds"),
                        end_time=finished.isoformat(timespec="seconds"),
                        execution_time_seconds=round(time.perf_counter() - started_epoch, 4),
                        status="SUCCESS",
                        error=None,
                    )
                )
                completed_domains += 1
                rows_processed_cumulative += int(len(df))
                if progress_callback:
                    progress_callback(
                        {
                            "run_id": run_id,
                            "domain": domain_name,
                            "status": "SUCCESS",
                            "rows_processed_cumulative": rows_processed_cumulative,
                            "domains_completed": completed_domains,
                            "total_domains": total_domains,
                            "progress_percent": round((completed_domains / total_domains) * 100, 2),
                        }
                    )
            except Exception as exc:  # pylint: disable=broad-except
                finished = datetime.now()
                results.append(
                    DomainExecutionResult(
                        timestamp=run_timestamp,
                        run_id=run_id,
                        domain=domain_name,
                        rows_processed=0,
                        start_time=started.isoformat(timespec="seconds"),
                        end_time=finished.isoformat(timespec="seconds"),
                        execution_time_seconds=round(time.perf_counter() - started_epoch, 4),
                        status="FAILED",
                        error=str(exc),
                    )
                )
                completed_domains += 1
                if progress_callback:
                    progress_callback(
                        {
                            "run_id": run_id,
                            "domain": domain_name,
                            "status": "FAILED",
                            "rows_processed_cumulative": rows_processed_cumulative,
                            "domains_completed": completed_domains,
                            "total_domains": total_domains,
                            "progress_percent": round((completed_domains / total_domains) * 100, 2),
                        }
                    )

        self._append_logs([result.to_dict() for result in results])

        total_rows = sum(item.rows_processed for item in results)
        total_duration = round(sum(item.execution_time_seconds for item in results), 4)
        failed_domains = [item.domain for item in results if item.status == "FAILED"]

        return {
            "run_id": run_id,
            "timestamp": run_timestamp,
            "domains_processed": len(results),
            "total_rows_processed": total_rows,
            "total_execution_time_seconds": total_duration,
            "failed_domains": failed_domains,
            "status": "SUCCESS" if not failed_domains else "PARTIAL_FAILURE",
            "log_path": str(self.log_path),
        }

    def _append_logs(self, records: List[Dict[str, object]]) -> None:
        """Append records to pipeline_log.json safely."""
        existing = self._read_logs()
        existing.extend(records)
        self.log_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")

    def _read_logs(self) -> List[Dict[str, object]]:
        """Read existing pipeline logs."""
        if not self.log_path.exists():
            return []
        content = self.log_path.read_text(encoding="utf-8").strip()
        if not content:
            return []
        try:
            parsed = json.loads(content)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []


if __name__ == "__main__":
    pipeline = DataMeshReloadPipeline()
    summary = pipeline.run_once()
    print("Pipeline run complete:")
    print(json.dumps(summary, indent=2))
