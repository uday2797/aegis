"""
Tests for guardrails/audit_log.py — append-only JSONL, read_recent.
Uses a temp file via tmp_path fixture so production data is never touched.
"""
import json
import os
import pytest
from pathlib import Path


@pytest.fixture(autouse=True)
def isolated_audit_log(tmp_path, monkeypatch):
    """Redirect audit log to a temp file for every test."""
    log_path = tmp_path / "audit_test.jsonl"
    monkeypatch.setenv("AEGIS_AUDIT_LOG", str(log_path))
    # Reload the module so the path constant is re-evaluated
    import importlib
    import src.guardrails.audit_log as audit_module
    importlib.reload(audit_module)
    yield log_path
    # Cleanup handled by tmp_path


def _get_audit_log():
    import src.guardrails.audit_log as m
    return m.AuditLog, m.AUDIT_LOG_PATH


class TestAuditLogRecord:
    def test_creates_file_on_first_write(self, isolated_audit_log):
        AuditLog, _ = _get_audit_log()
        AuditLog.record("TEST_ACTION", incident_id="INC-1")
        assert isolated_audit_log.exists()

    def test_entry_is_valid_json(self, isolated_audit_log):
        AuditLog, _ = _get_audit_log()
        AuditLog.record("MY_ACTION", job_id=42, extra="value")
        line = isolated_audit_log.read_text().strip()
        data = json.loads(line)
        assert data["action"] == "MY_ACTION"
        assert data["job_id"] == 42

    def test_entry_has_utc_timestamp(self, isolated_audit_log):
        AuditLog, _ = _get_audit_log()
        AuditLog.record("TS_CHECK")
        data = json.loads(isolated_audit_log.read_text().strip())
        assert "timestamp" in data
        assert data["timestamp"].endswith("+00:00") or data["timestamp"].endswith("Z")

    def test_multiple_writes_append(self, isolated_audit_log):
        AuditLog, _ = _get_audit_log()
        AuditLog.record("A1")
        AuditLog.record("A2")
        AuditLog.record("A3")
        lines = isolated_audit_log.read_text().strip().splitlines()
        assert len(lines) == 3

    def test_kwargs_appear_in_entry(self, isolated_audit_log):
        AuditLog, _ = _get_audit_log()
        AuditLog.record("KWARGS_TEST", foo="bar", baz=99)
        data = json.loads(isolated_audit_log.read_text().strip())
        assert data["foo"] == "bar"
        assert data["baz"] == 99

    def test_no_overwrite_on_second_call(self, isolated_audit_log):
        AuditLog, _ = _get_audit_log()
        AuditLog.record("FIRST")
        AuditLog.record("SECOND")
        lines = isolated_audit_log.read_text().strip().splitlines()
        assert json.loads(lines[0])["action"] == "FIRST"
        assert json.loads(lines[1])["action"] == "SECOND"


class TestAuditLogReadRecent:
    def test_returns_empty_when_no_log(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AEGIS_AUDIT_LOG", str(tmp_path / "nonexistent.jsonl"))
        import importlib
        import src.guardrails.audit_log as m
        importlib.reload(m)
        entries = m.AuditLog.read_recent(10)
        assert entries == []

    def test_returns_last_n_entries(self, isolated_audit_log):
        AuditLog, _ = _get_audit_log()
        for i in range(10):
            AuditLog.record(f"ACTION_{i}")
        recent = AuditLog.read_recent(3)
        assert len(recent) == 3
        assert recent[-1]["action"] == "ACTION_9"

    def test_read_recent_default_limit(self, isolated_audit_log):
        AuditLog, _ = _get_audit_log()
        for i in range(25):
            AuditLog.record(f"LOG_{i}")
        recent = AuditLog.read_recent()  # default n=20
        assert len(recent) == 20
