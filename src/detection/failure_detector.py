"""
AEGIS Failure Detection Engine
Monitors Databricks jobs, data quality, schema drift, and model drift in real-time.
Supports both simulation mode (for demo) and production mode (real Databricks).
"""
import asyncio
import json
import os
import random
import uuid
from datetime import datetime
from typing import Optional

from loguru import logger

from src.models import DetectedIncident, FailureType


# ─── Simulated job catalog for demo mode ────────────────────────────────────
DEMO_JOBS = [
    {
        "job_id": "job_001",
        "job_name": "nexus_exp_daily_pipeline",
        "table": "nexus_optimized",
        "p95_runtime_sec": 300,
    },
    {
        "job_id": "job_002",
        "job_name": "fraud_model_feature_pipeline",
        "table": "feature_store_fraud",
        "p95_runtime_sec": 180,
    },
    {
        "job_id": "job_003",
        "job_name": "customer_segmentation_training",
        "table": "model_training_data",
        "p95_runtime_sec": 600,
    },
]


class FailureDetector:
    """
    Continuously monitors data/ML pipeline health.
    In simulation mode, injects realistic failures for demo purposes.
    In production mode, polls the real Databricks Jobs API.
    """

    def __init__(self, config: dict, simulation_mode: bool = True):
        self.config = config
        self.simulation_mode = simulation_mode
        self._injected_failure: Optional[dict] = None
        logger.info(f"FailureDetector initialized | mode={'simulation' if simulation_mode else 'production'}")

    # ─── Public API ─────────────────────────────────────────────────────────

    def inject_failure(self, failure_spec: dict):
        """Used by demo scripts to inject a specific failure for live demo."""
        self._injected_failure = failure_spec
        logger.warning(f"[DEMO] Failure injected: {failure_spec['type']}")

    async def monitor(self) -> Optional[DetectedIncident]:
        """
        Single monitoring tick. Returns a DetectedIncident if a failure is found,
        else None. The main orchestrator calls this in a polling loop.
        Injected failures (demo/test) always take priority over real polling.
        """
        if self._injected_failure:
            return await self._monitor_simulated()
        if self.simulation_mode:
            return await self._monitor_simulated()
        return await self._monitor_databricks()

    # ─── Simulation Mode ────────────────────────────────────────────────────

    async def _monitor_simulated(self) -> Optional[DetectedIncident]:
        """Returns injected failure if one exists, else random healthy status."""
        if self._injected_failure:
            failure = self._injected_failure
            self._injected_failure = None  # consume it
            return self._build_incident(failure)
        return None  # healthy

    def _build_incident(self, failure_spec: dict) -> DetectedIncident:
        failure_type = FailureType(failure_spec["type"])
        job = random.choice(DEMO_JOBS)

        error_logs, error_summary = self._generate_realistic_logs(failure_type, job)

        return DetectedIncident(
            incident_id=f"INC-{uuid.uuid4().hex[:8].upper()}",
            job_name=job["job_name"],
            failure_type=failure_type,
            error_summary=error_summary,
            error_logs=error_logs,
            timestamp=datetime.utcnow(),
            upstream_jobs=["raw_ingest_job", "validation_job"],
            affected_tables=[job["table"], f"{job['table']}_downstream"],
            metrics={
                "null_pct": failure_spec.get("null_pct", 0),
                "row_count_drop_pct": failure_spec.get("row_count_drop_pct", 0),
                "psi_score": failure_spec.get("psi_score", 0),
                "runtime_sec": failure_spec.get("runtime_sec", job["p95_runtime_sec"]),
            },
        )

    def _generate_realistic_logs(self, failure_type: FailureType, job: dict) -> tuple[str, str]:
        logs_map = {
            FailureType.SCHEMA_DRIFT: (
                f"[ERROR] AnalysisException: cannot resolve 'txn_amount' given input columns: "
                f"[transaction_amount, user_id, ts]\n"
                f"  at org.apache.spark.sql.catalyst.analysis.Analyzer\n"
                f"  Table: {job['table']}\n"
                f"  Expected schema: {{txn_amount: double}}\n"
                f"  Actual schema:   {{transaction_amount: double}}\n"
                f"[INFO] Upstream API version changed from v2.1 to v2.2 at 14:28 UTC",
                "Schema column 'txn_amount' renamed to 'transaction_amount' in upstream source"
            ),
            FailureType.DATA_CORRUPTION: (
                f"[ERROR] Data quality check FAILED on table {job['table']}\n"
                f"  Check: null_count(user_id) <= 5%\n"
                f"  Actual: null_count = 34.2% (threshold: 5%)\n"
                f"  Affected rows: 342,000 / 1,000,000\n"
                f"[WARN] Upstream microservice returned HTTP 206 Partial Content at 09:14 UTC\n"
                f"[ERROR] Row count dropped from 1,000,000 to 658,000 (-34.2%)",
                "Critical null spike detected in user_id column (34.2% nulls, threshold 5%)"
            ),
            FailureType.TRANSIENT_FAILURE: (
                f"[ERROR] Job {job['job_name']} failed with exit code 1\n"
                f"  Caused by: java.net.SocketTimeoutException: Read timed out\n"
                f"  at sun.net.www.protocol.http.HttpURLConnection.getInputStream\n"
                f"  Retried 0/3 times\n"
                f"[INFO] S3 endpoint latency spike detected (P99: 4200ms vs baseline 180ms)",
                "Transient S3 network timeout during data read phase"
            ),
            FailureType.MODEL_DRIFT: (
                f"[WARN] Model drift detected for fraud_detection_v3\n"
                f"  PSI Score: 0.31 (threshold: 0.20)\n"
                f"  Feature 'transaction_amount' distribution shifted significantly\n"
                f"  Prediction mean: 0.83 -> 0.41 (last 24h vs training baseline)\n"
                f"[INFO] Model last retrained: 47 days ago",
                "Significant prediction distribution drift detected (PSI=0.31, threshold=0.20)"
            ),
            FailureType.UPSTREAM_DELAY: (
                f"[WARN] Job {job['job_name']} SLA breach detected\n"
                f"  Expected completion: 06:00 UTC\n"
                f"  Current runtime: 920s (P95 baseline: {job['p95_runtime_sec']}s)\n"
                f"[INFO] Upstream dependency 'raw_ingest_job' still running (started 03:45 UTC)\n"
                f"[WARN] Downstream jobs queued: customer_report_job, dashboard_refresh_job",
                f"SLA breach: job running 3x longer than P95 baseline due to upstream delay"
            ),
        }
        return logs_map.get(failure_type, ("[ERROR] Unknown failure", "Unknown failure type"))

    # ─── Production Mode ────────────────────────────────────────────────────

    async def _monitor_databricks(self) -> Optional[DetectedIncident]:
        """
        Production: polls the real Databricks Jobs API.
        Fetches latest failed run, extracts error logs and state message.
        Requires DATABRICKS_HOST, DATABRICKS_TOKEN, DATABRICKS_JOB_ID env vars.
        """
        try:
            from databricks.sdk import WorkspaceClient
            client = WorkspaceClient(
                host=os.environ["DATABRICKS_HOST"],
                token=os.environ["DATABRICKS_TOKEN"],
            )
            job_id = int(os.environ["DATABRICKS_JOB_ID"])
            runs = list(client.jobs.list_runs(job_id=job_id, limit=1))
            for run in runs:
                state = run.state
                if not state:
                    continue
                life = state.life_cycle_state.value if (state.life_cycle_state and hasattr(state.life_cycle_state, 'value')) else str(state.life_cycle_state or "")
                result = state.result_state.value if (state.result_state and hasattr(state.result_state, 'value')) else str(state.result_state or "")
                if life not in ("TERMINATED", "INTERNAL_ERROR") or result == "SUCCESS":
                    continue  # still running or succeeded — no incident

                error_msg = state.state_message or "Job failed with no state message"

                # Attempt to pull cluster logs from the run's tasks
                # Fetch actual Python error traces from each task's run output
                error_logs = error_msg
                actual_error_trace = ""
                try:
                    full_run = client.jobs.get_run(run_id=run.run_id)
                    tasks = full_run.tasks or []
                    log_lines = [f"[DATABRICKS] run_id={run.run_id} | state={life}/{result}"]
                    trace_parts = []
                    for task in tasks:
                        t_state = task.state
                        if t_state and t_state.state_message:
                            log_lines.append(f"[TASK:{task.task_key}] {t_state.state_message}")
                        # Get the actual Python error trace
                        if t_state and t_state.result_state and t_state.result_state.value != "SUCCESS":
                            try:
                                output = client.jobs.get_run_output(run_id=task.run_id)
                                if output.error_trace:
                                    trace_parts.append(f"Task '{task.task_key}':\n{output.error_trace}")
                                    log_lines.append(f"[TRACE:{task.task_key}]\n{output.error_trace}")
                                elif output.error:
                                    trace_parts.append(f"Task '{task.task_key}': {output.error}")
                                    log_lines.append(f"[ERROR:{task.task_key}] {output.error}")
                            except Exception:
                                pass
                    if trace_parts:
                        actual_error_trace = "\n\n".join(trace_parts)
                    error_logs = "\n".join(log_lines)
                except Exception:
                    pass  # fall back to state message only

                # Use actual Python error for classification and summary
                classify_on = actual_error_trace or error_msg
                error_summary = (actual_error_trace[:500] if actual_error_trace else error_msg[:200])

                # Classify failure type from error text
                failure_type = self._classify_failure(classify_on)

                logger.warning(
                    f"[DETECT] Databricks job {job_id} failed | "
                    f"run={run.run_id} | type={failure_type.value}"
                )
                return DetectedIncident(
                    incident_id=f"INC-{uuid.uuid4().hex[:8].upper()}",
                    job_name=str(run.run_name or f"job_{job_id}"),
                    failure_type=failure_type,
                    error_summary=error_summary,
                    error_logs=error_logs,
                    timestamp=datetime.utcnow(),
                    upstream_jobs=[],
                    affected_tables=[],
                    metrics={},
                )
        except Exception as e:
            logger.error(f"Databricks polling error: {e}")
        return None

    def _classify_failure(self, error_msg: str) -> FailureType:
        """Classify failure type from Databricks error message text."""
        msg = error_msg.lower()
        if any(k in msg for k in ["analysisexception", "cannot resolve", "schemamismatch", "schema"]):
            return FailureType.SCHEMA_DRIFT
        if any(k in msg for k in ["outofmemory", "oom", "gc overhead", "executor lost"]):
            return FailureType.CONFIG_MISMATCH
        if any(k in msg for k in ["null", "data quality", "completeness", "corrupt"]):
            return FailureType.DATA_CORRUPTION
        if any(k in msg for k in ["sla", "delay", "upstream", "dependency"]):
            return FailureType.UPSTREAM_DELAY
        if any(k in msg for k in ["drift", "psi", "distribution"]):
            return FailureType.MODEL_DRIFT
        # Default: treat as transient — attempt a retry before escalating
        return FailureType.TRANSIENT_FAILURE
