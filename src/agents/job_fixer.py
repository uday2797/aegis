"""
AEGIS JobFixerAgent
LLM-powered notebook repair: fetch → fix → upload → verify.
"""
import os
import asyncio
import base64
from typing import Dict, List
from loguru import logger
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.workspace import ImportFormat, Language
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage


class JobFixerAgent:
    """
    Autonomous notebook repair using GPT-4o.
    
    Flow:
    1. Fetch notebook source from Databricks
    2. Call GPT-4o with error + code → get fixed code
    3. Upload fixed notebook to Databricks
    4. Trigger job run and monitor to completion
    """

    def __init__(self, host: str, token: str, config: dict):
        self.client = WorkspaceClient(host=host, token=token)
        self.config = config
        self.llm = self._init_llm()
        logger.info("[JobFixer] Initialized")

    def _init_llm(self):
        """Initialize GPT-4o via EPAM DIAL API."""
        api_key = os.environ.get("DIAL_API_KEY")
        if not api_key:
            logger.warning("[JobFixer] No DIAL_API_KEY — LLM repair unavailable")
            return None
        
        return AzureChatOpenAI(
            azure_endpoint=os.environ.get("DIAL_API_ENDPOINT", "https://ai-proxy.lab.epam.com"),
            api_key=api_key,
            azure_deployment=os.environ.get("DIAL_DEPLOYMENT", "gpt-5.5-2026-04-24"),
            api_version=os.environ.get("DIAL_API_VERSION", "2025-04-01-preview"),
            temperature=0,
            max_tokens=4000,
            request_timeout=60,
        )

    async def fix_job(self, job_id: int, error_summary: str, incident_id: str, retry_attempt: int = 1, max_retries: int = 3) -> Dict:
        """
        Fix a failed job by repairing its notebooks with GPT-5.5.
        Automatically retries if post-fix run fails (up to max_retries attempts).
        
        Returns:
            {
                "status": "success" | "failed",
                "fixed_notebooks": List[{"path": str, "git_path": str, "content": str}],
                "post_fix_run_id": int,
                "outcome": str,
                "retry_attempt": int
            }
        """
        if not self.llm:
            return {
                "status": "failed",
                "fixed_notebooks": [],
                "post_fix_run_id": None,
                "outcome": "LLM not available (no DIAL_API_KEY)",
            }
        
        logger.info(f"[JobFixer] Fixing job {job_id} | incident={incident_id} | attempt={retry_attempt}/{max_retries}")
        
        try:
            # Step 1: Fetch notebook tasks
            job = self.client.jobs.get(job_id=job_id)
            notebooks = []
            for task in (job.settings.tasks or []):
                if task.notebook_task:
                    nb_path = task.notebook_task.notebook_path
                    exp = self.client.workspace.export(path=nb_path)
                    content = base64.b64decode(exp.content).decode("utf-8")
                    notebooks.append({"path": nb_path, "task_key": task.task_key, "content": content})
                    logger.info(f"[JobFixer] Fetched notebook '{nb_path}' ({len(content)} chars)")
            
            if not notebooks:
                return {
                    "status": "failed",
                    "fixed_notebooks": [],
                    "post_fix_run_id": None,
                    "outcome": "No notebook tasks found in job",
                }
            
            # Step 2: Fix each notebook with GPT-4o
            fixed_notebooks = []
            for nb in notebooks:
                logger.info(f"[JobFixer] GPT-5.5 fixing: {nb['path']}")
                fixed_content = await self._fix_notebook_with_llm(nb["content"], error_summary)
                
                # Map to git path
                git_path = self._map_to_git_path(nb["path"], nb["task_key"])
                fixed_notebooks.append({
                    "path": nb["path"],
                    "git_path": git_path,
                    "content": fixed_content,
                })
                logger.success(f"[JobFixer] Fixed {nb['path']} → git: {git_path}")
            
            # Step 3: Upload fixed notebooks to Databricks
            for nb in fixed_notebooks:
                encoded = base64.b64encode(nb["content"].encode("utf-8")).decode("utf-8")
                self.client.workspace.import_(
                    path=nb["path"],
                    content=encoded,
                    format=ImportFormat.SOURCE,
                    language=Language.PYTHON,
                    overwrite=True,
                )
                logger.success(f"[JobFixer] Uploaded fixed notebook → {nb['path']}")
            
            # Step 4: Trigger job run and monitor
            logger.info(f"[JobFixer] Triggering post-fix run for job {job_id}")
            run = self.client.jobs.run_now(job_id=job_id)
            run_id = run.run_id
            logger.success(f"[JobFixer] Post-fix run triggered: {run_id}")
            
            # Poll until terminal state
            for _ in range(60):  # max 5 min
                await asyncio.sleep(5)
                run_state = self.client.jobs.get_run(run_id=run_id)
                life = self._safe_enum(run_state.state.life_cycle_state) if run_state.state else "UNKNOWN"
                result = self._safe_enum(run_state.state.result_state) if (run_state.state and run_state.state.result_state) else None
                logger.info(f"[JobFixer] Post-fix run {run_id} state={life}/{result}")
                
                if life in ("TERMINATED", "INTERNAL_ERROR", "SKIPPED"):
                    if result == "SUCCESS":
                        return {
                            "status": "success",
                            "fixed_notebooks": fixed_notebooks,
                            "post_fix_run_id": run_id,
                            "outcome": f"Job run {run_id} completed successfully after LLM repair (attempt {retry_attempt}/{max_retries}).",
                            "retry_attempt": retry_attempt,
                        }
                    else:
                        # Post-fix run FAILED - should we retry?
                        if retry_attempt < max_retries:
                            logger.warning(f"[JobFixer] Post-fix run {run_id} still failed (attempt {retry_attempt}/{max_retries}). Extracting new error and retrying...")
                            
                            # Extract NEW error from the latest failed run
                            await asyncio.sleep(2)  # Brief pause
                            new_run = self.client.jobs.get_run(run_id=run_id)
                            new_error_summary = ""
                            
                            # Extract error from failed tasks
                            if new_run.tasks:
                                for task in new_run.tasks:
                                    if task.state and task.state.result_state:
                                        state_val = task.state.result_state.value if hasattr(task.state.result_state, 'value') else str(task.state.result_state)
                                        if state_val in ("FAILED", "INTERNAL_ERROR"):
                                            # Get detailed error
                                            if hasattr(task.state, 'state_message') and task.state.state_message:
                                                new_error_summary += f"Task {task.task_key}: {task.state.state_message}\n"
                            
                            if not new_error_summary:
                                new_error_summary = f"Run {run_id} failed with result_state={result_state}. No detailed error available."
                            
                            logger.info(f"[JobFixer] New error extracted ({len(new_error_summary)} chars). Retrying fix (attempt {retry_attempt + 1}/{max_retries})...")
                            
                            # Recursive retry with the NEW error
                            return await self.fix_job(
                                job_id=job_id,
                                error_summary=new_error_summary[:10000],  # Limit size
                                incident_id=incident_id,
                                retry_attempt=retry_attempt + 1,
                                max_retries=max_retries
                            )
                        else:
                            logger.error(f"[JobFixer] Max retries ({max_retries}) reached. Job {job_id} still failing after {retry_attempt} attempts.")
                            return {
                                "status": "failed",
                                "fixed_notebooks": fixed_notebooks,
                                "post_fix_run_id": run_id,
                                "outcome": f"Post-fix run {run_id} still failed after {max_retries} attempts. Manual review required.",
                                "retry_attempt": retry_attempt,
                            }
            
            # Timeout
            return {
                "status": "failed",
                "fixed_notebooks": fixed_notebooks,
                "post_fix_run_id": run_id,
                "outcome": f"Post-fix run {run_id} timed out after 5 min.",
            }
        
        except Exception as e:
            logger.error(f"[JobFixer] Fix failed: {e}")
            return {
                "status": "failed",
                "fixed_notebooks": [],
                "post_fix_run_id": None,
                "outcome": str(e),
            }

    async def _fix_notebook_with_llm(self, notebook_content: str, error_summary: str) -> str:
        """Use GPT-5.5 to comprehensively scan and fix ALL notebook bugs in ONE comprehensive fix."""
        prompt = (
            f"🚨 CRITICAL: AUTONOMOUS PRODUCTION NOTEBOOK REPAIR\n\n"
            f"## Mission\n"
            f"A Databricks notebook has failed in production. You must perform a DEEP SCAN of the ENTIRE notebook "
            f"and fix ALL bugs in ONE comprehensive repair - not just the immediate error.\n\n"
            f"## Current Error That Triggered This Scan\n"
            f"```\n{error_summary}\n```\n\n"
            f"## Full Notebook Source Code (SCAN EVERY LINE)\n"
            f"```python\n{notebook_content}\n```\n\n"
            f"## MANDATORY WORKFLOW\n\n"
            f"### PHASE 1: DEEP CODE SCAN (Find ALL Bugs)\n"
            f"Scan EVERY single line and identify ALL bugs, not just what caused the current error.\n\n"
            f"**Bug Categories to Check:**\n"
            f"1. **Import Errors**\n"
            f"   - Typos in module names (e.g., 'pandsa' → 'pandas')\n"
            f"   - Missing imports\n"
            f"   - Wrong import paths\n\n"
            f"2. **Table/Column Name Errors**\n"
            f"   - Typos in table names (e.g., 'transformed_sales_dataa' with extra 'a')\n"
            f"   - Wrong column references (e.g., 'price' when it should be 'unit_price')\n"
            f"   - Case sensitivity issues\n\n"
            f"3. **Undefined Variables**\n"
            f"   - Variables used before being defined\n"
            f"   - Misspelled variable names\n"
            f"   - Wrong scope references\n\n"
            f"4. **Math/Division Errors**\n"
            f"   - Division by zero (e.g., `x / quantity` when quantity can be 0)\n"
            f"   - Missing null checks\n"
            f"   - Literal zero in denominator (e.g., `100 / 0`)\n\n"
            f"5. **Logic Errors**\n"
            f"   - Reversed conditions (e.g., `< 1000` when it should be `>= 1000`)\n"
            f"   - Wrong boolean operators (AND vs OR)\n"
            f"   - Incorrect filter logic\n\n"
            f"6. **Data Aggregation Errors**\n"
            f"   - Wrong groupBy columns (e.g., grouping by 'customer_name' instead of 'customer_id')\n"
            f"   - Missing aggregate functions\n"
            f"   - Wrong column aliases\n\n"
            f"7. **PySpark/DataFrame Errors**\n"
            f"   - Wrong Spark function syntax\n"
            f"   - Missing F.col() wrappers\n"
            f"   - Incorrect .withColumn() usage\n\n"
            f"8. **File Path Errors**\n"
            f"   - Wrong output paths\n"
            f"   - Missing /mnt/ prefixes\n"
            f"   - Incorrect Delta Lake paths\n\n"
            f"### PHASE 2: FIX ALL BUGS (Not Just One)\n"
            f"Generate corrected code that fixes EVERY bug you found.\n\n"
            f"**Requirements:**\n"
            f"✅ Fix ALL imports (correct all typos)\n"
            f"✅ Fix ALL table/column names (remove typos, use correct names)\n"
            f"✅ Define ALL variables before use\n"
            f"✅ Add null/zero checks for ALL divisions\n"
            f"✅ Correct ALL logic errors (filters, conditions, operators)\n"
            f"✅ Fix ALL aggregation functions (correct groupBy, correct columns)\n"
            f"✅ Use proper PySpark syntax throughout\n"
            f"✅ Ensure the notebook will run from start to finish without ANY errors\n\n"
            f"### PHASE 3: OUTPUT FORMAT\n"
            f"Return ONLY the corrected Python source code with:\n"
            f"- Exact Databricks format (# Databricks notebook source, # COMMAND ---------- separators)\n"
            f"- NO explanations\n"
            f"- NO markdown code fences (```python)\n"
            f"- NO comments about what you changed\n"
            f"- JUST the clean, production-ready, bug-free code\n\n"
            f"⚠️ CRITICAL: This is AUTONOMOUS healing. No human will manually fix remaining bugs. "
            f"You MUST fix ALL bugs in this ONE pass or the pipeline stays broken. "
            f"Scan every line. Fix everything. Leave ZERO bugs."
        )
        messages = [
            SystemMessage(content=(
                "You are AEGIS Autonomous Reliability AI. You are an elite code auditor and production debugger. "
                "When given a notebook, you perform DEEP SCANS and fix ALL bugs in ONE comprehensive pass. "
                "You never do partial fixes. You scan EVERY line, identify EVERY bug, and fix EVERYTHING at once. "
                "You have expert knowledge of PySpark, Databricks, Pandas, and data engineering. "
                "You think like a senior SRE doing a thorough code review - nothing escapes your audit."
            )),
            HumanMessage(content=prompt),
        ]
        
        logger.info(f"[JobFixer] Invoking GPT-5.5 for COMPREHENSIVE notebook scan and repair...")
        response = await self.llm.ainvoke(messages)
        fixed = response.content.strip()
        
        # Strip code fences if GPT-4o added them
        if fixed.startswith("```"):
            parts = fixed.split("```")
            fixed = parts[1] if len(parts) > 1 else fixed
            if fixed.startswith("python"):
                fixed = fixed[6:]
            fixed = fixed.strip()
        
        logger.success(f"[JobFixer] GPT-5.5 completed comprehensive repair. Fixed code: {len(fixed)} chars")
        return fixed

    def _map_to_git_path(self, databricks_path: str, task_key: str) -> str:
        """Map Databricks workspace path to git repository path."""
        git_path_map = self.config.get("databricks_to_git_path", {})
        
        # Try direct lookup
        git_path = git_path_map.get(databricks_path)
        if git_path:
            return git_path
        
        # Try without .py extension
        git_path = git_path_map.get(databricks_path.rstrip(".py"))
        if git_path:
            return git_path
        
        # Fallback: use task key
        slug = task_key.replace(" ", "_").replace("-", "_").lower()
        return f"de_project/notebooks/{slug}.py"

    def _safe_enum(self, enum_val):
        """Safely extract value from Databricks SDK enum."""
        if enum_val is None:
            return ""
        return enum_val.value if hasattr(enum_val, "value") else str(enum_val)
