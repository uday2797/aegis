"""
AEGIS Main Orchestrator
The central event loop that ties all components together.
Runs the full DETECT → DIAGNOSE → DECIDE → HEAL → REPORT loop continuously.
"""
import asyncio
import os
import sys
from datetime import datetime

import yaml
from dotenv import load_dotenv
from loguru import logger
from rich.console import Console
from rich.panel import Panel

from src.detection.failure_detector import FailureDetector
from src.diagnosis.rca_agent import RCAAgent
from src.diagnosis.context_assembler import ContextAssembler
from src.healing.policy_engine import PolicyEngine
from src.healing.heal_orchestrator import HealOrchestrator
from src.reporting.incident_reporter import IncidentReporter
from src.knowledge.incident_store import IncidentKnowledgeStore
from src.models import HealResult, HealStatus

load_dotenv()
console = Console()


def load_config(path: str = "config/config.yaml") -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


class AEGISOrchestrator:
    """
    Main AEGIS event loop.
    Polls for incidents, runs the full autonomous reliability loop,
    and reports results with full audit trail.
    """

    def __init__(self, config: dict):
        self.config = config
        self.simulation_mode = os.environ.get("SIMULATION_MODE", "true").lower() == "true"
        self.poll_interval = config["aegis"]["poll_interval_seconds"]

        # Wire up all components
        self.knowledge_store = IncidentKnowledgeStore(config["knowledge_store"])
        self.detector = FailureDetector(config["detection"], simulation_mode=self.simulation_mode)
        self.assembler = ContextAssembler(knowledge_store=self.knowledge_store)
        self.rca_agent = RCAAgent(config["rca"])
        self.policy = PolicyEngine(config["policy"])
        self.healer = HealOrchestrator(config["healing"], simulation_mode=self.simulation_mode)
        self.reporter = IncidentReporter(knowledge_store=self.knowledge_store)

        logger.info("AEGIS Orchestrator initialized — all components ready")

    def inject_failure(self, failure_spec: dict):
        """Used by demo scripts to trigger a specific failure."""
        self.detector.inject_failure(failure_spec)

    async def run_once(self):
        """Execute one full monitoring tick — useful for testing and demo."""
        incident = await self.detector.monitor()
        if not incident:
            logger.debug("No incidents detected — system healthy")
            return None

        console.print(Panel(
            f"[bold red]🚨 INCIDENT DETECTED[/bold red]\n"
            f"ID: {incident.incident_id}\n"
            f"Job: {incident.job_name}\n"
            f"Type: {incident.failure_type.value}\n"
            f"Summary: {incident.error_summary}",
            border_style="red"
        ))

        # DIAGNOSE
        context = await self.assembler.assemble(incident)
        rca = await self.rca_agent.diagnose(context)
        console.print(Panel(
            f"[bold yellow]🔍 ROOT CAUSE ANALYSIS[/bold yellow]\n"
            f"Root Cause: {rca.root_cause}\n"
            f"Confidence: {rca.confidence:.0f}%\n"
            f"Risk Level: {rca.risk_level.value.upper()}\n"
            f"Recommended: {rca.recommended_action}",
            border_style="yellow"
        ))

        # DECIDE
        can_auto_heal, policy_reason = self.policy.should_auto_heal(rca)
        console.print(f"\n[bold]Policy Decision:[/bold] {policy_reason}\n")

        # HEAL
        if can_auto_heal:
            # ── Before-fix notification ──────────────────────────────────────
            before_subject = f"[AEGIS] 🔧 Fixing {incident.incident_id} | {incident.job_name}"
            before_body = (
                f"AEGIS is autonomously fixing a failure.\n\n"
                f"Incident  : {incident.incident_id}\n"
                f"Job       : {incident.job_name}\n"
                f"Error     : {incident.error_summary[:300]}\n\n"
                f"Root Cause: {rca.root_cause}\n"
                f"Confidence: {rca.confidence:.0f}%\n"
                f"Action    : GPT-5.5 notebook repair in progress...\n\n"
                f"You will receive another email when the fix is complete."
            )
            await self.reporter.gmail.send_alert(before_subject, before_body)
            # ────────────────────────────────────────────────────────────────
            heal = await self.healer.heal(rca, incident.incident_id)
        else:
            heal = HealResult(
                incident_id=incident.incident_id,
                status=HealStatus.ESCALATED,
                action_taken="Escalated to on-call engineer — risk too high for autonomous healing",
                outcome="Pending human review and approval",
                approval_required=True,
            )

        console.print(Panel(
            f"[bold green]⚡ HEALING ACTION[/bold green]\n"
            f"Status: {heal.status.value}\n"
            f"Action: {heal.action_taken}\n"
            f"Outcome: {heal.outcome}\n"
            f"Code Fix Generated: {heal.has_code_fix}",
            border_style="green"
        ))

        # REPORT
        resolution_time = datetime.utcnow()
        report = await self.reporter.report(incident, rca, heal, resolution_time)

        return report

    async def run_continuous(self):
        """Continuous monitoring loop — production mode."""
        console.print(Panel(
            "[bold cyan]🛡️  AEGIS — AI-Engine for Guardian Intelligence & Self-healing[/bold cyan]\n"
            f"Mode: {'SIMULATION' if self.simulation_mode else 'PRODUCTION'}\n"
            f"Poll Interval: {self.poll_interval}s",
            border_style="cyan"
        ))

        while True:
            try:
                await self.run_once()
            except KeyboardInterrupt:
                logger.info("AEGIS stopped by user")
                break
            except Exception as e:
                logger.error(f"Orchestrator error: {e}")
            await asyncio.sleep(self.poll_interval)


async def main():
    config = load_config()
    orchestrator = AEGISOrchestrator(config)
    await orchestrator.run_continuous()


if __name__ == "__main__":
    asyncio.run(main())
