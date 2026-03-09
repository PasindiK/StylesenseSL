from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
import sys

from date_rebase_utility import BusinessDateRebaseUtility
from governance_intelligence import GovernanceIntelligenceEngine
from importlib.util import module_from_spec, spec_from_file_location


def _load_reload_pipeline_class(data_root: Path):
    module_path = data_root / "monitoring" / "pipelines" / "reload_data_mesh_pipeline.py"
    spec = spec_from_file_location("reload_data_mesh_pipeline", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load pipeline module from {module_path}")
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.DataMeshReloadPipeline


def _run_silver_only_rebase(data_root: Path) -> dict[str, Any]:
    utility = BusinessDateRebaseUtility(data_root=data_root)
    utility.targets = [data_root / "Data" / "Silver-data"]
    return utility.run(apply_changes=True)


def _run_mesh_reload_pipeline(data_root: Path) -> dict[str, Any]:
    pipeline_class = _load_reload_pipeline_class(data_root)
    pipeline = pipeline_class(
        silver_path=data_root / "Data" / "Silver-data",
        domain_path=data_root / "Data_Mesh_Domains",
        log_path=data_root / "monitoring" / "logs" / "pipeline_log.json",
    )
    return pipeline.run_once()


def _refresh_governance(data_root: Path) -> dict[str, Any]:
    engine = GovernanceIntelligenceEngine(
        data_path=data_root / "Data_Mesh_Domains",
        monitoring_history_path=data_root / "monitoring" / "domain_health_history.csv",
    )
    summary = engine.governance_summary()
    domains = summary.get("domains", [])

    refresh_rows: list[dict[str, str]] = []
    governance_eval_times: list[str] = []
    for domain in domains:
        domain_name = str(domain.get("domain_name") or "")
        if not domain_name:
            continue
        detail = engine.governance_domain(domain_name)
        latest_refresh = str(detail.get("latest_domain_refresh_time") or "Not available for this domain")
        latest_eval = str(detail.get("latest_governance_evaluation_time") or "")
        if latest_eval:
            governance_eval_times.append(latest_eval)
        refresh_rows.append(
            {
                "domain_name": domain_name,
                "latest_domain_refresh_time": latest_refresh,
            }
        )

    latest_governance_eval = max(governance_eval_times) if governance_eval_times else "Not available"
    return {
        "domains": refresh_rows,
        "latest_governance_evaluation_time": latest_governance_eval,
    }


def run_workflow() -> dict[str, Any]:
    base_dir = Path(__file__).resolve().parent.parent
    data_root = base_dir / "data"

    rebase_result = _run_silver_only_rebase(data_root)
    pipeline_result = _run_mesh_reload_pipeline(data_root)
    governance_result = _refresh_governance(data_root)

    return {
        "workflow": "Synthetic Data Time Alignment + Governance Refresh",
        "executed_at": datetime.now().isoformat(timespec="seconds"),
        "rebase": rebase_result,
        "pipeline": pipeline_result,
        "governance": governance_result,
    }


def print_summary(result: dict[str, Any]) -> None:
    print("\n=== Synthetic Data Time Alignment Workflow ===")
    print(f"Executed at: {result.get('executed_at')}")

    rebase = result.get("rebase", {})
    print("\n1) Silver Rebase")
    print(f"Status: {rebase.get('status')}")
    print(f"Files changed: {rebase.get('files_changed', 0)}")
    print("Rebased Silver files:")
    for item in rebase.get("results", []):
        print(f"- {item.get('file')}")

    pipeline = result.get("pipeline", {})
    print("\n2) Silver → Data Mesh Pipeline")
    print(f"Run ID: {pipeline.get('run_id')}")
    print(f"Status: {pipeline.get('status')}")
    print(f"Failed domains: {pipeline.get('failed_domains') or []}")

    governance = result.get("governance", {})
    print("\n3) Governance Refresh")
    print(f"Latest governance evaluation time: {governance.get('latest_governance_evaluation_time')}")
    print("Latest domain refresh times:")
    for row in governance.get("domains", []):
        print(f"- {row.get('domain_name')}: {row.get('latest_domain_refresh_time')}")

    print("\n4) Expected effect")
    print("- Freshness and time-related outputs should update after rebasing + pipeline reload.")
    print("- Volume/distribution instability may remain similar if underlying numeric values did not change.")


if __name__ == "__main__":
    summary = run_workflow()
    print_summary(summary)
