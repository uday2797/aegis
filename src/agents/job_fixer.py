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

    async def fix_job(self, job_id: int, error_summary: str, incident_id: str) -> Dict:
        """
        Fix a failed job by repairing its notebooks with GPT-4o.
        
        Returns:
            {
                "status": "success" | "failed",
                "fixed_notebooks": List[{"path": str, "git_path": str, "content": str}],
                "post_fix_run_id": int,
                "outcome": str
            }
        """
        if not self.llm:
            return {
                "status": "failed",
                "fixed_notebooks": [],
                "post_fix_run_id": None,
                "outcome": "LLM not available (no DIAL_API_KEY)",
            }
        
        logger.info(f"[JobFixer] Fixing job {job_id} | incident={incident_id}")
        
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
                            "outcome": f"Job run {run_id} completed successfully after LLM repair.",
                        }
                    else:
                        return {
                            "status": "failed",
                            "fixed_notebooks": fixed_notebooks,
                            "post_fix_run_id": run_id,
                            "outcome": f"Post-fix run {run_id} still failed. Manual review required.",
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
        """Use GPT-4o to fix notebook bugs."""
        prompt = (
            f"A Databricks notebook failed with this PYTHON ERROR:\n\n"
            f"```\n{error_summary}\n```\n\n"
            f"Here is the notebook source code:\n\n"
            f"```python\n{notebook_content}\n```\n\n"
            f"INSTRUCTIONS:\n"
            f"1. Read the Python error trace carefully\n"
            f"2. Identify the EXACT line and bug (common issues: import typos, undefined variables, division by zero, type errors)\n"
            f"3. Fix ALL bugs in the notebook\n"
            f"4. Keep the Databricks format exactly (# Databricks notebook source header and # COMMAND ---------- separators)\n"
            f"5. Return ONLY the corrected Python source code\n"
            f"6. No explanations, no markdown code fences around your response"
        )
        messages = [
            SystemMessage(content="You are an expert Databricks/Python engineer. Analyze Python errors carefully and fix notebook bugs precisely. Return only corrected source code."),
            HumanMessage(content=prompt),
        ]
        response = await self.llm.ainvoke(messages)
        fixed = response.content.strip()
        
        # Strip code fences if GPT-4o added them
        if fixed.startswith("```"):
            parts = fixed.split("```")
            fixed = parts[1] if len(parts) > 1 else fixed
            if fixed.startswith("python"):
                fixed = fixed[6:]
            fixed = fixed.strip()
        
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
