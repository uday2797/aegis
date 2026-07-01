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

from src.guardrails.audit_log import AuditLog
from src.guardrails.rate_limiter import RateLimiter
from src.guardrails.prompt_guard import (
    sanitize_error_log,
    sanitize_notebook_code,
    sanitize_for_prompt,
    injection_resistant_system_message,
)
from src.guardrails.validators import (
    validate_python_code,
    lint_python_code,
    autoformat_code,
    compute_diff,
)


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
        1. Scan Databricks environment (tables, schemas, columns)
        2. Deep scan entire notebook (identify ALL bugs)
        3. Generate comprehensive fix (all bugs in one pass)
        4. Upload fixed notebook
        5. Verify with test run
        
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
            # PHASE 3: DEEP SCAN & COMPREHENSIVE FIX (ALL BUGS IN ONE PASS)
            # ═══════════════════════════════════════════════════════════════
            logger.info(f"[JobFixer] 🧠 Phase 3: Deep scan + comprehensive fix (GPT-5.5)...")
            fixed_notebooks = []
            for nb in notebooks:
                logger.info(f"[JobFixer] 🔬 Scanning: {nb['path']}")
                
                # Use enhanced prompt with Databricks context + past incidents
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

                # ─── PEP8 Auto-Format ───────────────────────────────
                fixed_content = autoformat_code(fixed_content)
                AuditLog.record(
                    "PEP8_FORMATTED",
                    incident_id=incident_id,
                    job_id=job_id,
                    notebook_path=nb['path'],
                )

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
                                new_error_summary = f"Run {run_id} failed with result_state={result}. No detailed error available."
                            
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
        PHASE 3: Deep scan entire notebook + comprehensive fix.
        
        This uses an enhanced 2-step prompt:
        1. First, GPT-5.5 scans and lists ALL bugs
        2. Then generates one comprehensive fix for everything
        """
        
        # ─── Guardrail #7: Sanitise untrusted inputs before prompt interpolation ───
        safe_error = sanitize_error_log(error_summary)
        safe_code = sanitize_notebook_code(notebook_content)

        # Build Databricks context string
        context_str = "**Databricks Environment:**\n"
        if databricks_context.get("context_available"):
            context_str += f"- {len(databricks_context.get('tables', []))} database(s) detected\n"
            if databricks_context.get('tables'):
                context_str += f"- Sample catalogs: {', '.join([t.get('note', '') for t in databricks_context['tables'][:3]])}\n"
        else:
            context_str += "- Running in isolated/test environment (no live tables detected)\n"

        # Build past-incidents reference block
        past_ref_str = ""
        if past_incidents:
            past_ref_str = "\n## Bug References — Similar Past Incidents\n"
            past_ref_str += "These are real incidents AEGIS has fixed before. Use them as hints:\n\n"
            for i, inc in enumerate(past_incidents, 1):
                past_ref_str += f"**Reference #{i}:** {inc}\n\n"
        else:
            past_ref_str = "\n## Bug References\nNo similar past incidents found — rely on code analysis.\n"

        prompt = (
            f"🤖 AEGIS AUTONOMOUS NOTEBOOK REPAIR\n\n"
            f"## Mission: DEEP SCAN → LIST ALL BUGS → FIX EVERYTHING → PEP8 CLEAN\n\n"
            f"You are an autonomous reliability AI. A Databricks notebook has failed in production.\n"
            f"Your job: scan the ENTIRE notebook, understand it deeply, identify ALL bugs, then fix everything in ONE pass.\n\n"
            f"## Databricks Context\n"
            f"{context_str}\n"
            f"{past_ref_str}\n"
            f"## Current Error (What Triggered This Scan)\n"
            f"```\n{safe_error}\n```\n\n"
            f"## Full Notebook Source Code\n"
            f"**Path:** `{notebook_path}`\n"
            f"```python\n{safe_code}\n```\n\n"
            f"## AUTONOMOUS WORKFLOW\n\n"
            f"### STEP 1: DEEP SCAN (Understand Everything)\n"
            f"Read through the ENTIRE notebook carefully. Understand:\n"
            f"- What is this notebook trying to do?\n"
            f"- What tables/data does it reference?\n"
            f"- What transformations/calculations are being performed?\n"
            f"- What is the intended data flow?\n\n"
            f"### STEP 2: IDENTIFY ALL BUGS (Complete Audit)\n"
            f"Scan EVERY line and identify ALL bugs. Check for:\n\n"
            f"**Syntax & Import Errors:** Import typos, missing imports, undefined variables\n"
            f"**Schema/Data Errors:** Wrong table names (typos), wrong column names, non-existent columns\n"
            f"**Math/Logic Errors:** Division by zero, reversed conditions, off-by-one errors\n"
            f"**PySpark/DataFrame Errors:** Wrong groupBy columns, missing F.col() wrappers, incorrect aggregations\n"
            f"**Runtime Errors:** Variables used before assignment, wrong function signatures, type mismatches\n"
            f"**PEP8/Style Issues:** Lines > 120 chars, bare excepts, magic numbers without comments\n\n"
            f"### STEP 3: LIST ALL BUGS FOUND\n"
            f"Before fixing, explicitly list every bug. Format: `BUG #X: [description]`\n\n"
            f"### STEP 4: FIX ALL BUGS (One Comprehensive Fix)\n"
            f"Generate corrected code that fixes EVERY bug you listed.\n\n"
            f"**Functional Requirements:**\n"
            f"✅ Fix ALL import errors | Fix ALL table/column name typos\n"
            f"✅ Define ALL variables before use | Add safety checks for divisions\n"
            f"✅ Correct ALL logic errors | Fix ALL PySpark syntax issues\n\n"
            f"**Code Quality Requirements (PEP8):**\n"
            f"✅ Follow PEP8: 4-space indentation, max 120 chars per line\n"
            f"✅ Use descriptive variable names (no single-letter vars except loop counters)\n"
            f"✅ Add type hints on all function definitions\n"
            f"✅ Use f-strings for string formatting (not .format() or %)\n"
            f"✅ No bare `except:` — always catch specific exceptions\n"
            f"✅ Two blank lines between top-level functions/classes\n"
            f"✅ Imports grouped: stdlib → third-party → local\n\n"
            f"### STEP 5: OUTPUT FORMAT\n"
            f"Return your response in TWO sections:\n\n"
            f"**Section 1: BUG REPORT**\n"
            f"```\n"
            f"BUGS FOUND:\n"
            f"BUG #1: [description]\n"
            f"BUG #2: [description]\n"
            f"...\n"
            f"TOTAL: X bugs identified\n"
            f"```\n\n"
            f"**Section 2: FIXED CODE**\n"
            f"```python\n"
            f"[corrected PEP8-compliant notebook code with ALL bugs fixed]\n"
            f"```\n\n"
            f"⚠️ CRITICAL: Fix EVERY bug in ONE pass. Code must be PEP8-compliant and production-ready."
        )
        
        _base_system = (
            "You are AEGIS, an elite autonomous AI reliability engineer and senior Python developer. "
            "You specialize in deep code analysis, comprehensive bug fixing, and writing clean, production-grade code. "
            "You NEVER do partial fixes. You scan thoroughly, identify ALL issues, then fix everything at once. "
            "You are an expert in PySpark, Databricks, Python, and data engineering. "
            "You ALWAYS write PEP8-compliant code: proper indentation, descriptive names, type hints, specific exception handling. "
            "You think systematically: understand → scan → reference past bugs → list → fix → clean."
        )
        messages = [
            SystemMessage(content=injection_resistant_system_message(_base_system)),
            HumanMessage(content=prompt),
        ]

        logger.info(f"[JobFixer] 🧠 Invoking GPT-5.5 for deep scan + comprehensive fix...")
        try:
            response = await asyncio.wait_for(self.llm.ainvoke(messages), timeout=300)
        except asyncio.TimeoutError:
            raise Exception("GPT-5.5 request timed out after 300s — try again or check VPN/API status")
        full_response = response.content.strip()
        
        # Parse response: extract bug list and fixed code
        if "BUGS FOUND:" in full_response and "FIXED CODE" in full_response:
            parts = full_response.split("FIXED CODE")
            bug_list = parts[0]
            fixed_code_section = parts[1] if len(parts) > 1 else full_response
            
            # Log the bug list
            logger.info(f"[JobFixer] 📋 Bug Analysis:\n{bug_list[:1000]}")  # First 1000 chars
            
            # Extract just the code
            fixed = fixed_code_section.strip()
        else:
            # Fallback if format not followed
            fixed = full_response
        
        # Strip code fences if present
        if "```python" in fixed:
            fixed = fixed.split("```python")[1].split("```")[0].strip()
        elif "```" in fixed:
            parts = fixed.split("```")
            fixed = parts[1] if len(parts) > 1 else fixed
            fixed = fixed.strip()
        
        logger.success(f"[JobFixer] ✅ Comprehensive fix completed. Fixed code: {len(fixed)} chars")
        return fixed

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
