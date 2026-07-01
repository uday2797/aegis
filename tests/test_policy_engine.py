"""
Tests for PolicyEngine — all 4 decision branches, zero external dependencies.
"""
import pytest
from src.healing.policy_engine import PolicyEngine
from src.models import RCAResult, FailureType, RiskLevel


def _rca(confidence: float, risk: str, failure_type: str = "transient_failure") -> RCAResult:
    return RCAResult(
        incident_id="INC-TEST",
        root_cause="test cause",
        confidence=confidence,
        failure_type=FailureType(failure_type),
        risk_level=RiskLevel(risk),
        recommended_action="fix it",
        explanation="test",
    )


@pytest.fixture()
def engine(policy_config) -> PolicyEngine:
    return PolicyEngine(policy_config)


# ── Rule 1: confidence too low → always escalate ─────────────────────────────

class TestLowConfidence:
    def test_very_low_confidence_escalates(self, engine):
        ok, reason = engine.should_auto_heal(_rca(confidence=30, risk="low"))
        assert ok is False
        assert "60%" in reason or "threshold" in reason.lower()

    def test_exactly_at_floor_escalates(self, engine):
        ok, _ = engine.should_auto_heal(_rca(confidence=59.9, risk="low"))
        assert ok is False

    def test_boundary_60_passes_for_low_risk(self, engine):
        ok, _ = engine.should_auto_heal(_rca(confidence=60, risk="low"))
        assert ok is True


# ── Rule 2: high risk → always escalate regardless of confidence ──────────────

class TestHighRisk:
    def test_high_risk_100pct_confidence_still_escalates(self, engine):
        ok, reason = engine.should_auto_heal(_rca(confidence=100, risk="high"))
        assert ok is False
        assert "high" in reason.lower() or "human" in reason.lower()

    def test_high_risk_medium_confidence_escalates(self, engine):
        ok, _ = engine.should_auto_heal(_rca(confidence=70, risk="high"))
        assert ok is False


# ── Rule 3: medium risk — need high confidence (≥ auto_heal_confidence_min) ──

class TestMediumRisk:
    def test_medium_risk_high_confidence_heals(self, engine, policy_config):
        threshold = policy_config["auto_heal_confidence_min"]
        ok, reason = engine.should_auto_heal(_rca(confidence=threshold, risk="medium"))
        assert ok is True
        assert "medium" in reason.lower() or "approve" in reason.lower()

    def test_medium_risk_below_threshold_escalates(self, engine, policy_config):
        threshold = policy_config["auto_heal_confidence_min"]
        ok, _ = engine.should_auto_heal(_rca(confidence=threshold - 1, risk="medium"))
        assert ok is False

    def test_medium_risk_exactly_at_threshold_heals(self, engine, policy_config):
        threshold = policy_config["auto_heal_confidence_min"]
        ok, _ = engine.should_auto_heal(_rca(confidence=float(threshold), risk="medium"))
        assert ok is True


# ── Rule 4: low risk — auto-heal if confidence ≥ 60 ─────────────────────────

class TestLowRisk:
    def test_low_risk_sufficient_confidence_heals(self, engine):
        ok, reason = engine.should_auto_heal(_rca(confidence=75, risk="low"))
        assert ok is True
        assert "low" in reason.lower() or "approve" in reason.lower()

    def test_low_risk_insufficient_confidence_escalates(self, engine):
        ok, _ = engine.should_auto_heal(_rca(confidence=55, risk="low"))
        assert ok is False


# ── Return type contract ─────────────────────────────────────────────────────

def test_return_is_tuple_bool_str(engine):
    result = engine.should_auto_heal(_rca(confidence=80, risk="low"))
    assert isinstance(result, tuple) and len(result) == 2
    ok, reason = result
    assert isinstance(ok, bool)
    assert isinstance(reason, str) and len(reason) > 0
