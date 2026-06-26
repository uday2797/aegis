"""
AEGIS Context Assembler
Gathers all relevant signals before feeding them to the LLM RCA Agent.
Combines logs, metrics, lineage, upstream status, and similar past incidents.
"""
import os
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import List, Optional

from src.models import DetectedIncident


@dataclass
class IncidentContext:
    incident_id: str
    job_name: str
    error_summary: str
    error_logs: str
    failure_type: str
    upstream_jobs: List[str]
    affected_tables: List[str]
    metrics: dict
    similar_incidents: List[str] = field(default_factory=list)
    recent_schema_changes: str = ""
    timestamp: Optional[datetime] = None


class ContextAssembler:
    """
    Pulls together all signals needed for effective RCA:
    - Raw error logs and summary
    - Upstream job statuses
    - Data lineage (which tables feed this job)
    - Recent job run history from Databricks (real data)
    - Similar historical incidents from knowledge store
    """

    def __init__(
        self,
        knowledge_store=None,
        workspace_host: str = "",
        workspace_token: str = "",
    ):
        self.knowledge_store = knowledge_store
        self.workspace_host = workspace_host or os.environ.get("DATABRICKS_HOST", "")
        self.workspace_token = workspace_token or os.environ.get("DATABRICKS_TOKEN", "")

    async def assemble(self, incident: DetectedIncident) -> IncidentContext:
        similar = []
        if self.knowledge_store:
            similar = await self.knowledge_store.find_similar(incident.error_summary, k=3)

        schema_changes = await self._get_recent_pipeline_activity(incident)

        return IncidentContext(
            incident_id=incident.incident_id,
            job_name=incident.job_name,
            error_summary=incident.error_summary,
            error_logs=incident.error_logs,
            failure_type=incident.failure_type.value,
            upstream_jobs=incident.upstream_jobs,
            affected_tables=incident.affected_tables,
            metrics=incident.metrics,
            similar_incidents=similar,
            recent_schema_changes=schema_changes,
            timestamp=incident.timestamp,
        )

    async def _get_recent_pipeline_activity(self, incident: DetectedIncident) -> str:
        """
        Query Databricks for recent job run history to provide real context to the RCA LLM.
        Shows what ran recently, what succeeded/failed, and any state messages — no fake data.
        """
        if not self.workspace_host or not self.workspace_token:
            return "Recent pipeline activity: not available (Databricks credentials not configured)"

        try:
            from databricks.sdk import WorkspaceClient
            client = WorkspaceClient(host=self.workspace_host, token=self.workspace_token)

            lines = [f"Recent Databricks pipeline activity (last 24h):"]
            cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=24)
            run_count = 0

            # List recent runs across all jobs (last 20 runs)
            for run in client.jobs.list_runs(limit=20):
                run_count += 1
                start_ts = run.start_time  # milliseconds epoch
                if start_ts:
                    run_dt = datetime.fromtimestamp(start_ts / 1000, tz=timezone.utc)
                    if run_dt < cutoff:
                        continue
                    age_minutes = int((datetime.now(tz=timezone.utc) - run_dt).total_seconds() / 60)
                    age_str = f"{age_minutes}m ago" if age_minutes < 60 else f"{age_minutes // 60}h ago"
                else:
                    age_str = "unknown time"

                state = run.state
                if not state:
                    continue

                life = state.life_cycle_state.value if (state.life_cycle_state and hasattr(state.life_cycle_state, "value")) else "UNKNOWN"
                result = state.result_state.value if (state.result_state and hasattr(state.result_state, "value")) else None
                status_icon = "✅" if result == "SUCCESS" else ("❌" if result in ("FAILED", "INTERNAL_ERROR") else "⏳")
                state_msg = (state.state_message or "")[:120]

                run_name = getattr(run, "run_name", None) or f"run_{run.run_id}"
                lines.append(
                    f"  [{age_str}] {status_icon} {run_name} | {life}/{result or life}"
                    + (f" — {state_msg}" if state_msg else "")
                )

            if len(lines) == 1:
                return "Recent pipeline activity: no runs found in the last 24 hours"

            return "\n".join(lines)

        except Exception as exc:
            return f"Recent pipeline activity: query failed — {exc}"
