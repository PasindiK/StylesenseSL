"""Pipeline monitoring agent for Data Mesh pipeline logs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from statistics import mean
from typing import Dict, List, Optional


@dataclass
class RunSummary:
    """Aggregated details for a single pipeline run."""

    run_id: str
    timestamp: str
    domains_processed: int
    total_rows_processed: int
    total_execution_time_seconds: float
    failed_domains: int
    failure_rate_percent: float
    status: str


class PipelineMonitoringAgent:
    """Compute health and monitoring summaries from pipeline_log.json."""

    def __init__(
        self,
        log_path: Optional[Path] = None,
        report_path: Optional[Path] = None,
        execution_time_threshold_seconds: float = 20.0,
    ) -> None:
        monitoring_dir = Path(__file__).resolve().parents[1]
        self.log_path = log_path or monitoring_dir / "logs" / "pipeline_log.json"
        self.report_path = report_path or monitoring_dir / "logs" / "pipeline_health_report.json"
        self.execution_time_threshold_seconds = execution_time_threshold_seconds

    def load_logs(self) -> List[Dict[str, object]]:
        """Load all pipeline log entries from JSON."""
        if not self.log_path.exists():
            return []
        content = self.log_path.read_text(encoding="utf-8").strip()
        if not content:
            return []
        try:
            data = json.loads(content)
            return data if isinstance(data, list) else []
        except json.JSONDecodeError:
            return []

    def latest_run_summary(self) -> Optional[RunSummary]:
        """Return summary for the latest run."""
        summaries = self._all_run_summaries()
        return summaries[-1] if summaries else None

    def _all_run_summaries(self) -> List[RunSummary]:
        logs = self.load_logs()
        if not logs:
            return []

        grouped: Dict[str, List[Dict[str, object]]] = {}
        for record in logs:
            run_id = str(record.get("run_id") or str(record.get("timestamp", ""))[:16])
            grouped.setdefault(run_id, []).append(record)

        run_summaries: List[RunSummary] = []
        for run_id, records in grouped.items():
            domains_processed = len(records)
            total_rows = int(sum(int(item.get("rows_processed", 0) or 0) for item in records))
            total_duration = float(sum(float(item.get("execution_time_seconds", 0.0) or 0.0) for item in records))
            failed = sum(1 for item in records if str(item.get("status", "")).upper() != "SUCCESS")
            failure_rate = (failed / domains_processed * 100.0) if domains_processed else 0.0
            latest_timestamp = max(str(item.get("timestamp", "")) for item in records)

            if failed == 0:
                status = "SUCCESS"
            elif failed == domains_processed:
                status = "FAILED"
            else:
                status = "PARTIAL_FAILURE"

            run_summaries.append(
                RunSummary(
                    run_id=run_id,
                    timestamp=latest_timestamp,
                    domains_processed=domains_processed,
                    total_rows_processed=total_rows,
                    total_execution_time_seconds=round(total_duration, 4),
                    failed_domains=failed,
                    failure_rate_percent=round(failure_rate, 2),
                    status=status,
                )
            )

        run_summaries.sort(key=lambda item: item.timestamp)
        return run_summaries

    def compute_health_report(self) -> Dict[str, object]:
        """Compute health score, classification, trends, and alerts."""
        latest = self.latest_run_summary()
        summaries = self._all_run_summaries()

        if not latest:
            report = {
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "latest_run_status": "NO_DATA",
                "total_rows_processed": 0,
                "execution_time_seconds": 0.0,
                "failure_rate_percent": 0.0,
                "health_score": 0,
                "health_classification": "Critical",
                "trend_last_5_runs": [],
                "alerts": ["No pipeline runs found."],
            }
            self._write_report(report)
            return report

        score = 0

        if latest.status == "SUCCESS":
            score += 50

        if latest.total_execution_time_seconds < self.execution_time_threshold_seconds:
            score += 20

        if latest.total_rows_processed > 0:
            score += 20

        last_five = summaries[-5:]
        has_recent_failures = any(item.failed_domains > 0 for item in last_five)
        if not has_recent_failures:
            score += 10

        if score >= 80:
            classification = "Healthy"
        elif score >= 50:
            classification = "Warning"
        else:
            classification = "Critical"

        alerts: List[str] = []
        if latest.failed_domains > 0:
            alerts.append(f"{latest.failed_domains} domain(s) failed in the latest run.")

        trend_analysis = [
            {
                "run_id": run.run_id,
                "timestamp": run.timestamp,
                "status": run.status,
                "rows_processed": run.total_rows_processed,
                "execution_time_seconds": run.total_execution_time_seconds,
                "failure_rate_percent": run.failure_rate_percent,
            }
            for run in last_five
        ]

        if len(last_five) >= 2:
            baseline = mean(item.total_execution_time_seconds for item in last_five[:-1])
            if baseline > 0:
                increase_ratio = (latest.total_execution_time_seconds - baseline) / baseline
                if increase_ratio >= 0.3:
                    alerts.append(
                        "Execution time increased significantly compared with recent runs "
                        f"({increase_ratio * 100:.1f}% higher)."
                    )

        if not alerts:
            alerts.append("No critical alerts.")

        report = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "latest_run_status": latest.status,
            "domains_processed": latest.domains_processed,
            "total_rows_processed": latest.total_rows_processed,
            "execution_time_seconds": latest.total_execution_time_seconds,
            "failure_rate_percent": latest.failure_rate_percent,
            "health_score": score,
            "health_classification": classification,
            "trend_last_5_runs": trend_analysis,
            "alerts": alerts,
        }

        self._write_report(report)
        return report

    def console_summary(self) -> str:
        """Return a human-readable summary for terminal display."""
        report = self.compute_health_report()
        lines = [
            "=== Pipeline Monitoring Summary ===",
            f"Generated At         : {report['generated_at']}",
            f"Latest Run Status    : {report['latest_run_status']}",
            f"Domains Processed    : {report.get('domains_processed', 0)}",
            f"Total Rows Processed : {report['total_rows_processed']}",
            f"Execution Time (sec) : {report['execution_time_seconds']}",
            f"Failure Rate (%)     : {report['failure_rate_percent']}",
            f"Health Score         : {report['health_score']}",
            f"Health Classification: {report['health_classification']}",
            f"Alerts               : {'; '.join(report['alerts'])}",
        ]
        return "\n".join(lines)

    def _write_report(self, report: Dict[str, object]) -> None:
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        self.report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    agent = PipelineMonitoringAgent()
    print(agent.console_summary())
