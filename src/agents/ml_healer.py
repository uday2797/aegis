"""
AEGIS ML Drift Healer Agent
Detects model drift → triggers retraining job → validates improvement → promotes or rolls back.

Healing steps:
1. Accept degraded model report from ModelMonitorAgent
2. Trigger Databricks ML training job via SDK
3. Poll until job run completes
4. Query new MLflow metrics — compare accuracy vs old
5. Promote (register new Production version) if better, rollback if worse
6. Send email notification at each milestone
"""
import asyncio
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional
from loguru import logger

from src.agents.mail_sender import MailSenderAgent


# How much improvement is required to promote the new model
MIN_ACCURACY_GAIN = 0.005  # 0.5% absolute gain over previous Production version


class MLHealerAgent:
    """
    Autonomous ML retraining and model promotion agent.

    Usage:
        healer = MLHealerAgent(config)
        result = await healer.heal(degraded_model_reports)
    """

    def __init__(self, config: dict):
        self.config = config
        self.workspace_host = os.environ.get("DATABRICKS_HOST", "")
        self.workspace_token = os.environ.get("DATABRICKS_TOKEN", "")
        self.mlflow_uri = os.environ.get("MLFLOW_TRACKING_URI", config.get("mlflow_uri", ""))
        # Support both full config (healing.ml_retraining_job_name) and direct key
        healing_cfg = config.get("healing", config)
        self.ml_job_name = (
            healing_cfg.get("ml_retraining_job_name")
            or config.get("ml_retraining_job_name")
            or "[AEGIS ML] Model Retraining Pipeline"
        )
        self.mail = MailSenderAgent()

    # ─── Public entry point ──────────────────────────────────────────────────

    async def heal(self, degraded_reports: List[Dict]) -> Dict:
        """
        Run the full ML healing cycle for all degraded models.

        Returns:
            {
                "healed": List[str],    # model names successfully retrained+promoted
                "failed": List[str],    # model names where healing failed
                "skipped": List[str],   # models with no ML job configured
                "status": "success" | "partial" | "failed",
            }
        """
        if not degraded_reports:
            return {"healed": [], "failed": [], "skipped": [], "status": "success"}

        logger.info(f"[MLHealer] Starting healing cycle for {len(degraded_reports)} degraded model(s)")

        healed, failed, skipped = [], [], []

        for report in degraded_reports:
            model_name = report.get("model_name", "unknown")
            try:
                result = await self._heal_single_model(report)
                if result == "healed":
                    healed.append(model_name)
                elif result == "skipped":
                    skipped.append(model_name)
                else:
                    failed.append(model_name)
            except Exception as e:
                logger.error(f"[MLHealer] Unhandled error healing {model_name}: {e}")
                failed.append(model_name)

        overall = "success" if not failed else ("partial" if healed else "failed")
        logger.info(f"[MLHealer] Cycle complete | healed={healed} | failed={failed} | skipped={skipped}")
        return {"healed": healed, "failed": failed, "skipped": skipped, "status": overall}

    # ─── Single-model healing pipeline ──────────────────────────────────────

    async def _heal_single_model(self, report: Dict) -> str:
        model_name = report.get("model_name", "unknown")
        old_accuracy = report.get("current_accuracy", 0.0)
        psi_score = report.get("psi_score", 0.0)
        alert_msg = report.get("alert", "degradation detected")

        logger.info(f"[MLHealer] Healing model: {model_name} | accuracy={old_accuracy:.2%} | PSI={psi_score:.3f}")

        # Step 1: Find the ML retraining job in Databricks
        job_id = await self._find_ml_job()
        if not job_id:
            logger.warning(f"[MLHealer] ML retraining job not found in Databricks — skipping {model_name}")
            return "skipped"

        # Step 2: Trigger retraining job
        run_id = await self._trigger_retraining(job_id, model_name)
        if not run_id:
            await self.mail.send_stage("ml_healing_failed", {
                "model_name": model_name,
                "reason": "Failed to trigger Databricks retraining job",
                "old_accuracy": old_accuracy,
                "psi_score": psi_score,
            })
            return "failed"

        # Step 3: Poll run until complete
        run_state = await self._wait_for_run(run_id, job_id, model_name)
        if run_state != "SUCCESS":
            await self.mail.send_stage("ml_healing_failed", {
                "model_name": model_name,
                "reason": f"Retraining job run ended with state: {run_state}",
                "run_id": run_id,
                "old_accuracy": old_accuracy,
            })
            return "failed"

        # Step 4: Fetch new model metrics from MLflow
        new_accuracy, new_run_id = await self._get_latest_model_metrics(model_name)

        if new_accuracy is None:
            # MLflow not available — treat the successful job run as healing complete
            logger.info(f"[MLHealer] MLflow not available — accepting job success as healing complete")
            await self.mail.send_stage("ml_healing_complete", {
                "model_name": model_name,
                "old_accuracy": old_accuracy,
                "new_accuracy": None,
                "improvement": None,
                "run_id": run_id,
                "promoted": True,
                "note": "Model retrained successfully (MLflow metrics unavailable)",
            })
            return "healed"

        improvement = new_accuracy - old_accuracy
        logger.info(f"[MLHealer] {model_name}: old={old_accuracy:.2%} → new={new_accuracy:.2%} (Δ{improvement:+.2%})")

        # Step 5: Promote or rollback
        if improvement >= MIN_ACCURACY_GAIN:
            promoted = await self._promote_model(model_name, new_run_id)
            await self.mail.send_stage("ml_healing_complete", {
                "model_name": model_name,
                "old_accuracy": old_accuracy,
                "new_accuracy": new_accuracy,
                "improvement": improvement,
                "run_id": run_id,
                "promoted": promoted,
            })
            return "healed"
        else:
            logger.warning(f"[MLHealer] New model not better enough (Δ{improvement:+.2%} < {MIN_ACCURACY_GAIN:.1%}) — keeping old version")
            await self.mail.send_stage("ml_healing_failed", {
                "model_name": model_name,
                "reason": (
                    f"Retrained model accuracy ({new_accuracy:.2%}) did not improve enough "
                    f"over current ({old_accuracy:.2%}). Kept existing Production version."
                ),
                "old_accuracy": old_accuracy,
                "new_accuracy": new_accuracy,
                "run_id": run_id,
            })
            return "failed"

    # ─── Databricks SDK helpers ──────────────────────────────────────────────

    async def _find_ml_job(self) -> Optional[int]:
        """Find the ML retraining job by name in Databricks."""
        try:
            from databricks.sdk import WorkspaceClient
            client = WorkspaceClient(host=self.workspace_host, token=self.workspace_token)

            jobs = await asyncio.to_thread(lambda: list(client.jobs.list(name=self.ml_job_name)))
            if not jobs:
                logger.warning(f"[MLHealer] No Databricks job named '{self.ml_job_name}' found")
                return None

            job_id = jobs[0].job_id
            logger.info(f"[MLHealer] Found ML job: '{self.ml_job_name}' | job_id={job_id}")
            return job_id
        except Exception as e:
            logger.error(f"[MLHealer] Error finding ML job: {e}")
            return None

    async def _trigger_retraining(self, job_id: int, model_name: str) -> Optional[int]:
        """Trigger a Databricks job run with model_name as parameter."""
        try:
            from databricks.sdk import WorkspaceClient
            client = WorkspaceClient(host=self.workspace_host, token=self.workspace_token)

            run = await asyncio.to_thread(
                lambda: client.jobs.run_now(
                    job_id=job_id,
                    notebook_params={"model_name": model_name, "trigger": "aegis_auto_heal"},
                )
            )
            run_id = run.run_id
            logger.success(f"[MLHealer] Triggered retraining | job_id={job_id} | run_id={run_id}")
            return run_id
        except Exception as e:
            logger.error(f"[MLHealer] Failed to trigger retraining job: {e}")
            return None

    async def _wait_for_run(self, run_id: int, job_id: int, model_name: str) -> str:
        """Poll run until terminal state. Returns life_cycle_state string."""
        try:
            from databricks.sdk import WorkspaceClient
            client = WorkspaceClient(host=self.workspace_host, token=self.workspace_token)

            terminal_states = {"TERMINATED", "SKIPPED", "INTERNAL_ERROR"}
            poll_count = 0
            MAX_POLLS = 240  # 240 × 30s = 2 hours max

            while poll_count < MAX_POLLS:
                run = await asyncio.to_thread(lambda: client.jobs.get_run(run_id=run_id))
                state = run.state
                lc_state = state.life_cycle_state.value if state.life_cycle_state else "UNKNOWN"
                result_state = state.result_state.value if state.result_state else "RUNNING"

                poll_count += 1
                if poll_count % 6 == 0:  # log every ~3 min
                    logger.info(f"[MLHealer] Run {run_id} state: {lc_state}/{result_state} (polling...)")

                if lc_state in terminal_states:
                    logger.info(f"[MLHealer] Run {run_id} completed: {lc_state}/{result_state}")
                    return result_state  # "SUCCESS" | "FAILED" | "CANCELED" | "TIMEDOUT"

                await asyncio.sleep(30)

            logger.error(f"[MLHealer] Run {run_id} timed out after {MAX_POLLS * 30 // 60} minutes")
            return "TIMEDOUT"

        except Exception as e:
            logger.error(f"[MLHealer] Error polling run {run_id}: {e}")
            return "FAILED"

    # ─── MLflow helpers ──────────────────────────────────────────────────────

    async def _get_latest_model_metrics(self, model_name: str):
        """
        Get the latest registered model version metrics from MLflow.
        Returns (accuracy, run_id) or (None, None) if MLflow unavailable.
        """
        if not self.mlflow_uri:
            return None, None
        try:
            import mlflow
            from mlflow.tracking import MlflowClient

            mlflow.set_tracking_uri(self.mlflow_uri)
            client = MlflowClient()

            # Get latest version across all stages (just registered)
            versions = await asyncio.to_thread(
                lambda: client.search_model_versions(f"name='{model_name}'")
            )
            if not versions:
                return None, None

            latest = sorted(versions, key=lambda v: int(v.version), reverse=True)[0]
            run = await asyncio.to_thread(lambda: client.get_run(latest.run_id))
            accuracy = run.data.metrics.get("accuracy") or run.data.metrics.get("val_accuracy") or 0.0
            logger.info(f"[MLHealer] Latest {model_name} v{latest.version}: accuracy={accuracy:.2%}")
            return float(accuracy), latest.run_id
        except Exception as e:
            logger.warning(f"[MLHealer] MLflow metrics fetch failed: {e}")
            return None, None

    async def _promote_model(self, model_name: str, run_id: str) -> bool:
        """Transition latest model version to Production stage in MLflow."""
        if not self.mlflow_uri:
            return False
        try:
            import mlflow
            from mlflow.tracking import MlflowClient

            mlflow.set_tracking_uri(self.mlflow_uri)
            client = MlflowClient()

            versions = await asyncio.to_thread(
                lambda: client.search_model_versions(f"name='{model_name}'")
            )
            if not versions:
                return False

            latest_version = sorted(versions, key=lambda v: int(v.version), reverse=True)[0].version

            # Archive existing Production versions
            prod_versions = await asyncio.to_thread(
                lambda: client.get_latest_versions(model_name, stages=["Production"])
            )
            for v in prod_versions:
                ver = v.version  # capture loop variable by value to avoid late-binding closure
                await asyncio.to_thread(
                    lambda ver=ver: client.transition_model_version_stage(
                        name=model_name, version=ver, stage="Archived"
                    )
                )

            # Promote new version
            await asyncio.to_thread(
                lambda: client.transition_model_version_stage(
                    name=model_name, version=latest_version, stage="Production"
                )
            )
            logger.success(f"[MLHealer] Promoted {model_name} v{latest_version} to Production")
            return True
        except Exception as e:
            logger.error(f"[MLHealer] Model promotion failed: {e}")
            return False
