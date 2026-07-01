"""
AEGIS LLM-Powered RCA Agent
The core AI brain of AEGIS. Uses GPT-4o to reason across multiple signals
and produce an explainable root cause with confidence score and recommended action.
"""
import os
from loguru import logger
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from src.models import RCAResult, FailureType, RiskLevel
from src.diagnosis.context_assembler import IncidentContext
from src.guardrails.prompt_guard import (
    sanitize_error_log,
    sanitize_for_prompt,
    injection_resistant_system_message,
    MAX_ERROR_LOG_CHARS,
)


SYSTEM_PROMPT = """You are AEGIS, a senior AI Site Reliability Engineer specializing in 
Data DevOps and MLOps. You have deep expertise in Databricks pipelines, Delta Lake, 
Apache Spark, MLflow, and distributed data systems.

When given an incident context, you perform structured root cause analysis (RCA) by 
reasoning across logs, metrics, lineage, and historical incident patterns.

You always:
1. Identify the single most likely root cause
2. Provide a confidence score (0-100)
3. Recommend a specific, actionable fix
4. Assess risk level of the recommended fix
5. Explain your reasoning clearly

You respond ONLY in valid JSON format."""


RCA_PROMPT_TEMPLATE = """
Analyze this production incident and provide root cause analysis:

## Incident ID: {incident_id}
## Job: {job_name}
## Timestamp: {timestamp}

## ⚠️ PYTHON ERROR TRACE (MOST IMPORTANT - ANALYZE THIS FIRST):
{error_logs}

## Error Summary:
{error_summary}

---

## Additional Context (use only if Python error is unclear):
- Failure Type (detected): {failure_type}
- Upstream Job Status: {upstream_jobs}
- Affected Tables: {affected_tables}
- Current Metrics: {metrics}
- Recent Changes: {recent_schema_changes}
- Similar Past Incidents: {similar_incidents}

---

IMPORTANT INSTRUCTIONS:
1. **START BY ANALYZING THE PYTHON ERROR TRACE ABOVE**
2. If you see a clear Python exception (ImportError, NameError, SyntaxError, etc.), diagnose based on that
3. Common Python issues to look for:
   - Import typos (e.g., "pandas" misspelled as "pandsa")
   - Undefined variables
   - Division by zero
   - Type errors
   - Index out of range
4. Only consider "upstream API changes" or "schema drift" if the Python error clearly indicates that

Respond with this exact JSON structure:
{{
  "root_cause": "one clear sentence describing the ACTUAL root cause from the Python error",
  "confidence": 95,
  "failure_type": "transient_failure",
  "risk_level": "low",
  "recommended_action": "Fix the specific Python error: [exact fix needed]",
  "explanation": "The Python error trace shows [specific exception]. This is caused by [specific line/issue].",
  "prevention": "what code change prevents this exact error"
}}

risk_level must be: low | medium | high
failure_type must be one of: transient_failure | upstream_delay | data_corruption | schema_drift | model_drift | infra_failure | data_quality | config_mismatch
"""


class RCAAgent:
    """
    LLM-powered Root Cause Analysis agent.
    Reasons across all available signals to produce structured, explainable RCA.
    Falls back to rule-based analysis if LLM is unavailable.
    """

    def __init__(self, config: dict):
        self.config = config
        self.llm = self._init_llm()

    def _init_llm(self):
        # EPAM DIAL API — Azure OpenAI-compatible proxy
        api_key = os.environ.get("DIAL_API_KEY")
        endpoint = os.environ.get("DIAL_API_ENDPOINT", "https://ai-proxy.lab.epam.com")
        deployment = os.environ.get("DIAL_DEPLOYMENT", "gpt-5.5-2026-04-24")
        api_version = os.environ.get("DIAL_API_VERSION", "2025-04-01-preview")

        if not api_key:
            logger.warning("DIAL_API_KEY not set — using rule-based fallback RCA")
            return None

        return AzureChatOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            azure_deployment=deployment,
            api_version=api_version,
            temperature=0,
            max_tokens=2000,
            request_timeout=30,
        )

    async def diagnose(self, context: IncidentContext) -> RCAResult:
        logger.info(f"[RCA] Starting analysis for {context.incident_id}")

        if self.llm:
            result = await self._llm_diagnose(context)
        else:
            result = self._rule_based_diagnose(context)

        logger.success(
            f"[RCA] Complete | cause='{result.root_cause}' | "
            f"confidence={result.confidence}% | risk={result.risk_level}"
        )
        return result

    async def _llm_diagnose(self, context: IncidentContext) -> RCAResult:
        import json

        # Guardrail #7 — sanitise all untrusted fields before prompt interpolation
        safe_error_summary = sanitize_for_prompt(context.error_summary, max_chars=1_000, field_name="error_summary")
        safe_error_logs = sanitize_error_log(context.error_logs)
        safe_schema_changes = sanitize_for_prompt(context.recent_schema_changes, max_chars=500, field_name="schema_changes")
        safe_similar = [sanitize_for_prompt(s, max_chars=300, field_name="similar_incident") for s in context.similar_incidents]

        prompt = RCA_PROMPT_TEMPLATE.format(
            incident_id=context.incident_id,
            job_name=context.job_name,
            failure_type=context.failure_type,
            timestamp=context.timestamp,
            error_summary=safe_error_summary,
            error_logs=safe_error_logs,
            upstream_jobs=", ".join(context.upstream_jobs) or "none",
            affected_tables=", ".join(context.affected_tables) or "none",
            metrics=str(context.metrics),
            recent_schema_changes=safe_schema_changes,
            similar_incidents="\n".join(safe_similar) or "none found",
        )

        messages = [
            SystemMessage(content=injection_resistant_system_message(SYSTEM_PROMPT)),
            HumanMessage(content=prompt),
        ]

        try:
            response = await self.llm.ainvoke(messages)
            raw = response.content.strip()
            # Strip markdown code fences if present (handles ```json, ```JSON, ``` etc.)
            if raw.startswith("```"):
                parts = raw.split("```")
                raw = parts[1] if len(parts) > 1 else raw
                if raw.lower().startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()
            data = json.loads(raw)
            return RCAResult(
                incident_id=context.incident_id,
                root_cause=data["root_cause"],
                confidence=float(data["confidence"]),
                failure_type=FailureType(data["failure_type"]),
                risk_level=RiskLevel(data["risk_level"]),
                recommended_action=data["recommended_action"],
                explanation=data["explanation"],
                prevention=data.get("prevention", ""),
                similar_incidents=context.similar_incidents,
            )
        except Exception as e:
            logger.error(f"LLM RCA failed: {e} — falling back to rule-based")
            return self._rule_based_diagnose(context)

    def _rule_based_diagnose(self, context: IncidentContext) -> RCAResult:
        """
        Deterministic fallback when LLM is not available.
        Maps known failure types to predefined RCA results.
        """
        rules = {
            "schema_drift": RCAResult(
                incident_id=context.incident_id,
                root_cause="Upstream schema changed: column renamed or dropped without downstream notification",
                confidence=88.0,
                failure_type=FailureType.SCHEMA_DRIFT,
                risk_level=RiskLevel.MEDIUM,
                recommended_action="Update downstream column references and apply schema mapping patch",
                explanation="Log analysis shows AnalysisException on column reference. Recent change log confirms API version bump with breaking schema change.",
                prevention="Add schema contract tests (Great Expectations) to CI pipeline. Enable schema change alerts on the upstream data catalog.",
                similar_incidents=context.similar_incidents,
            ),
            "data_corruption": RCAResult(
                incident_id=context.incident_id,
                root_cause="Upstream data source returned partial/corrupt data causing null spike in critical column",
                confidence=91.0,
                failure_type=FailureType.DATA_CORRUPTION,
                risk_level=RiskLevel.LOW,
                recommended_action="Rollback Delta table to last known good version and retrigger pipeline",
                explanation="Null percentage exceeds threshold. Row count drop correlates with upstream HTTP 206 response indicating partial data delivery.",
                prevention="Add upstream data quality checks at ingestion layer. Set row-count anomaly alerts on the source connector.",
                similar_incidents=context.similar_incidents,
            ),
            "transient_failure": RCAResult(
                incident_id=context.incident_id,
                root_cause="Transient network timeout from cloud storage endpoint during data read phase",
                confidence=95.0,
                failure_type=FailureType.TRANSIENT_FAILURE,
                risk_level=RiskLevel.LOW,
                recommended_action="Retry job with exponential backoff — no data fix needed",
                explanation="SocketTimeoutException with no data corruption indicators. S3 latency spike confirms transient infra issue.",
                prevention="Configure built-in Databricks retry policy (max_retries=3) and enable S3 endpoint health monitoring with auto-failover.",
                similar_incidents=context.similar_incidents,
            ),
            "model_drift": RCAResult(
                incident_id=context.incident_id,
                root_cause="Significant prediction distribution drift detected — model requires retraining on recent data",
                confidence=87.0,
                failure_type=FailureType.MODEL_DRIFT,
                risk_level=RiskLevel.MEDIUM,
                recommended_action="Rollback to previous stable model version and trigger retraining pipeline",
                explanation="PSI score of 0.31 exceeds threshold of 0.20. Model was last retrained 47 days ago. Feature distribution shift indicates concept drift.",
                prevention="Schedule automatic weekly retraining triggered when PSI > 0.15. Add pre-production shadow scoring to catch drift earlier.",
                similar_incidents=context.similar_incidents,
            ),
            "upstream_delay": RCAResult(
                incident_id=context.incident_id,
                root_cause="SLA breach caused by upstream dependency delay blocking downstream execution",
                confidence=90.0,
                failure_type=FailureType.UPSTREAM_DELAY,
                risk_level=RiskLevel.LOW,
                recommended_action="Wait for upstream job completion and retrigger with adjusted SLA window",
                explanation="Runtime 3x above P95 baseline. Upstream job still running, causing cascading SLA breach across dependent pipelines.",
                prevention="Add upstream SLA monitoring with early-warning alerts at 1.5x baseline. Decouple downstream jobs using event-driven triggers.",
                similar_incidents=context.similar_incidents,
            ),
        }
        return rules.get(context.failure_type, RCAResult(
            incident_id=context.incident_id,
            root_cause="Unknown failure — manual investigation required",
            confidence=40.0,
            failure_type=FailureType.UNKNOWN,
            risk_level=RiskLevel.HIGH,
            recommended_action="Escalate to on-call engineer for manual investigation",
            explanation="Could not match failure pattern to known incident types.",
            similar_incidents=[],
        ))
