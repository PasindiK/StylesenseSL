"""Integration tests for data workflows."""

import pytest
from src.integration import WorkflowOrchestrator, Workflow


class TestWorkflowOrchestrator:
    """Tests for workflow orchestration."""

    def test_workflow_registration(self):
        """Test workflow registration."""
        orchestrator = WorkflowOrchestrator()

        workflow = Workflow(
            workflow_id="test_workflow",
            name="Test Workflow",
            description="Test workflow for unit testing",
        )

        orchestrator.register_workflow(workflow)

        assert "test_workflow" in orchestrator.workflows

    def test_workflow_execution(self):
        """Test workflow execution."""

        def sample_step(**kwargs):
            return {"result": "success"}

        orchestrator = WorkflowOrchestrator()
        workflow = Workflow(
            workflow_id="test_workflow",
            name="Test Workflow",
        )

        workflow.add_step(
            step_id="step_1",
            step_name="Sample Step",
            step_function=sample_step,
        )

        orchestrator.register_workflow(workflow)
        execution_id = orchestrator.execute_workflow("test_workflow")

        assert execution_id is not None
        execution = orchestrator.get_execution_status(execution_id)
        assert execution.status.value == "completed"

    def test_workflow_with_dependencies(self):
        """Test workflow with step dependencies."""

        def step_a(**kwargs):
            return {"data": [1, 2, 3]}

        def step_b(**kwargs):
            return {"processed": True}

        orchestrator = WorkflowOrchestrator()
        workflow = Workflow(
            workflow_id="test_workflow",
            name="Test Workflow",
        )

        workflow.add_step(
            step_id="step_a",
            step_name="Step A",
            step_function=step_a,
        )

        workflow.add_step(
            step_id="step_b",
            step_name="Step B",
            step_function=step_b,
            depends_on=["step_a"],
        )

        orchestrator.register_workflow(workflow)
        execution_id = orchestrator.execute_workflow("test_workflow")

        assert execution_id is not None
        execution = orchestrator.get_execution_status(execution_id)
        assert "step_a" in execution.step_results
        assert "step_b" in execution.step_results
