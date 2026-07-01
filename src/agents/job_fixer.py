"""
AEGIS JobFixerAgent
LLM-powered notebook repair: fetch → fix → upload → verify.
"""
import os
import asyncio
import base64
from typing import Dict
from loguru import logger
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.workspace import ImportFormat, Language
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from src.guardrails.audit_log import AuditLog
from src.guardrails.rate_limiter import RateLimiter
from src.guardrails.prompt_guard import (
    sanitize_error_log,
    sanitize_notebook_code,
    injection_resistant_system_message,
)
from src.guardrails.validators import (
    validate_python_code,
    lint_python_code,
    compute_diff,
)


class JobFixerAgent:
    """
    Autonomous notebook repair using GPT-5.5.

    Flow:
    1. Fetch notebook source from Databricks
    2. Call GPT-5.5 with error + code → surgical targeted fix
    3. Validate syntax, log diff, upload fixed notebook
    4. Trigger job run and monitor; rollback + retry on failure (max 3 attempts)
    """

    def __init__(self, host: str, token: str, config: dict):
        self.client = WorkspaceClient(host=host, token=token)
        # config is the FULL config dict; healing sub-config is at config["healing"]
        self.config = config
        self.healing_config = config.get("healing", config)
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
            azure_deployment=os.environ.get("DIAL_DEPLOYMENT", "gpt-5.5-2026-04-24"),  # GPT-5.5 for deep repair
            api_version=os.environ.get("DIAL_API_VERSION", "2025-04-01-preview"),
            temperature=1,      # reasoning models require temperature=1
            max_tokens=16000,   # reasoning model: reserves tokens for chain-of-thought + full code output
            request_timeout=300,  # 5 minutes — GPT-5.5 needs time for deep scan
        )

    async def fix_job(self, job_id: int, error_summary: str, incident_id: str, retry_attempt: int = 1, max_retries: int = 3) -> Dict:
        """
        Fix a failed job by repairing its notebooks with GPT-5.5.
        
        **AUTONOMOUS WORKFLOW:**
        1. Discover Databricks environment context
        2. Fetch past similar incidents as reference
        3. Call GPT-5.5 with full error trace → targeted fix (minimum change)
        4. Validate syntax + lint, log diff, upload fixed notebook
        5. Re-run job and verify; rollback + retry with new error on failure
        
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
        
        logger.info(f"[JobFixer] 🔍 Starting AUTONOMOUS repair for job {job_id} | incident={incident_id} | attempt={retry_attempt}/{max_retries}")
        AuditLog.record("FIX_STARTED", incident_id=incident_id, job_id=job_id, attempt=retry_attempt)
        
        # ───────────────────────────────────────────────────────────────────
        # GUARDRAIL #5: RATE LIMITER — check before doing ANY work
        # ───────────────────────────────────────────────────────────────────
        allowed, rate_reason = RateLimiter.check(job_id)
        if not allowed:
            AuditLog.record("RATE_LIMITED", incident_id=incident_id, job_id=job_id, reason=rate_reason)
            return {
                "status": "failed",
                "fixed_notebooks": [],
                "post_fix_run_id": None,
                "outcome": rate_reason,
            }

        try:
            # ═══════════════════════════════════════════════════════════════
            # PHASE 1: DISCOVER DATABRICKS CONTEXT
            # ═══════════════════════════════════════════════════════════════
            logger.info(f"[JobFixer] 📊 Phase 1: Discovering Databricks environment...")
            databricks_context = await self._discover_databricks_context()
            logger.success(f"[JobFixer] ✓ Context discovered: {len(databricks_context.get('tables', []))} tables found")

            # ═══════════════════════════════════════════════════════════════
            # PHASE 1b: FETCH PAST INCIDENTS (bug reference lookup)
            # ═══════════════════════════════════════════════════════════════
            logger.info(f"[JobFixer] 📚 Phase 1b: Looking up similar past incidents...")
            past_incidents = await self._fetch_past_incidents(error_summary)
            
            # ═══════════════════════════════════════════════════════════════
            # PHASE 2: FETCH NOTEBOOKS
            # ═══════════════════════════════════════════════════════════════
            logger.info(f"[JobFixer] 📄 Phase 2: Fetching notebook code...")
            job = self.client.jobs.get(job_id=job_id)
            notebooks = []
            for task in (job.settings.tasks or []):
                if task.notebook_task:
                    nb_path = task.notebook_task.notebook_path
                    exp = self.client.workspace.export(path=nb_path)
                    content = base64.b64decode(exp.content).decode("utf-8")
                    notebooks.append({"path": nb_path, "task_key": task.task_key, "content": content})
                    logger.info(f"[JobFixer] ✓ Fetched '{nb_path}' ({len(content)} chars)")
            
            if not notebooks:
                AuditLog.record("NO_NOTEBOOKS", incident_id=incident_id, job_id=job_id)
                return {
                    "status": "failed",
                    "fixed_notebooks": [],
                    "post_fix_run_id": None,
                    "outcome": "No notebook tasks found in job",
                }
            
            # Store original content for rollback (Guardrail #3)
            originals: Dict[str, str] = {nb["path"]: nb["content"] for nb in notebooks}
            
            # ═══════════════════════════════════════════════════════════════
            # PHASE 3: TARGETED ERROR FIX (GPT-5.5 — minimal surgical change)
            # ═══════════════════════════════════════════════════════════════
            logger.info(f"[JobFixer] 🔧 Phase 3: Targeted error fix (GPT-5.5)...")
            fixed_notebooks = []
            for nb in notebooks:
                logger.info(f"[JobFixer] 🔬 Fixing: {nb['path']}")
                fixed_content = await self._comprehensive_scan_and_fix(
                    notebook_content=nb["content"],
                    error_summary=error_summary,
                    databricks_context=databricks_context,
                    notebook_path=nb['path'],
                    past_incidents=past_incidents,
                )

                # ─── GUARDRAIL #4: LLM Output Validation ─────────────────
                is_valid, validation_error = validate_python_code(fixed_content, nb['path'])
                if not is_valid:
                    logger.error(f"[JobFixer] ❌ GUARDRAIL: LLM output failed syntax check — skipping upload")
                    AuditLog.record(
                        "LLM_OUTPUT_INVALID",
                        incident_id=incident_id,
                        job_id=job_id,
                        notebook_path=nb['path'],
                        error=validation_error,
                    )
                    return {
                        "status": "failed",
                        "fixed_notebooks": [],
                        "post_fix_run_id": None,
                        "outcome": f"LLM produced invalid Python code: {validation_error}",
                    }

                # ─── GUARDRAIL #4b: Lint Check ──────────────────────────
                lint_passed, lint_issues = lint_python_code(fixed_content, nb['path'])
                AuditLog.record(
                    "LINT_CHECK",
                    incident_id=incident_id,
                    job_id=job_id,
                    notebook_path=nb['path'],
                    passed=lint_passed,
                    issues=lint_issues[:5],  # log first 5
                )
                if not lint_passed:
                    logger.warning(f"[JobFixer] ⚠️  Lint issues found (non-blocking): {lint_issues[:3]}")

                # ─── GUARDRAIL #2: Notebook Diff Review ──────────────────
                diff_text = compute_diff(nb["content"], fixed_content, nb['path'])
                if not diff_text:
                    logger.warning(f"[JobFixer] ⚠️  GUARDRAIL: No changes detected — LLM returned identical code")
                    AuditLog.record("NO_DIFF", incident_id=incident_id, job_id=job_id, notebook_path=nb['path'])
                AuditLog.record(
                    "DIFF_COMPUTED",
                    incident_id=incident_id,
                    job_id=job_id,
                    notebook_path=nb['path'],
                    lines_changed=len(diff_text.splitlines()),
                )

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
                AuditLog.record(
                    "NOTEBOOK_UPLOADED",
                    incident_id=incident_id,
                    job_id=job_id,
                    notebook_path=nb['path'],
                )
            
            # Step 4: Trigger job run and monitor
            # ─── GUARDRAIL #5: Record trigger in rate limiter ─────────────
            RateLimiter.record_trigger(job_id)
            logger.info(f"[JobFixer] Triggering post-fix run for job {job_id} (remaining quota: {RateLimiter.remaining(job_id)})")
            run = self.client.jobs.run_now(job_id=job_id)
            run_id = run.run_id
            logger.success(f"[JobFixer] Post-fix run triggered: {run_id}")
            AuditLog.record("RUN_TRIGGERED", incident_id=incident_id, job_id=job_id, run_id=run_id)
            
            # Poll until terminal state
            for _ in range(60):  # max 5 min
                await asyncio.sleep(5)
                run_state = self.client.jobs.get_run(run_id=run_id)
                life = self._safe_enum(run_state.state.life_cycle_state) if run_state.state else "UNKNOWN"
                result = self._safe_enum(run_state.state.result_state) if (run_state.state and run_state.state.result_state) else None
                logger.info(f"[JobFixer] Post-fix run {run_id} state={life}/{result}")
                
                if life in ("TERMINATED", "INTERNAL_ERROR", "SKIPPED"):
                    if result == "SUCCESS":
                        AuditLog.record(
                            "FIX_SUCCESS",
                            incident_id=incident_id,
                            job_id=job_id,
                            run_id=run_id,
                            attempt=retry_attempt,
                        )
                        return {
                            "status": "success",
                            "fixed_notebooks": fixed_notebooks,
                            "post_fix_run_id": run_id,
                            "outcome": f"Job run {run_id} completed successfully after LLM repair (attempt {retry_attempt}/{max_retries}).",
                            "retry_attempt": retry_attempt,
                        }
                    else:
                        # ─── GUARDRAIL #3: ROLLBACK on post-fix failure ───
                        logger.warning(f"[JobFixer] 🔄 GUARDRAIL: Post-fix run failed — rolling back to original notebook")
                        for nb in fixed_notebooks:
                            original_content = originals.get(nb["path"])
                            if original_content:
                                try:
                                    encoded_orig = base64.b64encode(original_content.encode("utf-8")).decode("utf-8")
                                    self.client.workspace.import_(
                                        path=nb["path"],
                                        content=encoded_orig,
                                        format=ImportFormat.SOURCE,
                                        language=Language.PYTHON,
                                        overwrite=True,
                                    )
                                    logger.success(f"[JobFixer] ✅ Rolled back {nb['path']} to original")
                                    AuditLog.record(
                                        "NOTEBOOK_ROLLED_BACK",
                                        incident_id=incident_id,
                                        job_id=job_id,
                                        notebook_path=nb['path'],
                                        reason=f"post-fix run {run_id} failed",
                                    )
                                except Exception as rb_err:
                                    logger.error(f"[JobFixer] ❌ Rollback failed for {nb['path']}: {rb_err}")
                                    AuditLog.record(
                                        "ROLLBACK_FAILED",
                                        incident_id=incident_id,
                                        job_id=job_id,
                                        notebook_path=nb['path'],
                                        error=str(rb_err),
                                    )

                        # Post-fix run FAILED - should we retry?
                        if retry_attempt < max_retries:
                            logger.warning(f"[JobFixer] Post-fix run {run_id} still failed (attempt {retry_attempt}/{max_retries}). Extracting full error trace and retrying...")

                            # Extract full error trace from the failed run (same depth as StatusChecker)
                            new_error_summary = await self._extract_run_error(run_id)
                            logger.info(f"[JobFixer] New error extracted ({len(new_error_summary)} chars). Retrying fix (attempt {retry_attempt + 1}/{max_retries})...")
                            
                            return await self.fix_job(
                                job_id=job_id,
                                error_summary=new_error_summary,
                                incident_id=incident_id,
                                retry_attempt=retry_attempt + 1,
                                max_retries=max_retries,
                            )
                        else:
                            logger.error(f"[JobFixer] Max retries ({max_retries}) reached. Job {job_id} still failing after {retry_attempt} attempts.")
                            AuditLog.record(
                                "MAX_RETRIES_EXCEEDED",
                                incident_id=incident_id,
                                job_id=job_id,
                                attempts=retry_attempt,
                            )
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
            AuditLog.record("FIX_EXCEPTION", incident_id=incident_id, job_id=job_id, error=str(e))
            return {
                "status": "failed",
                "fixed_notebooks": [],
                "post_fix_run_id": None,
                "outcome": str(e),
            }

    async def _fetch_past_incidents(self, error_summary: str) -> list[dict]:
        """
        Look up similar past incidents from the knowledge store.
        These are passed to GPT-5.5 as bug references so it can learn
        from previous fixes rather than guessing from scratch.
        """
        try:
            from src.knowledge.incident_store import IncidentKnowledgeStore
            store = IncidentKnowledgeStore(
                self.config.get("knowledge_store", {"persist_dir": "./data/knowledge_store", "collection_name": "aegis_incidents"})
            )
            results = await store.find_similar(query=error_summary[:500], k=3)
            if results:
                logger.info(f"[JobFixer] 📚 Found {len(results)} similar past incident(s) for context")
            else:
                logger.info("[JobFixer] 📚 No similar past incidents found (first time seeing this error)")
            return results
        except Exception as e:
            logger.debug(f"[JobFixer] Past incident lookup skipped: {e}")
            return []

    async def _discover_databricks_context(self) -> dict:
        """
        Scan Databricks environment to understand available tables and schemas.
        This helps GPT-5.5 make context-aware fixes.
        """
        try:
            logger.info("[JobFixer] Querying Databricks for available tables and schemas...")
            
            # Try to list tables (this may fail if no databases exist, which is OK)
            tables_info = []
            try:
                # Get list of databases
                databases = list(self.client.catalogs.list())
                logger.info(f"[JobFixer] Found {len(databases)} catalogs/databases")
                
                # For demo/testing, we just note that tables exist
                # In production, you might query specific schemas
                tables_info.append({
                    "note": f"Databricks workspace has {len(databases)} catalog(s) available",
                    "catalogs": [db.name for db in databases[:5]]  # Sample first 5
                })
            except Exception as e:
                logger.debug(f"[JobFixer] Could not list catalogs: {e}")
                tables_info.append({
                    "note": "Could not enumerate tables (may be mock/test environment)",
                })
            
            return {
                "tables": tables_info,
                "environment": "databricks_workspace",
                "context_available": len(tables_info) > 0
            }
        except Exception as e:
            logger.warning(f"[JobFixer] Context discovery failed: {e} (continuing with code-only analysis)")
            return {
                "tables": [],
                "environment": "databricks_workspace",
                "context_available": False,
                "error": str(e)
            }

    async def _comprehensive_scan_and_fix(
        self,
        notebook_content: str,
        error_summary: str,
        databricks_context: Dict,
        notebook_path: str,
        past_incidents: list[dict] | None = None,
    ) -> str:
        """
        Targeted error fix: repair ONLY the lines that caused the job to fail.
        Logic, variable names, structure, and style are never changed.
        """
        # ─── Guardrail #7: Sanitise untrusted inputs before prompt interpolation ───
        safe_error = sanitize_error_log(error_summary)
        safe_code = sanitize_notebook_code(notebook_content)

        past_ref_str = ""
        if past_incidents:
            past_ref_str = "\n## Similar Past Incidents (reference only — do not copy fixes blindly)\n"
            for i, inc in enumerate(past_incidents, 1):
                past_ref_str += f"Reference #{i}: {inc}\n"

        prompt = (
            f"A Databricks notebook job failed with the error below. "
            f"Fix ONLY the lines that directly caused this error. Touch nothing else.\n\n"
            f"## Error to Fix\n"
            f"```\n{safe_error}\n```\n\n"
            f"## Notebook Source\n"
            f"**Path:** `{notebook_path}`\n"
            f"```python\n{safe_code}\n```\n\n"
            f"{past_ref_str}"
            f"## Non-Negotiable Rules\n"
            f"1. Fix ONLY what the error above points to. Do not touch unrelated code.\n"
            f"2. NEVER rename variables, functions, table names, or column names.\n"
            f"3. NEVER refactor, restructure, or rewrite working code sections.\n"
            f"4. NEVER add or remove imports unless they are the direct cause of the error.\n"
            f"5. NEVER add type hints, docstrings, or comments that were not there before.\n"
            f"6. NEVER reformat or restyle lines that are not part of the fix.\n"
            f"7. Preserve all Databricks magic comments exactly as-is "
            f"(# Databricks notebook source, # COMMAND ----------, # MAGIC).\n"
            f"8. The fix must be the MINIMUM change that makes the job pass.\n\n"
            f"## Output Format\n"
            f"Line 1: `FIX: <one sentence describing what you changed>`\n\n"
            f"Then the complete corrected notebook source:\n"
            f"```python\n"
            f"[full notebook with ONLY the error-causing lines corrected]\n"
            f"```"
        )

        _base_system = (
            "You are a surgical code repair tool. "
            "Your only job is to fix the specific error that caused a Databricks job to fail. "
            "You make the MINIMUM change required — nothing more. "
            "You never refactor, rename, restructure, or improve working code. "
            "You never add type hints, docstrings, style changes, or cosmetic edits. "
            "Every line of working code is treated as correct and sacred. "
            "A good fix changes as few lines as possible."
        )
        messages = [
            SystemMessage(content=injection_resistant_system_message(_base_system)),
            HumanMessage(content=prompt),
        ]

        logger.info(f"[JobFixer] 🔧 Invoking GPT-5.5 for targeted error fix...")
        try:
            response = await asyncio.wait_for(self.llm.ainvoke(messages), timeout=300)
        except asyncio.TimeoutError:
            raise Exception("GPT-5.5 request timed out after 300s — try again or check VPN/API status")
        full_response = response.content.strip()

        # Extract fix description and code
        if full_response.startswith("FIX:"):
            first_newline = full_response.find("\n")
            fix_line = full_response[:first_newline].strip() if first_newline != -1 else full_response
            logger.info(f"[JobFixer] 📋 {fix_line}")
            full_response = full_response[first_newline:].strip() if first_newline != -1 else ""

        # Strip code fences
        if "```python" in full_response:
            full_response = full_response.split("```python")[1].split("```")[0].strip()
        elif "```" in full_response:
            parts = full_response.split("```")
            full_response = parts[1].strip() if len(parts) > 1 else full_response

        logger.success(f"[JobFixer] ✅ Targeted fix generated ({len(full_response)} chars)")
        return full_response

    async def _extract_run_error(self, run_id: int) -> str:
        """Extract the full Python error trace from a failed run using get_run_output."""
        errors = []
        try:
            run = self.client.jobs.get_run(run_id=run_id)
            for task in (run.tasks or []):
                if not (task.state and task.state.result_state):
                    continue
                result_val = task.state.result_state.value if hasattr(task.state.result_state, "value") else str(task.state.result_state)
                if result_val == "SUCCESS":
                    continue
                try:
                    output = self.client.jobs.get_run_output(run_id=task.run_id)
                    if output.error_trace:
                        errors.append(f"Task '{task.task_key}':\n{output.error_trace}")
                    elif output.error:
                        errors.append(f"Task '{task.task_key}': {output.error}")
                    elif task.state.state_message:
                        errors.append(f"Task '{task.task_key}': {task.state.state_message}")
                except Exception:
                    if task.state.state_message:
                        errors.append(f"Task '{task.task_key}': {task.state.state_message}")
        except Exception as e:
            return f"Could not retrieve error details: {e}"
        return "\n\n".join(errors) if errors else f"Run {run_id} failed (no detailed error available)"

    def _map_to_git_path(self, databricks_path: str, task_key: str) -> str:
        """Map Databricks workspace path to git repository path."""
        # databricks_to_git_path is a top-level config key
        git_path_map = self.config.get("databricks_to_git_path", {})

        # Try direct lookup
        git_path = git_path_map.get(databricks_path)
        if git_path:
            return git_path

        # Try without .py extension (removesuffix strips only the exact suffix)
        git_path = git_path_map.get(databricks_path.removesuffix(".py"))
        if git_path:
            return git_path

        # Try basename match
        basename = databricks_path.rstrip("/").split("/")[-1].removesuffix(".py")
        for key, val in git_path_map.items():
            if key.rstrip("/").split("/")[-1].removesuffix(".py") == basename:
                return val

        # Fallback: use task key
        slug = task_key.replace(" ", "_").replace("-", "_").lower()
        return f"de_project/notebooks/{slug}.py"

    def _safe_enum(self, enum_val):
        """Safely extract value from Databricks SDK enum."""
        if enum_val is None:
            return ""
        return enum_val.value if hasattr(enum_val, "value") else str(enum_val)
