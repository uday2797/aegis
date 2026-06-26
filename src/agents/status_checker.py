"""
AEGIS StatusCheckerAgent
Monitors Databricks jobs and reports health status.

Can monitor:
1. All jobs in workspace (DAB jobs discovery)
2. Specific job by job_id
"""
import os
from typing import List, Dict, Optional
from loguru import logger
from databricks.sdk import WorkspaceClient


class StatusCheckerAgent:
    """
    Monitors Databricks jobs and reports health status.
    Returns JobHealthReport[] with job_id, name, status, error_summary.
    """

    def __init__(self, host: str, token: str):
        self.client = WorkspaceClient(host=host, token=token)
        self.host = host
        logger.info("[StatusChecker] Initialized")

    async def check_health(
        self,
        monitor_all_jobs: bool = False,
        specific_job_id: Optional[str] = None,
        dab_bundle_name: Optional[str] = None,
    ) -> List[Dict]:
        """
        Check health of Databricks jobs.
        
        Args:
            monitor_all_jobs: If True, discover and monitor all jobs in workspace
            specific_job_id: If provided, monitor only this job
            dab_bundle_name: If provided, filter jobs by DAB bundle tag
        
        Returns:
            List[JobHealthReport]:
                {
                    "job_id": str,
                    "job_name": str,
                    "status": "healthy" | "failed" | "unknown",
                    "last_run_id": int,
                    "error_summary": str,
                    "failed_tasks": List[str]
                }
        """
        logger.info(f"[StatusChecker] Checking health | all_jobs={monitor_all_jobs} | job_id={specific_job_id}")
        
        reports = []
        
        if specific_job_id:
            # Monitor single job
            report = await self._check_single_job(int(specific_job_id))
            reports.append(report)
        elif monitor_all_jobs:
            # Discover all jobs (optionally filter by DAB bundle)
            jobs = list(self.client.jobs.list())
            logger.info(f"[StatusChecker] Discovered {len(jobs)} jobs in workspace")
            
            for job in jobs:
                # Filter by DAB bundle if specified
                if dab_bundle_name:
                    job_tags = getattr(job.settings, "tags", {}) or {}
                    bundle_tag = job_tags.get("bundle", "") or job_tags.get("BUNDLE_NAME", "")
                    if dab_bundle_name not in bundle_tag:
                        continue
                
                report = await self._check_single_job(job.job_id)
                reports.append(report)
        
        healthy_count = sum(1 for r in reports if r["status"] == "healthy")
        failed_count = sum(1 for r in reports if r["status"] == "failed")
        logger.info(f"[StatusChecker] Health check complete | healthy={healthy_count} failed={failed_count}")
        
        return reports

    async def _check_single_job(self, job_id: int) -> Dict:
        """Check health of a single job by examining its latest run."""
        try:
            job = self.client.jobs.get(job_id=job_id)
            job_name = job.settings.name if job.settings else f"Job-{job_id}"
            
            # Get latest run
            runs = list(self.client.jobs.list_runs(job_id=job_id, limit=1))
            if not runs:
                return {
                    "job_id": str(job_id),
                    "job_name": job_name,
                    "status": "unknown",
                    "last_run_id": None,
                    "error_summary": "No runs found",
                    "failed_tasks": [],
                }
            
            run = runs[0]
            run_id = run.run_id
            
            # CRITICAL FIX: list_runs() returns lightweight Run without tasks
            # We must call get_run() to get full run details including task info
            logger.debug(f"[StatusChecker] Fetching full run details for run_id={run_id}")
            run = self.client.jobs.get_run(run_id=run_id)
            
            state = run.state
            
            # Safe enum access
            life = state.life_cycle_state.value if (state and state.life_cycle_state and hasattr(state.life_cycle_state, "value")) else "UNKNOWN"
            result = state.result_state.value if (state and state.result_state and hasattr(state.result_state, "value")) else None
            
            # Determine health status
            if life in ("TERMINATED", "INTERNAL_ERROR", "SKIPPED"):
                if result == "SUCCESS":
                    status = "healthy"
                    error_summary = ""
                    failed_tasks = []
                else:
                    status = "failed"
                    error_summary, failed_tasks = await self._extract_error(run)
            else:
                # Running or pending
                status = "healthy"
                error_summary = ""
                failed_tasks = []
            
            return {
                "job_id": str(job_id),
                "job_name": job_name,
                "status": status,
                "last_run_id": run_id,
                "error_summary": error_summary,
                "failed_tasks": failed_tasks,
            }
        
        except Exception as e:
            logger.error(f"[StatusChecker] Error checking job {job_id}: {e}")
            return {
                "job_id": str(job_id),
                "job_name": f"Job-{job_id}",
                "status": "unknown",
                "last_run_id": None,
                "error_summary": str(e),
                "failed_tasks": [],
            }

    async def _extract_error(self, run) -> tuple:
        """Extract error summary and failed task names from a failed run."""
        errors = []
        failed_tasks = []
        
        try:
            for task in (run.tasks or []):
                task_state = task.state
                if not task_state or not task_state.result_state:
                    continue
                
                result = task_state.result_state.value if hasattr(task_state.result_state, "value") else str(task_state.result_state)
                if result != "SUCCESS":
                    failed_tasks.append(task.task_key)
                    try:
                        output = self.client.jobs.get_run_output(run_id=task.run_id)
                        if output.error_trace:
                            logger.debug(f"[StatusChecker] Extracted error_trace for task '{task.task_key}': {output.error_trace[:500]}...")
                            errors.append(f"Task '{task.task_key}':\n{output.error_trace}")
                        elif output.error:
                            logger.debug(f"[StatusChecker] Extracted error for task '{task.task_key}': {output.error[:500]}...")
                            errors.append(f"Task '{task.task_key}': {output.error}")
                        else:
                            logger.warning(f"[StatusChecker] No error_trace or error field for task '{task.task_key}'")
                    except Exception as ex:
                        logger.warning(f"[StatusChecker] Failed to get run output for task '{task.task_key}': {ex}")
                        if task_state.state_message:
                            errors.append(f"Task '{task.task_key}': {task_state.state_message}")
        except Exception as e:
            logger.warning(f"[StatusChecker] Error extracting error details: {e}")
            return f"Run failed (error extraction failed: {e})", failed_tasks
        
        error_summary = "\n\n".join(errors) if errors else "Run failed (no detailed error available)"
        logger.info(f"[StatusChecker] Final error_summary length: {len(error_summary)} chars, failed_tasks: {failed_tasks}")
        return error_summary, failed_tasks
