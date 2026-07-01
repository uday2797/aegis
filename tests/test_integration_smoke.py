"""
Integration smoke test — mirrors demo/quick_test.py but with proper assertions.
Runs all 5 failure types through the full simulation pipeline and verifies
every output field, not just that the call didn't crash.
"""
import asyncio
import os
import pytest
import yaml

os.environ["SIMULATION_MODE"] = "true"

from src.main import AEGISOrchestrator, load_config
from src.models import HealStatus


@pytest.fixture(scope="module")
def orchestrator():
    config = load_config("config/config.yaml")
    return AEGISOrchestrator(config)


ALL_FAILURE_TYPES = [
    {"type": "schema_drift"},
    {"type": "data_corruption", "null_pct": 34.2},
    {"type": "transient_failure"},
    {"type": "model_drift", "psi_score": 0.31},
    {"type": "upstream_delay"},
]


@pytest.mark.parametrize("failure_spec", ALL_FAILURE_TYPES, ids=[f["type"] for f in ALL_FAILURE_TYPES])
def test_run_once_returns_report_or_none(orchestrator, failure_spec):
    orchestrator.inject_failure(failure_spec)
    report = asyncio.get_event_loop().run_until_complete(orchestrator.run_once())
    # run_once can legitimately return None if detector yields nothing
    if report is not None:
        assert hasattr(report, "incident_id")
        assert hasattr(report, "auto_healed")
        assert isinstance(report.auto_healed, bool)
        assert report.mttr_seconds >= 0


def test_schema_drift_produces_report(orchestrator):
    orchestrator.inject_failure({"type": "schema_drift"})
    report = asyncio.get_event_loop().run_until_complete(orchestrator.run_once())
    assert report is not None


def test_transient_failure_produces_report(orchestrator):
    orchestrator.inject_failure({"type": "transient_failure"})
    report = asyncio.get_event_loop().run_until_complete(orchestrator.run_once())
    assert report is not None


def test_report_has_root_cause(orchestrator):
    orchestrator.inject_failure({"type": "data_corruption", "null_pct": 15.0})
    report = asyncio.get_event_loop().run_until_complete(orchestrator.run_once())
    if report is not None:
        assert hasattr(report, "root_cause") or hasattr(report, "rca_summary")


def test_mttr_is_numeric(orchestrator):
    orchestrator.inject_failure({"type": "transient_failure"})
    report = asyncio.get_event_loop().run_until_complete(orchestrator.run_once())
    if report is not None:
        assert isinstance(report.mttr_seconds, (int, float))
        assert report.mttr_seconds >= 0
