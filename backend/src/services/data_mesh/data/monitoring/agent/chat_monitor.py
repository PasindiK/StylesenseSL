"""CLI chat interface for conversational pipeline monitoring."""

from __future__ import annotations

from pathlib import Path
import importlib.util
import sys
from typing import Any

DATA_MESH_SRC = Path(__file__).resolve().parents[3] / "src"
if str(DATA_MESH_SRC) not in sys.path:
    sys.path.append(str(DATA_MESH_SRC))


def _load_agent_class() -> Any:
    module_path = DATA_MESH_SRC / "pipeline_conversational_agent.py"
    spec = importlib.util.spec_from_file_location("pipeline_conversational_agent", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load pipeline_conversational_agent module.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.PipelineConversationalAgent


PipelineConversationalAgent = _load_agent_class()


class PipelineChatInterface:
    """Interactive chat interface backed by conversational monitoring agent."""

    def __init__(self, agent: Any) -> None:
        self.agent = agent

    def answer(self, question: str) -> str:
        """Return a conversational response for any user query."""
        result = self.agent.answer(question)
        return str(result.get("answer", "No response available."))

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
    data_root = Path(__file__).resolve().parents[2]
    agent = PipelineConversationalAgent(data_root=data_root)
    PipelineChatInterface(agent).run()
