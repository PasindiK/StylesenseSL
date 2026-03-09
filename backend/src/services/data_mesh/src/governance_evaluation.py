from __future__ import annotations

import json
from pathlib import Path

try:
    from .governance_intelligence import GovernanceIntelligenceEngine
except ImportError:
    from governance_intelligence import GovernanceIntelligenceEngine


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_ROOT = BASE_DIR / "data"
DATA_PATH = DATA_ROOT / "Data_Mesh_Domains"
MONITORING_HISTORY_PATH = DATA_ROOT / "monitoring" / "domain_health_history.csv"


def run_adgri_evaluation(domain_name: str = "sales_domain") -> dict:
    engine = GovernanceIntelligenceEngine(
        data_path=DATA_PATH,
        monitoring_history_path=MONITORING_HISTORY_PATH,
    )
    return engine.evaluate_domain_scenarios(domain_name)


if __name__ == "__main__":
    output = run_adgri_evaluation("sales_domain")
    print("=== ADGRI Scenario Evaluation ===")
    print(json.dumps(output, indent=2))
