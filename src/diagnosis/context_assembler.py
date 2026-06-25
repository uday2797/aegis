"""
AEGIS Context Assembler
Gathers all relevant signals before feeding them to the LLM RCA Agent.
Combines logs, metrics, lineage, upstream status, and similar past incidents.
"""
from datetime import datetime
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
    - Recent schema/config changes
    - Similar historical incidents from knowledge store
    """

    def __init__(self, knowledge_store=None):
        self.knowledge_store = knowledge_store

    async def assemble(self, incident: DetectedIncident) -> IncidentContext:
        similar = []
        if self.knowledge_store:
            similar = await self.knowledge_store.find_similar(incident.error_summary, k=3)

        schema_changes = self._get_recent_schema_changes(incident)

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

    def _get_recent_schema_changes(self, incident: DetectedIncident) -> str:
        """
        In production: query Delta table history / data catalog change log.
        In demo: returns realistic simulated change history.
        """
        return (
            f"Recent changes for {incident.job_name}:\n"
            f"  - [2h ago] Upstream API v2.1 -> v2.2 deployed (schema change)\n"
            f"  - [1d ago] Partition strategy updated on {', '.join(incident.affected_tables[:1])}\n"
            f"  - [3d ago] Feature pipeline config updated (batch size: 5000 -> 10000)"
        )
