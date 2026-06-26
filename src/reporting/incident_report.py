"""
AEGIS Incident Report Generator
Produces a structured JSON + rich terminal report at the end of every cycle.

Saved to: data/reports/INC-<id>_<timestamp>.json
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

REPORTS_DIR = Path("data/reports")
console = Console()


def generate_incident_report(state: dict) -> dict:
    """
    Build a structured incident report from the final workflow state.

    Returns the report dict (also saved to disk).
    """
    now = datetime.now(tz=timezone.utc)
    incident_id = state.get("current_incident_id") or "NO-INCIDENT"
    timestamp_str = now.strftime("%Y%m%dT%H%M%S")

    # ── Build timeline from emails_sent + key stages ────────────────────
    stage_labels = {
        "initial_health_check": "Initial health check email sent",
        "failure_alert":        "Failure detected — RCA complete",
        "fix_in_progress":      "Autonomous fix started",
        "fix_complete":         "Fix verified — job running successfully",
        "pr_raised":            "GitHub PR created",
        "final_confirmation":   "Full cycle complete — job healthy in production",
        "deployment_failed":    "Post-deployment check failed — escalated to human",
    }
    timeline = [
        {"step": i + 1, "event": stage_labels.get(stage, stage)}
        for i, stage in enumerate(state.get("emails_sent", []))
    ]

    # ── Prevention recommendation (derived from root cause) ─────────────
    root_cause = state.get("root_cause") or "Unknown"
    prevention = _derive_prevention(root_cause)

    # ── Guardrails triggered (from audit log if available) ───────────────
    guardrails_triggered = _read_relevant_audit_entries(incident_id)

    report = {
        "report_id": f"RPT-{incident_id}-{timestamp_str}",
        "generated_at": now.isoformat(),
        "aegis_version": "2.0.0",
        "incident": {
            "id": incident_id,
            "job_id": state.get("current_job_id"),
            "job_name": state.get("current_job_name"),
        },
        "timeline": timeline,
        "diagnosis": {
            "root_cause": root_cause,
            "confidence_percent": state.get("confidence", 0),
            "risk_level": state.get("risk_level", "unknown"),
        },
        "resolution": {
            "action_taken": "GPT-5.5 autonomous notebook repair"
            if state.get("fix_status") == "success"
            else state.get("fix_status") or "none",
            "result": state.get("fix_status") or "not_attempted",
            "mttr_seconds": round(state.get("mttr_seconds", 0), 1),
            "mttr_human": _format_duration(state.get("mttr_seconds", 0)),
            "post_fix_run_id": state.get("post_fix_run_id"),
            "notebooks_fixed": [
                nb.get("path") for nb in (state.get("fixed_notebooks") or [])
            ],
        },
        "gitops": {
            "pr_url": state.get("pr_url"),
            "pr_number": state.get("pr_number"),
            "pr_merged": state.get("pr_merged", False),
            "deployment_status": state.get("deployment_status"),
            "workflow_run_url": state.get("workflow_run_url"),
        },
        "model_health": {
            "reports": state.get("model_health_reports", []),
            "drift_detected": any(
                r.get("status") == "degraded"
                for r in (state.get("model_health_reports") or [])
            ),
        },
        "notifications": {
            "emails_sent": state.get("emails_sent", []),
            "total_emails": len(state.get("emails_sent", [])),
        },
        "guardrails_triggered": guardrails_triggered,
        "prevention_recommendation": prevention,
    }

    # ── Save to disk ─────────────────────────────────────────────────────
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"{report['report_id']}.json"
    report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    logger.success(f"[Report] 📋 Incident report saved → {report_path}")

    # ── Print rich terminal summary ──────────────────────────────────────
    _print_report(report)

    return report


def _print_report(report: dict) -> None:
    """Print a beautiful terminal summary of the incident report."""
    inc = report["incident"]
    diag = report["diagnosis"]
    res = report["resolution"]
    git = report["gitops"]
    model = report["model_health"]

    status_icon = "✅" if res["result"] == "success" else "❌"
    title = f"{status_icon}  AEGIS INCIDENT REPORT  —  {inc['id']}"

    console.print("\n")
    console.print(Panel(f"[bold cyan]{title}[/bold cyan]", border_style="cyan"))

    # Diagnosis table
    diag_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    diag_table.add_column("Field", style="bold yellow")
    diag_table.add_column("Value")
    diag_table.add_row("Incident ID", inc["id"])
    diag_table.add_row("Job", f"{inc['job_name']} (ID: {inc['job_id']})")
    diag_table.add_row("Root Cause", diag["root_cause"])
    diag_table.add_row("RCA Confidence", f"{diag['confidence_percent']:.0f}%")
    diag_table.add_row("Risk Level", diag["risk_level"].upper())
    diag_table.add_row("Action Taken", res["action_taken"])
    diag_table.add_row("Fix Result", res["result"].upper())
    diag_table.add_row("MTTR", res["mttr_human"])
    if res.get("post_fix_run_id"):
        diag_table.add_row("Verified Run", str(res["post_fix_run_id"]))
    if git.get("pr_url"):
        diag_table.add_row("PR", git["pr_url"])
    console.print(diag_table)

    # Timeline
    if report["timeline"]:
        console.print("[bold]📅 Timeline:[/bold]")
        for entry in report["timeline"]:
            console.print(f"  [{entry['step']}] {entry['event']}")

    # Model health
    if model["reports"]:
        drift_icon = "⚠️ " if model["drift_detected"] else "✅"
        console.print(f"\n[bold]🤖 Model Health:[/bold] {drift_icon}")
        for m in model["reports"]:
            console.print(
                f"  • {m.get('model_name', 'model')}  "
                f"accuracy={m.get('current_accuracy', 'N/A')}  "
                f"status={m.get('status', 'unknown').upper()}"
            )

    # Prevention
    console.print(f"\n[bold]🛡️  Prevention Recommendation:[/bold]")
    console.print(f"  {report['prevention_recommendation']}")

    # Guardrails
    if report["guardrails_triggered"]:
        console.print(f"\n[bold]🔒 Guardrails Triggered:[/bold] {len(report['guardrails_triggered'])}")
        for g in report["guardrails_triggered"][:5]:
            console.print(f"  • {g.get('action', '?')} at {g.get('timestamp', '?')[:19]}")

    console.print(f"\n[dim]Report saved → data/reports/{report['report_id']}.json[/dim]\n")


def _derive_prevention(root_cause: str) -> str:
    """Derive a prevention recommendation from the root cause text."""
    rc_lower = root_cause.lower()
    if "cache" in rc_lower or "persist" in rc_lower:
        return (
            "Remove df.cache() / df.persist() calls from notebooks running on "
            "Databricks Serverless compute. Use checkpointing or Delta table writes instead."
        )
    if "import" in rc_lower or "module" in rc_lower:
        return (
            "Add a requirements check at notebook start. Use try/import blocks "
            "and pin package versions in cluster libraries."
        )
    if "schema" in rc_lower or "column" in rc_lower:
        return (
            "Add schema validation (Great Expectations or Delta constraints) before "
            "transformations. Alert on upstream schema changes via Delta CDF."
        )
    if "division" in rc_lower or "zero" in rc_lower:
        return (
            "Add nullIf / CASE WHEN guards around all division operations. "
            "Use F.when(F.col('denominator') != 0, ...).otherwise(F.lit(None))."
        )
    if "timeout" in rc_lower or "connection" in rc_lower:
        return (
            "Implement exponential backoff retries for external connections. "
            "Add circuit breaker pattern for dependent services."
        )
    return (
        "Review the root cause and add a targeted unit test covering this scenario. "
        "Consider adding a pre-run validation step to catch this class of error early."
    )


def _format_duration(seconds: float) -> str:
    """Convert seconds to a human-readable duration string."""
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m {s % 60}s"
    return f"{s // 3600}h {(s % 3600) // 60}m"


def _read_relevant_audit_entries(incident_id: str) -> list[dict]:
    """Read audit log entries relevant to this incident."""
    try:
        from src.guardrails.audit_log import AUDIT_LOG_PATH
        if not AUDIT_LOG_PATH.exists():
            return []
        lines = AUDIT_LOG_PATH.read_text(encoding="utf-8").strip().splitlines()
        entries = []
        for line in lines:
            try:
                entry = json.loads(line)
                if entry.get("incident_id") == incident_id:
                    entries.append(entry)
            except json.JSONDecodeError:
                pass
        return entries
    except Exception:
        return []
