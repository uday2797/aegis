"""
Tests for IncidentKnowledgeStore — store/retrieve cycle, in-memory fallback.
Uses a tmp_path so the real ./data/knowledge_store is never modified.
"""
import asyncio
import pytest
from datetime import datetime, timezone

from src.knowledge.incident_store import IncidentKnowledgeStore
from src.models import (
    DetectedIncident,
    RCAResult,
    HealResult,
    FailureType,
    RiskLevel,
    HealStatus,
    IncidentStatus,
)


def _incident(job_name: str = "test_job") -> DetectedIncident:
    return DetectedIncident(
        incident_id="INC-STORE-001",
        job_name=job_name,
        failure_type=FailureType.TRANSIENT_FAILURE,
        error_summary="NullPointerException in column 'price'",
        error_logs="Full stack trace here",
        timestamp=datetime.now(tz=timezone.utc),
        status=IncidentStatus.RESOLVED,
    )


def _rca() -> RCAResult:
    return RCAResult(
        incident_id="INC-STORE-001",
        root_cause="Column 'price' contains null values",
        confidence=90.0,
        failure_type=FailureType.DATA_QUALITY,
        risk_level=RiskLevel.LOW,
        recommended_action="Add null filter",
        explanation="Null check missing",
    )


def _heal() -> HealResult:
    return HealResult(
        incident_id="INC-STORE-001",
        status=HealStatus.AUTO_HEALED,
        action_taken="Added null filter before aggregation",
        outcome="Job completed successfully",
    )


@pytest.fixture()
def store(tmp_path) -> IncidentKnowledgeStore:
    config = {
        "persist_dir": str(tmp_path / "knowledge_store"),
        "collection_name": "test_incidents",
    }
    return IncidentKnowledgeStore(config)


class TestStoreAndRetrieve:
    def test_store_does_not_raise(self, store):
        asyncio.run(
            store.store(_incident(), _rca(), _heal())
        )

    def test_find_similar_returns_list(self, store):
        asyncio.run(
            store.store(_incident(), _rca(), _heal())
        )
        results = asyncio.run(
            store.find_similar("null pointer exception price column", k=3)
        )
        assert isinstance(results, list)

    def test_find_similar_returns_at_most_k(self, store):
        for i in range(3):
            inc = _incident(f"job_{i}")
            inc.incident_id = f"INC-{i}"
            rca = _rca()
            rca.incident_id = f"INC-{i}"
            heal = _heal()
            heal.incident_id = f"INC-{i}"
            asyncio.run(store.store(inc, rca, heal))

        results = asyncio.run(
            store.find_similar("null pointer", k=2)
        )
        assert len(results) <= 2

    def test_empty_store_returns_empty_list(self, store):
        results = asyncio.run(
            store.find_similar("anything", k=5)
        )
        assert isinstance(results, list)
        assert len(results) == 0


class TestInMemoryFallback:
    def test_store_with_bad_path_still_works(self, tmp_path):
        """ChromaDB should fall back to in-memory if path is invalid."""
        config = {
            "persist_dir": "/nonexistent/path/that/cannot/be/created/xyz",
            "collection_name": "fallback_test",
        }
        store = IncidentKnowledgeStore(config)
        asyncio.run(
            store.store(_incident(), _rca(), _heal())
        )
        results = asyncio.run(
            store.find_similar("null", k=3)
        )
        assert isinstance(results, list)
