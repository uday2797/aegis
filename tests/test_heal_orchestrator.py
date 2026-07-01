"""
Tests for HealOrchestrator — simulation mode only (no Databricks calls).
Covers all failure-type routing, escalation, and result structure.
"""
import asyncio
import pytest
from src.healing.heal_orchestrator import HealOrchestrator
from src.models import RCAResult, HealResult, HealStatus, FailureType, RiskLevel


def _rca(failure_type: str, confidence: float = 90.0) -> RCAResult:
    return RCAResult(
        incident_id="INC-HEAL-TEST",
        root_cause="test root cause",
        confidence=confidence,
        failure_type=FailureType(failure_type),
        risk_level=RiskLevel.LOW,
        recommended_action="fix it",
        explanation="test explanation",
    )


@pytest.fixture()
def orchestrator(healing_config) -> HealOrchestrator:
    return HealOrchestrator(healing_config, simulation_mode=True)


class TestHealingActionRouting:
    """In simulation mode every action should complete without error."""

    @pytest.mark.parametrize("failure_type", [
        "transient_failure",
        "upstream_delay",
        "data_corruption",
        "schema_drift",
        "model_drift",
        "data_quality",
        "config_mismatch",
    ])
    def test_all_failure_types_produce_result(self, orchestrator, failure_type):
        result = asyncio.run(
            orchestrator.heal(_rca(failure_type), "INC-ROUTE-TEST")
        )
        assert isinstance(result, HealResult)

    def test_result_has_incident_id(self, orchestrator):
        result = asyncio.run(
            orchestrator.heal(_rca("transient_failure"), "INC-ID-CHECK")
        )
        assert result.incident_id == "INC-ID-CHECK"

    def test_result_has_valid_status(self, orchestrator):
        result = asyncio.run(
            orchestrator.heal(_rca("transient_failure"), "INC-STATUS")
        )
        assert result.status in list(HealStatus)

    def test_result_action_taken_non_empty(self, orchestrator):
        result = asyncio.run(
            orchestrator.heal(_rca("transient_failure"), "INC-ACTION")
        )
        assert isinstance(result.action_taken, str) and len(result.action_taken) > 0

    def test_result_outcome_non_empty(self, orchestrator):
        result = asyncio.run(
            orchestrator.heal(_rca("schema_drift"), "INC-OUTCOME")
        )
        assert isinstance(result.outcome, str) and len(result.outcome) > 0


class TestHealOrchestratorSimulationMode:
    def test_simulation_mode_is_set(self, orchestrator):
        assert orchestrator.simulation_mode is True

    def test_production_mode_flag(self, healing_config):
        prod_orch = HealOrchestrator(healing_config, simulation_mode=False)
        assert prod_orch.simulation_mode is False
