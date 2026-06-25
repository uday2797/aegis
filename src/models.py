"""
AEGIS Core Data Models
Defines all shared data structures used across the system.
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any


class FailureType(str, Enum):
    TRANSIENT_FAILURE = "transient_failure"
    UPSTREAM_DELAY = "upstream_delay"
    DATA_CORRUPTION = "data_corruption"
    SCHEMA_DRIFT = "schema_drift"
    MODEL_DRIFT = "model_drift"
    INFRA_FAILURE = "infra_failure"
    DATA_QUALITY = "data_quality"
    CONFIG_MISMATCH = "config_mismatch"
    UNKNOWN = "unknown"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class HealStatus(str, Enum):
    AUTO_HEALED = "auto_healed"
    ESCALATED = "escalated"
    PENDING_APPROVAL = "pending_approval"
    FAILED = "failed"


class IncidentStatus(str, Enum):
    DETECTED = "detected"
    DIAGNOSING = "diagnosing"
    HEALING = "healing"
    RESOLVED = "resolved"
    ESCALATED = "escalated"


@dataclass
class DetectedIncident:
    incident_id: str
    job_name: str
    failure_type: FailureType
    error_summary: str
    error_logs: str
    timestamp: datetime
    upstream_jobs: List[str] = field(default_factory=list)
    affected_tables: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    status: IncidentStatus = IncidentStatus.DETECTED


@dataclass
class RCAResult:
    incident_id: str
    root_cause: str
    confidence: float                # 0-100
    failure_type: FailureType
    risk_level: RiskLevel
    recommended_action: str
    explanation: str
    prevention: str = ""             # preventive action to avoid recurrence
    similar_incidents: List[str] = field(default_factory=list)


@dataclass
class HealResult:
    incident_id: str
    status: HealStatus
    action_taken: str
    outcome: str
    has_code_fix: bool = False
    fix_files: List[Dict[str, str]] = field(default_factory=list)
    pr_url: Optional[str] = None
    approval_required: bool = False


@dataclass
class IncidentReport:
    incident_id: str
    job_name: str
    timestamp: datetime
    resolution_time: datetime
    mttr_seconds: float
    root_cause: str
    confidence: float
    risk_level: str
    action_taken: str
    outcome: str
    prevention_recommendation: str
    auto_healed: bool
    pr_url: Optional[str] = None
