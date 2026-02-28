"""Workflow definitions and execution."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class WorkflowStep:
    """A step in a workflow."""

    step_id: str
    step_name: str
    step_function: Callable
    inputs: Dict[str, Any]
    depends_on: List[str]  # Step IDs this depends on


class Workflow:
    """A workflow composed of multiple steps."""

    def __init__(self, workflow_id: str, name: str, description: str = ""):
        """Initialize workflow.

        Args:
            workflow_id: Unique workflow ID
            name: Workflow name
            description: Workflow description
        """
        self.workflow_id = workflow_id
        self.name = name
        self.description = description
        self.steps: Dict[str, WorkflowStep] = {}
        self.step_order: List[str] = []

    def add_step(
        self,
        step_id: str,
        step_name: str,
        step_function: Callable,
        inputs: Optional[Dict[str, Any]] = None,
        depends_on: Optional[List[str]] = None,
    ) -> None:
        """Add a step to the workflow.

        Args:
            step_id: Unique step ID
            step_name: Human-readable step name
            step_function: Callable to execute
            inputs: Input parameters
            depends_on: List of step IDs this depends on
        """
        step = WorkflowStep(
            step_id=step_id,
            step_name=step_name,
            step_function=step_function,
            inputs=inputs or {},
            depends_on=depends_on or [],
        )
        self.steps[step_id] = step
        self.step_order.append(step_id)
        logger.info(f"Added step {step_id} to workflow {self.workflow_id}")

    def execute(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the workflow.

        Args:
            parameters: Execution parameters

        Returns:
            Dictionary with step results
        """
        results = {}
        executed = set()

        logger.info(f"Executing workflow: {self.workflow_id}")

        # Execute steps in order with dependency checking
        for step_id in self.step_order:
            step = self.steps[step_id]

            # Check dependencies
            if not all(dep in executed for dep in step.depends_on):
                raise RuntimeError(
                    f"Step {step_id} dependencies not satisfied: {step.depends_on}"
                )

            try:
                # Prepare inputs
                inputs = step.inputs.copy()
                inputs.update(parameters)

                # Execute step
                result = step.step_function(**inputs)
                results[step_id] = result
                executed.add(step_id)

                logger.info(f"Completed step: {step_id}")
            except Exception as e:
                logger.error(f"Failed step {step_id}: {e}")
                raise

        logger.info(f"Workflow {self.workflow_id} completed successfully")
        return results

    def get_dag(self) -> Dict[str, List[str]]:
        """Get the workflow DAG.

        Returns:
            Dictionary representing the DAG
        """
        dag = {}
        for step_id, step in self.steps.items():
            dag[step_id] = step.depends_on
        return dag

    def to_dict(self) -> Dict[str, Any]:
        """Convert workflow to dictionary."""
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "description": self.description,
            "steps": [
                {
                    "step_id": step.step_id,
                    "step_name": step.step_name,
                    "inputs": step.inputs,
                    "depends_on": step.depends_on,
                }
                for step in self.steps.values()
            ],
        }


class WorkflowExecutor:
    """Executes workflows with error handling and logging."""

    def __init__(self):
        """Initialize workflow executor."""
        self.execution_history: List[Dict] = []

    def execute(
        self, workflow: Workflow, parameters: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Execute a workflow.

        Args:
            workflow: Workflow to execute
            parameters: Execution parameters

        Returns:
            Execution results
        """
        parameters = parameters or {}

        try:
            results = workflow.execute(parameters)
            self.execution_history.append(
                {"workflow_id": workflow.workflow_id, "status": "success", "results": results}
            )
            return results
        except Exception as e:
            self.execution_history.append(
                {"workflow_id": workflow.workflow_id, "status": "failed", "error": str(e)}
            )
            raise

    def get_history(self, workflow_id: Optional[str] = None) -> List[Dict]:
        """Get execution history.

        Args:
            workflow_id: Optional filter by workflow ID

        Returns:
            List of execution records
        """
        if workflow_id:
            return [h for h in self.execution_history if h["workflow_id"] == workflow_id]
        return self.execution_history
