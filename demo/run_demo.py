"""
AEGIS Live Demo Script
Run this for the hackathon demonstration.
Injects 3 realistic failure scenarios and shows AEGIS healing each one autonomously.
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

import yaml
from dotenv import load_dotenv
from src.main import AEGISOrchestrator

load_dotenv()
console = Console()


DEMO_SCENARIOS = [
    {
        "title": "Scenario 1: Schema Drift (MEDIUM risk — auto-healed with patch)",
        "description": "Upstream payments API v2.2 renamed 'txn_amount' → 'transaction_amount'.\nPipeline breaks silently. AEGIS detects, patches, and creates a hotfix PR.",
        "failure": {
            "type": "schema_drift",
        },
        "color": "yellow",
    },
    {
        "title": "Scenario 2: Data Corruption (LOW risk — auto-healed with rollback)",
        "description": "Upstream microservice returned partial data — 34% null spike in user_id.\nAEGIS detects anomaly, rolls back Delta table, retriggers pipeline.",
        "failure": {
            "type": "data_corruption",
            "null_pct": 34.2,
            "row_count_drop_pct": 34.2,
        },
        "color": "red",
    },
    {
        "title": "Scenario 3: Transient Failure (LOW risk — auto-retried)",
        "description": "S3 network timeout caused job failure. No data issue.\nAEGIS identifies as transient, retries with backoff — job recovers.",
        "failure": {
            "type": "transient_failure",
        },
        "color": "blue",
    },
    {
        "title": "Scenario 4: Model Drift (MEDIUM risk — rollback + retraining triggered)",
        "description": "Fraud detection model PSI=0.31 exceeds threshold. Predictions degraded.\nAEGIS rolls back to stable v2, triggers retraining on last 30 days of data.",
        "failure": {
            "type": "model_drift",
            "psi_score": 0.31,
        },
        "color": "magenta",
    },
    {
        "title": "Scenario 5: Upstream Delay / SLA Breach (LOW risk — retriggered)",
        "description": "Upstream raw_ingest_job delayed 3x P95. Downstream dashboards stale.\nAEGIS monitors completion, retriggers dependent pipeline automatically.",
        "failure": {
            "type": "upstream_delay",
        },
        "color": "cyan",
    },
]


async def run_demo():
    console.print(Panel(
        "[bold cyan]🛡️  AEGIS LIVE DEMO[/bold cyan]\n"
        "[bold]AI-Engine for Guardian Intelligence & Self-healing[/bold]\n\n"
        "Watch AEGIS detect, diagnose, and autonomously heal production incidents\n"
        "across Data DevOps and MLOps systems in real-time.\n\n"
        "[dim]Mode: SIMULATION (no real Databricks connection needed)[/dim]",
        border_style="cyan",
        padding=(1, 4),
    ))

    config = yaml.safe_load(open("config/config.yaml"))
    orchestrator = AEGISOrchestrator(config)
    results = []

    for i, scenario in enumerate(DEMO_SCENARIOS, 1):
        console.print()
        console.print(Rule(f"[bold {scenario['color']}]{scenario['title']}[/bold {scenario['color']}]"))
        console.print(f"[dim]{scenario['description']}[/dim]\n")
        input(f"  Press ENTER to inject failure #{i} and start AEGIS recovery...\n")

        orchestrator.inject_failure(scenario["failure"])
        report = await orchestrator.run_once()

        if report:
            results.append(report)
            mttr = f"{report.mttr_seconds:.0f}s"
            status = "✅ AUTO-HEALED" if report.auto_healed else "⚠️  ESCALATED"
            console.print(f"\n  [{scenario['color']}]{status}[/{scenario['color']}] | MTTR: {mttr} | Confidence: {report.confidence:.0f}%")

        await asyncio.sleep(0.5)

    # Summary
    console.print()
    console.print(Rule("[bold green]DEMO COMPLETE — AEGIS SUMMARY[/bold green]"))
    total_mttr = sum(r.mttr_seconds for r in results)
    auto_healed = sum(1 for r in results if r.auto_healed)
    console.print(f"\n  Incidents Handled  : {len(results)}")
    console.print(f"  Auto-Healed        : {auto_healed}/{len(results)} ({auto_healed/len(results)*100:.0f}%)")
    console.print(f"  Total MTTR         : {total_mttr:.0f}s (avg {total_mttr/len(results):.0f}s per incident)")
    manual_minutes = len(results) * 45
    manual_seconds = manual_minutes * 60
    reduction_pct = int((manual_seconds - total_mttr) / manual_seconds * 100)
    console.print(f"  Manual MTTR Equiv. : ~{manual_minutes} minutes ({len(results)} × 45 min avg per engineer)\n")
    console.print(Panel(
        f"[bold green]AEGIS reduced MTTR by ~{reduction_pct}%[/bold green]\n"
        f"[dim]{total_mttr:.0f}s autonomous resolution vs ~{manual_minutes} minutes manual firefighting.[/dim]\n"
        "From reactive firefighting to governed autonomy.",
        border_style="green"
    ))


if __name__ == "__main__":
    asyncio.run(run_demo())
