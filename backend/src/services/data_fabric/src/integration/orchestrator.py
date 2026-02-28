"""Workflow orchestration."""

from enum import Enum
from typing import Dict, List, Optional, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class WorkflowStatus(str, Enum):
    """Workflow execution status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowExecution:
    """Execution record for a workflow."""

    def __init__(self, workflow_id: str, execution_id: str):
        """Initialize workflow execution.

        Args:
            workflow_id: Workflow ID
            execution_id: Unique execution ID
        """
        self.workflow_id = workflow_id
        self.execution_id = execution_id
        self.status = WorkflowStatus.PENDING
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.step_results: Dict[str, Any] = {}
        self.error_message: Optional[str] = None

    def start(self) -> None:
        """Mark execution as started."""
        self.status = WorkflowStatus.RUNNING
        self.started_at = datetime.now()

    def complete(self) -> None:
        """Mark execution as completed."""
        self.status = WorkflowStatus.COMPLETED
        self.completed_at = datetime.now()

    def fail(self, error: str) -> None:
        """Mark execution as failed.

        Args:
            error: Error message
        """
        self.status = WorkflowStatus.FAILED
        self.completed_at = datetime.now()
        self.error_message = error

    def get_duration(self) -> Optional[float]:
        """Get execution duration in seconds."""
        if not self.started_at or not self.completed_at:
            return None
        return (self.completed_at - self.started_at).total_seconds()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "workflow_id": self.workflow_id,
            "execution_id": self.execution_id,
            "status": self.status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.get_duration(),
            "error_message": self.error_message,
            "step_results": self.step_results,
        }


class WorkflowOrchestrator:
    """Orchestrates workflow execution."""

    def __init__(self):
        """Initialize orchestrator."""
        self.workflows: Dict[str, "Workflow"] = {}
        self.executions: Dict[str, WorkflowExecution] = {}
        self.execution_counter = 0

    def register_workflow(self, workflow: "Workflow") -> None:
        """Register a workflow.

        Args:
            workflow: Workflow to register
        """
        self.workflows[workflow.workflow_id] = workflow
        logger.info(f"Registered workflow: {workflow.workflow_id}")

    def execute_workflow(self, workflow_id: str, parameters: Optional[Dict] = None) -> str:
        """Execute a workflow.

        Args:
            workflow_id: Workflow ID
            parameters: Execution parameters

        Returns:
            Execution ID
        """
        if workflow_id not in self.workflows:
            raise ValueError(f"Workflow {workflow_id} not found")

        self.execution_counter += 1
        execution_id = f"{workflow_id}_{self.execution_counter}"
        execution = WorkflowExecution(workflow_id, execution_id)

        self.executions[execution_id] = execution
        workflow = self.workflows[workflow_id]

        execution.start()
        logger.info(f"Started execution: {execution_id}")

        try:
            execution.step_results = workflow.execute(parameters or {})
            execution.complete()
            logger.info(f"Completed execution: {execution_id}")
        except Exception as e:
            execution.fail(str(e))
            logger.error(f"Failed execution {execution_id}: {e}")

        return execution_id

    def get_execution_status(self, execution_id: str) -> Optional[WorkflowExecution]:
        """Get execution status.

        Args:
            execution_id: Execution ID

        Returns:
            WorkflowExecution or None
        """
        return self.executions.get(execution_id)

    def cancel_execution(self, execution_id: str) -> bool:
        """Cancel an execution.

        Args:
            execution_id: Execution ID

        Returns:
            True if cancelled
        """
        execution = self.executions.get(execution_id)
        if execution and execution.status == WorkflowStatus.RUNNING:
            execution.status = WorkflowStatus.CANCELLED
            logger.info(f"Cancelled execution: {execution_id}")
            return True
        return False

    def list_executions(self, workflow_id: Optional[str] = None) -> List[WorkflowExecution]:
        """List executions.

        Args:
            workflow_id: Optional filter by workflow ID

        Returns:
            List of executions
        """
        executions = list(self.executions.values())
        if workflow_id:
            executions = [e for e in executions if e.workflow_id == workflow_id]
        return executions

    def get_statistics(self) -> Dict[str, Any]:
        """Get orchestrator statistics."""
        executions = list(self.executions.values())
        completed = [e for e in executions if e.status == WorkflowStatus.COMPLETED]
        failed = [e for e in executions if e.status == WorkflowStatus.FAILED]

        avg_duration = None
        if completed:
            durations = [e.get_duration() for e in completed if e.get_duration()]
            if durations:
                avg_duration = sum(durations) / len(durations)

        return {
            "total_workflows": len(self.workflows),
            "total_executions": len(self.executions),
            "completed_executions": len(completed),
            "failed_executions": len(failed),
            "average_duration_seconds": avg_duration,
        }
