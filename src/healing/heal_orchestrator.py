"""
AEGIS Self-Healing Orchestrator
Executes the appropriate healing action based on RCA result and policy decision.
All actions are idempotent and safe to retry.

Production mode: makes real Databricks SDK calls (job retrigger, run cancel).
Simulation mode: fast asyncio.sleep stubs for demo.
"""
import asyncio
import os
from loguru import logger
from src.models import RCAResult, HealResult, HealStatus, FailureType


def _databricks_client():
    """Returns a Databricks WorkspaceClient using env vars. Raises if not configured."""
    from databricks.sdk import WorkspaceClient
    return WorkspaceClient(
        host=os.environ["DATABRICKS_HOST"],
        token=os.environ["DATABRICKS_TOKEN"],
    )


def _ev(v) -> str:
    """Safely extract string from a Databricks SDK Enum or plain string."""
    if v is None:
        return ""
    return v.value if hasattr(v, "value") else str(v)


class HealOrchestrator:
    """
    Routes healing actions based on failure type.
    Each action is isolated, logged, and returns a structured result.
    """

    def __init__(self, config: dict, simulation_mode: bool = True):
        self.config = config
        self.simulation_mode = simulation_mode
        self._job_id = os.environ.get("DATABRICKS_JOB_ID", "")

    async def heal(self, rca: RCAResult, incident_id: str) -> HealResult:
        logger.info(f"[HEAL] Executing auto-heal for {incident_id} | type={rca.failure_type.value}")

        action_map = {
            FailureType.TRANSIENT_FAILURE: self._retry_with_backoff,
            FailureType.UPSTREAM_DELAY: self._wait_and_retrigger,
            FailureType.DATA_CORRUPTION: self._rollback_and_retrigger,
            FailureType.SCHEMA_DRIFT: self._adapt_schema,
            FailureType.MODEL_DRIFT: self._rollback_model_and_retrain,
            FailureType.DATA_QUALITY: self._quarantine_and_backfill,
            FailureType.CONFIG_MISMATCH: self._generate_config_fix,
        }

        # In production mode, skip retries — go straight to LLM notebook repair
        if not self.simulation_mode and self._job_id:
            action_fn = self._direct_llm_heal
        else:
            action_fn = action_map.get(rca.failure_type, self._escalate_unknown)
        result = await action_fn(rca, incident_id)
        logger.success(f"[HEAL] Done | status={result.status} | action='{result.action_taken}'")
        return result

    # ─── Healing Actions ─────────────────────────────────────────────────────

    async def _direct_llm_heal(self, rca: RCAResult, incident_id: str) -> HealResult:
        """Production fast-path: fetch last error, call GPT-4o once, fix & run."""
        api_key = os.environ.get("DIAL_API_KEY")
        if not api_key:
            logger.warning("[HEAL] No DIAL_API_KEY — falling back to retry")
            return await self._retry_with_backoff(rca, incident_id)
        try:
            client = _databricks_client()
            job_id = int(self._job_id)
            # Fetch error from the most recent failed run
            runs = list(client.jobs.list_runs(job_id=job_id, limit=1))
            last_error = ""
            if runs:
                last_error = await self._get_run_error(client, runs[0].run_id)
            if not last_error:
                last_error = rca.root_cause  # fallback to LLM-inferred cause
            logger.info("[HEAL] Direct LLM path — skipping retries, fixing notebook now")
            return await self._fix_notebook_and_retry(incident_id, last_error, client, job_id)
        except Exception as e:
            logger.error(f"[HEAL] Direct LLM heal failed: {e}")
            return HealResult(
                incident_id=incident_id,
                status=HealStatus.ESCALATED,
                action_taken="LLM heal encountered an error — escalated",
                outcome=str(e),
                approval_required=True,
            )

    async def _retry_with_backoff(self, rca: RCAResult, incident_id: str) -> HealResult:
        max_retries = self.config.get("retry", {}).get("max_retries", 3)
        backoff = self.config.get("retry", {}).get("backoff_seconds", 30)
        logger.info(f"[HEAL] Retry | max_retries={max_retries} backoff={backoff}s")

        if not self.simulation_mode and self._job_id:
            return await self._databricks_run_now(incident_id, max_retries, backoff)

        # ── Simulation ──
        await asyncio.sleep(1)
        return HealResult(
            incident_id=incident_id,
            status=HealStatus.AUTO_HEALED,
            action_taken=f"Retried job with exponential backoff (max {max_retries} retries, {backoff}s intervals)",
            outcome="Job completed successfully on retry attempt 1. No data loss detected.",
            has_code_fix=False,
        )

    async def _databricks_run_now(self, incident_id: str, max_retries: int, backoff: int) -> HealResult:
        """Triggers a real Databricks job run via the SDK. Falls through to LLM notebook repair if all retries fail."""
        try:
            client = _databricks_client()
            job_id = int(self._job_id)
            last_error = ""
            for attempt in range(1, max_retries + 1):
                logger.info(f"[HEAL] Databricks run_now | job_id={job_id} attempt={attempt}")
                run = client.jobs.run_now(job_id=job_id)
                run_id = run.run_id
                logger.success(f"[HEAL] Triggered run_id={run_id} on job {job_id}")
                # Poll until terminal state
                for _ in range(60):   # max 5 min wait (60 × 5s)
                    await asyncio.sleep(5)
                    run_state = client.jobs.get_run(run_id=run_id)
                    life = _ev(run_state.state.life_cycle_state) if run_state.state else "UNKNOWN"
                    result = _ev(run_state.state.result_state) if run_state.state and run_state.state.result_state else None
                    logger.info(f"[HEAL] run_id={run_id} state={life}/{result}")
                    if life in ("TERMINATED", "INTERNAL_ERROR", "SKIPPED"):
                        if result == "SUCCESS":
                            return HealResult(
                                incident_id=incident_id,
                                status=HealStatus.AUTO_HEALED,
                                action_taken=f"Triggered Databricks job retry (run_id={run_id}, attempt {attempt}/{max_retries})",
                                outcome=f"Job run {run_id} completed successfully. State: {life}/{result}.",
                                has_code_fix=False,
                            )
                        # Capture actual error trace for LLM repair
                        last_error = await self._get_run_error(client, run_id)
                        logger.warning(f"[HEAL] Run {run_id} failed ({result}) — will retry if attempts remain")
                        break
                if attempt < max_retries:
                    logger.info(f"[HEAL] Waiting {backoff}s before next attempt...")
                    await asyncio.sleep(backoff)

            # All retries exhausted — escalate to LLM notebook repair if DIAL is available
            api_key = os.environ.get("DIAL_API_KEY")
            if api_key and last_error:
                logger.info("[HEAL] Retries exhausted — escalating to LLM notebook repair...")
                return await self._fix_notebook_and_retry(incident_id, last_error, client, job_id)

            return HealResult(
                incident_id=incident_id,
                status=HealStatus.ESCALATED,
                action_taken=f"Databricks job retry exhausted ({max_retries} attempts)",
                outcome="All retry attempts failed — escalating to on-call engineer.",
                approval_required=True,
            )
        except Exception as e:
            logger.error(f"[HEAL] Databricks retry failed: {e}")
            return HealResult(
                incident_id=incident_id,
                status=HealStatus.ESCALATED,
                action_taken="Databricks retry call failed — escalated",
                outcome=str(e),
                approval_required=True,
            )

    async def _get_run_error(self, client, run_id: int) -> str:
        """Extract actual Python error trace from Databricks task run output."""
        try:
            run = client.jobs.get_run(run_id=run_id)
            errors = []
            for task in (run.tasks or []):
                if task.state and task.state.result_state and _ev(task.state.result_state) != "SUCCESS":
                    try:
                        output = client.jobs.get_run_output(run_id=task.run_id)
                        if output.error_trace:
                            errors.append(f"Task '{task.task_key}':\n{output.error_trace}")
                        elif output.error:
                            errors.append(f"Task '{task.task_key}': {output.error}")
                    except Exception:
                        if task.state.state_message:
                            errors.append(f"Task '{task.task_key}': {task.state.state_message}")
            return "\n\n".join(errors) if errors else "Workload failed (no detailed error available)"
        except Exception as e:
            return f"Could not retrieve error details: {e}"

    async def _fix_notebook_and_retry(self, incident_id: str, error_summary: str, client, job_id: int) -> HealResult:
        """Delegate to JobFixerAgent — single canonical repair path for both entry points."""
        from src.agents.job_fixer import JobFixerAgent

        logger.info("[HEAL] Delegating to JobFixerAgent for surgical notebook repair...")
        try:
            fixer = JobFixerAgent(
                host=os.environ["DATABRICKS_HOST"],
                token=os.environ["DATABRICKS_TOKEN"],
                config=self.config,
            )
            result = await fixer.fix_job(
                job_id=job_id,
                error_summary=error_summary,
                incident_id=incident_id,
            )
            if result["status"] == "success":
                fixed_notebooks = result.get("fixed_notebooks", [])
                run_id = result.get("post_fix_run_id")
                return HealResult(
                    incident_id=incident_id,
                    status=HealStatus.AUTO_HEALED,
                    action_taken=f"GPT-5.5 surgically fixed {len(fixed_notebooks)} notebook(s) (run_id={run_id})",
                    outcome=result.get("outcome", "Job completed successfully after repair."),
                    has_code_fix=True,
                    fix_files=[
                        {"path": nb["git_path"], "content": nb["content"], "description": "AEGIS surgical fix"}
                        for nb in fixed_notebooks
                    ],
                )
            return HealResult(
                incident_id=incident_id,
                status=HealStatus.ESCALATED,
                action_taken="JobFixerAgent repair did not succeed",
                outcome=result.get("outcome", "Fix failed — manual review required."),
                has_code_fix=bool(result.get("fixed_notebooks")),
                approval_required=True,
            )
        except Exception as e:
            logger.error(f"[HEAL] JobFixerAgent delegation failed: {e}")
            return HealResult(
                incident_id=incident_id,
                status=HealStatus.ESCALATED,
                action_taken="Notebook repair encountered an error — escalated",
                outcome=str(e),
                approval_required=True,
            )

    async def _wait_and_retrigger(self, rca: RCAResult, incident_id: str) -> HealResult:
        logger.info("[HEAL] WaitAndRetrigger | monitoring upstream job completion")

        if not self.simulation_mode and self._job_id:
            # Cancel any active run then retrigger
            try:
                client = _databricks_client()
                job_id = int(self._job_id)
                runs = list(client.jobs.list_runs(job_id=job_id, active_only=True, limit=1))
                if runs:
                    client.jobs.cancel_run(run_id=runs[0].run_id)
                    logger.info(f"[HEAL] Cancelled stale run {runs[0].run_id}")
                return await self._databricks_run_now(incident_id, max_retries=1, backoff=0)
            except Exception as e:
                logger.error(f"[HEAL] Retrigger failed: {e}")

        await asyncio.sleep(1)
        return HealResult(
            incident_id=incident_id,
            status=HealStatus.AUTO_HEALED,
            action_taken="Monitored upstream job completion, retriggered downstream pipeline",
            outcome="Upstream job completed at +18min. Downstream pipeline retriggered successfully. SLA breach window: 18 minutes.",
            has_code_fix=False,
        )

    async def _rollback_and_retrigger(self, rca: RCAResult, incident_id: str) -> HealResult:
        logger.info("[HEAL] DeltaRollback | rolling back to last known good version")
        await asyncio.sleep(1.5)
        return HealResult(
            incident_id=incident_id,
            status=HealStatus.AUTO_HEALED,
            action_taken="Rolled back Delta table to version N-1 (last known good), retriggered pipeline",
            outcome="Table restored to pre-corruption state. Pipeline retriggered with clean data. 342,000 affected rows recovered.",
            has_code_fix=False,
        )

    async def _adapt_schema(self, rca: RCAResult, incident_id: str) -> HealResult:
        logger.info("[HEAL] SchemaAdaptation | generating column mapping patch")
        await asyncio.sleep(1.5)
        fix_content = '''# AEGIS Auto-Generated Schema Fix
# Incident: {incident_id}
# Root Cause: Column renamed from txn_amount to transaction_amount

-- models/staging/stg_transactions.sql
SELECT
    transaction_amount AS txn_amount,  -- AEGIS fix: mapped renamed column
    user_id,
    ts,
    merchant_id
FROM {{{{ source("payments", "transactions") }}}}
'''.format(incident_id=incident_id)

        return HealResult(
            incident_id=incident_id,
            status=HealStatus.AUTO_HEALED,
            action_taken="Generated schema mapping patch (txn_amount -> transaction_amount), applied to staging layer",
            outcome="Column mapping applied. Pipeline retriggered with schema fix. All downstream tables recovering.",
            has_code_fix=True,
            fix_files=[{
                "path": "models/staging/stg_transactions.sql",
                "content": fix_content,
                "description": "Schema column mapping fix for renamed upstream field"
            }],
        )

    async def _rollback_model_and_retrain(self, rca: RCAResult, incident_id: str) -> HealResult:
        logger.info("[HEAL] ModelRollback | rolling back to stable model version and triggering retraining")
        await asyncio.sleep(1.5)
        return HealResult(
            incident_id=incident_id,
            status=HealStatus.AUTO_HEALED,
            action_taken="Rolled back fraud_detection_v3 to v2 (last stable). Triggered retraining pipeline with last 30 days of data.",
            outcome="Model serving switched to v2 (precision: 91%). Retraining job queued. Estimated completion: 4 hours.",
            has_code_fix=False,
        )

    async def _quarantine_and_backfill(self, rca: RCAResult, incident_id: str) -> HealResult:
        logger.info("[HEAL] Quarantine | isolating bad partition and triggering backfill")
        await asyncio.sleep(1)
        return HealResult(
            incident_id=incident_id,
            status=HealStatus.AUTO_HEALED,
            action_taken="Quarantined corrupted partition (2024-06-25/batch_003), triggered backfill from source",
            outcome="Bad data isolated. Backfill job running. Downstream jobs paused pending clean data confirmation.",
            has_code_fix=False,
        )

    async def _generate_config_fix(self, rca: RCAResult, incident_id: str) -> HealResult:
        logger.info("[HEAL] ConfigFix | generating IaC configuration patch")
        await asyncio.sleep(1)
        fix_content = '''# AEGIS Auto-Generated Config Fix
# Incident: {incident_id}

spark:
  executor:
    memory: "8g"          # Increased from 4g (OOM fix)
    memoryOverhead: "2g"  # Added to prevent executor OOM
  driver:
    memory: "4g"
  sql:
    shuffle:
      partitions: 400     # Tuned for dataset size
'''.format(incident_id=incident_id)

        return HealResult(
            incident_id=incident_id,
            status=HealStatus.AUTO_HEALED,
            action_taken="Generated Spark config patch for memory settings, applied to job configuration",
            outcome="Config updated. Job retriggered with new memory settings. Monitoring for OOM recurrence.",
            has_code_fix=True,
            fix_files=[{
                "path": "config/spark_job_config.yaml",
                "content": fix_content,
                "description": "Spark executor memory configuration fix"
            }],
        )

    async def _escalate_unknown(self, rca: RCAResult, incident_id: str) -> HealResult:
        return HealResult(
            incident_id=incident_id,
            status=HealStatus.ESCALATED,
            action_taken="Unknown failure type — escalated to on-call engineer",
            outcome="Pending human investigation",
            approval_required=True,
        )
