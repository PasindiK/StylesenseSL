from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[4]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from src.services.agentic_ai.component import AgenticSemanticFeatureOpsComponent


def main() -> None:
    component = AgenticSemanticFeatureOpsComponent()
    demo = component.recommend(
        query="show me a red dress for a party under 7000",
        user_id="demo-user",
        context={"time_of_day": 20, "device": "mobile"},
    )
    print(json.dumps(demo, indent=2, default=str))


if __name__ == "__main__":
    main()
