"""
AEGIS Teams Notifier
Sends rich adaptive card notifications to Microsoft Teams via webhook.
Includes full incident context, RCA, action taken, and PR link.
"""
import os
import httpx
from datetime import datetime
from loguru import logger

from src.models import IncidentReport


def _severity_color(risk_level: str) -> str:
    return {"low": "good", "medium": "warning", "high": "attention"}.get(risk_level.lower(), "default")


def _status_emoji(auto_healed: bool) -> str:
    return "✅ Auto-Healed" if auto_healed else "⚠️ Escalated — Human Review Required"


class TeamsNotifier:
    """
    Sends Microsoft Teams Adaptive Card with full incident details.
    Uses incoming webhook — no app registration required.
    """

    def __init__(self):
        self.webhook_url = os.environ.get("TEAMS_WEBHOOK_URL")

    async def send(self, report: IncidentReport):
        if not self.webhook_url:
            logger.warning("[TEAMS] Webhook URL not configured — printing to console")
            self._print_to_console(report)
            return

        card = self._build_adaptive_card(report)
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.webhook_url,
                    json=card,
                    headers={"Content-Type": "application/json"},
                    timeout=10,
                )
                if response.status_code == 200:
                    logger.success("[TEAMS] Notification sent successfully")
                else:
                    logger.error(f"[TEAMS] Failed: {response.status_code} {response.text}")
        except Exception as e:
            logger.error(f"[TEAMS] Error sending notification: {e}")
            self._print_to_console(report)

    def _build_adaptive_card(self, report: IncidentReport) -> dict:
        color = _severity_color(report.risk_level)
        status = _status_emoji(report.auto_healed)
        mttr_display = f"{report.mttr_seconds:.0f}s" if report.mttr_seconds < 120 else f"{report.mttr_seconds/60:.1f}min"
        pr_section = []
        if report.pr_url:
            pr_section = [{"type": "Action.OpenUrl", "title": "View Hotfix PR", "url": report.pr_url}]

        return {
            "type": "message",
            "attachments": [{
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": [
                        {
                            "type": "TextBlock",
                            "text": f"🛡️ AEGIS Incident Report — {report.incident_id}",
                            "weight": "Bolder",
                            "size": "Large",
                            "color": color,
                        },
                        {
                            "type": "FactSet",
                            "facts": [
                                {"title": "Status", "value": status},
                                {"title": "Job", "value": report.job_name},
                                {"title": "Detected At", "value": report.timestamp.strftime("%Y-%m-%d %H:%M UTC")},
                                {"title": "MTTR", "value": mttr_display},
                                {"title": "Risk Level", "value": report.risk_level.upper()},
                                {"title": "Confidence", "value": f"{report.confidence:.0f}%"},
                            ]
                        },
                        {"type": "TextBlock", "text": "Root Cause", "weight": "Bolder", "spacing": "Medium"},
                        {"type": "TextBlock", "text": report.root_cause, "wrap": True},
                        {"type": "TextBlock", "text": "Action Taken", "weight": "Bolder", "spacing": "Medium"},
                        {"type": "TextBlock", "text": report.action_taken, "wrap": True},
                        {"type": "TextBlock", "text": "Outcome", "weight": "Bolder", "spacing": "Medium"},
                        {"type": "TextBlock", "text": report.outcome, "wrap": True},
                        {"type": "TextBlock", "text": "Prevention Recommendation", "weight": "Bolder", "spacing": "Medium"},
                        {"type": "TextBlock", "text": report.prevention_recommendation, "wrap": True, "color": "good"},
                    ],
                    "actions": pr_section,
                }
            }]
        }

    def _print_to_console(self, report: IncidentReport):
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table

        console = Console()
        color = {"low": "green", "medium": "yellow", "high": "red"}.get(report.risk_level.lower(), "white")
        status = "✅ AUTO-HEALED" if report.auto_healed else "⚠️  ESCALATED"
        mttr = f"{report.mttr_seconds:.0f}s"

        table = Table(show_header=False, box=None)
        table.add_column("Field", style="bold")
        table.add_column("Value")
        table.add_row("Incident ID", report.incident_id)
        table.add_row("Job", report.job_name)
        table.add_row("Status", f"[{color}]{status}[/{color}]")
        table.add_row("MTTR", mttr)
        table.add_row("Risk", f"[{color}]{report.risk_level.upper()}[/{color}]")
        table.add_row("Confidence", f"{report.confidence:.0f}%")
        table.add_row("Root Cause", report.root_cause)
        table.add_row("Action Taken", report.action_taken)
        table.add_row("Outcome", report.outcome)
        table.add_row("Prevention", report.prevention_recommendation)
        if report.pr_url:
            table.add_row("PR URL", report.pr_url)

        console.print(Panel(table, title="🛡️  AEGIS INCIDENT REPORT", border_style=color))
