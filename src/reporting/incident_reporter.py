"""
AEGIS Incident Reporter
Orchestrates Teams notification + PR creation + knowledge store update.
Generates the final structured incident report.
"""
from datetime import datetime
from loguru import logger

from src.models import DetectedIncident, RCAResult, HealResult, IncidentReport
from src.reporting.teams_notifier import TeamsNotifier
from src.reporting.gmail_notifier import GmailNotifier
from src.reporting.pr_creator import PRCreator


class IncidentReporter:

    def __init__(self, knowledge_store=None):
        self.teams = TeamsNotifier()
        self.gmail = GmailNotifier()
        self.pr_creator = PRCreator()
        self.knowledge_store = knowledge_store

    async def report(
        self,
        incident: DetectedIncident,
        rca: RCAResult,
        heal: HealResult,
        resolution_time: datetime,
    ) -> IncidentReport:

        mttr = (resolution_time - incident.timestamp).total_seconds()
        pr_url = ""
        if heal.has_code_fix:
            pr_url = await self.pr_creator.create(rca, heal)

        report = IncidentReport(
            incident_id=incident.incident_id,
            job_name=incident.job_name,
            timestamp=incident.timestamp,
            resolution_time=resolution_time,
            mttr_seconds=mttr,
            root_cause=rca.root_cause,
            confidence=rca.confidence,
            risk_level=rca.risk_level.value,
            action_taken=heal.action_taken,
            outcome=heal.outcome,
            prevention_recommendation=rca.prevention or rca.explanation,
            auto_healed=heal.status.value == "auto_healed",
            pr_url=pr_url,
        )

        await self.teams.send(report)
        await self.gmail.send(report)

        if self.knowledge_store:
            await self.knowledge_store.store(incident, rca, heal)

        logger.success(
            f"[REPORT] Incident {incident.incident_id} closed | MTTR={mttr:.0f}s | "
            f"auto_healed={report.auto_healed} | pr={pr_url or 'none'}"
        )
        return report
