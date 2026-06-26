"""
AEGIS Audit Log — Guardrail #6
Immutable, append-only record of every autonomous action taken.
Written to both a JSONL file and printed to the logger.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from loguru import logger


AUDIT_LOG_PATH = Path(os.environ.get("AEGIS_AUDIT_LOG", "data/audit_log.jsonl"))


class AuditLog:
    """
    Append-only audit log.  Each entry is one JSON line so the file can be
    streamed, grepped, or ingested into any log aggregator.

    Usage:
        AuditLog.record("NOTEBOOK_ROLLBACK", incident_id="INC-ABC", job_id=123, reason="post-fix run failed")
        AuditLog.record("FIX_UPLOADED",      incident_id="INC-ABC", job_id=123, notebook_path="/Workspace/...")
    """

    @staticmethod
    def record(action: str, **kwargs) -> None:
        """
        Append one audit entry.

        Args:
            action:  Short uppercase label, e.g. "FIX_UPLOADED", "ROLLBACK", "ESCALATED"
            **kwargs: Any additional key-value pairs to include.
        """
        entry = {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "action": action,
            **kwargs,
        }

        # Ensure directory exists
        AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

        # Append to JSONL (one JSON object per line — never overwrites)
        with AUDIT_LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")

        logger.info(f"[AuditLog] {action} | {' | '.join(f'{k}={v}' for k, v in kwargs.items())}")

    @staticmethod
    def read_recent(n: int = 20) -> list[dict]:
        """Return the last *n* audit entries."""
        if not AUDIT_LOG_PATH.exists():
            return []
        lines = AUDIT_LOG_PATH.read_text(encoding="utf-8").strip().splitlines()
        return [json.loads(l) for l in lines[-n:]]
