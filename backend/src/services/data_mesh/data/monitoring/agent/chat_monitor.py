"""CLI chat interface for pipeline monitoring.

No external APIs are used; intent handling is keyword-based.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

from pipeline_monitoring_agent import PipelineMonitoringAgent


class PipelineChatInterface:
    """Simple chat interface to ask log-based questions."""

    def __init__(self, agent: PipelineMonitoringAgent) -> None:
        self.agent = agent

    def answer(self, question: str) -> str:
        """Return a response for a user query."""
        q = question.lower().strip()
        report = self.agent.compute_health_report()

        if "today" in q or "latest" in q or "how was" in q or "pipeline run" in q:
            return (
                f"Latest pipeline status: {report['latest_run_status']}. "
                f"Domains processed: {report.get('domains_processed', 0)}. "
                f"Total rows: {report['total_rows_processed']}. "
                f"Execution time: {report['execution_time_seconds']} seconds. "
                f"Overall health: {report['health_classification']} (score {report['health_score']})."
            )

        if "fail" in q or "error" in q:
            if report["failure_rate_percent"] == 0:
                return "No domain failures detected in the latest run."
            return (
                f"Failures detected. Failure rate is {report['failure_rate_percent']}%. "
                f"Alerts: {'; '.join(report['alerts'])}."
            )

        if "row" in q or "record" in q:
            return f"Total rows processed in the latest run: {report['total_rows_processed']}."

        if "time" in q or "duration" in q or "execution" in q:
            return (
                f"Latest execution time is {report['execution_time_seconds']} seconds. "
                f"Threshold is {self.agent.execution_time_threshold_seconds} seconds."
            )

        if "health" in q or "score" in q or "status" in q:
            return (
                f"Health is {report['health_classification']} with score {report['health_score']}. "
                f"Latest status: {report['latest_run_status']}."
            )

        if "trend" in q or "last 5" in q or "history" in q:
            trend = report.get("trend_last_5_runs", [])
            if not trend:
                return "No run trend data available yet."
            trend_text = ", ".join(
                f"{item['run_id']}: {item['status']} ({item['execution_time_seconds']}s)"
                for item in trend
            )
            return f"Last runs: {trend_text}."

        return (
            "Ask about: latest pipeline run, failures, rows processed, execution time, health score, "
            "or trend for last 5 runs."
        )

    def run(self) -> None:
        """Run interactive terminal chat loop."""
        print("Pipeline Monitoring Chat")
        print("Type 'exit' to quit.\n")
        while True:
            user_input = input("You: ").strip()
            if not user_input:
                continue
            if user_input.lower() in {"exit", "quit", "q"}:
                print("Agent: Goodbye.")
                break
            print(f"Agent: {self.answer(user_input)}")


if __name__ == "__main__":
    monitoring_dir = Path(__file__).resolve().parents[1]
    agent = PipelineMonitoringAgent(
        log_path=monitoring_dir / "logs" / "pipeline_log.json",
        report_path=monitoring_dir / "logs" / "pipeline_health_report.json",
    )
    PipelineChatInterface(agent).run()
