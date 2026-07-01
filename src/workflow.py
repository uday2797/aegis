"""
AEGIS LangGraph Multi-Agent Workflow
Orchestrates the full autonomous reliability lifecycle.

Enhanced Workflow Stages (15 nodes):
0. Interactive Job Selection → User selects job(s) to monitor
1. Status Check → Email (healthy or failed)
2. If failed → RCA → Fix → Verify Post-Fix Run
3. Create PR → Email (PR raised)
4. Wait for PR approval (INDEFINITE - no timeout)
5. Trigger CD → Monitor deployment
6. Post-Deployment Health Verification (re-run status check)
7. If healthy → Final confirmation email
8. If still failing → Deployment failed email (escalate to human)
"""
import os
from typing import TypedDict, Annotated, Literal
from loguru import logger
from langgraph.graph import StateGraph, END

from src.agents.status_checker import StatusCheckerAgent
from src.agents.mail_sender import MailSenderAgent
from src.agents.job_fixer import JobFixerAgent
from src.agents.pr_manager import PRManagerAgent
from src.agents.deployment import DeploymentAgent
from src.agents.model_monitor import ModelMonitorAgent
from src.diagnosis.rca_agent import RCAAgent
from src.guardrails.audit_log import AuditLog
from src.reporting.incident_report import generate_incident_report

# Confidence threshold below which AEGIS escalates instead of auto-fixing
RCA_CONFIDENCE_THRESHOLD = 70.0  # percent


# ─── State Definition ────────────────────────────────────────────────────────


class AEGISState(TypedDict):
    """Global state shared across all agents."""
    
    # Configuration
    workspace_host: str
    workspace_token: str
    monitor_all_jobs: bool
    monitor_ml_models: bool
    specific_job_id: str | None
    dab_bundle_name: str | None
    config: dict
    
    # Status Check Results
    job_health_reports: list[dict]
    has_failures: bool
    healthy_count: int
    failed_count: int
    
    # Current incident being processed
    current_incident_id: str | None
    current_job_id: str | None
    current_job_name: str | None
    current_error_summary: str | None
    
    # RCA Results
    root_cause: str | None
    confidence: float
    risk_level: str
    
    # Fix Results
    fix_status: str | None  # "success" | "failed"
    fixed_notebooks: list[dict]
    post_fix_run_id: int | None
    mttr_seconds: float
    
    # PR Management
    pr_url: str | None
    pr_number: int
    pr_merged: bool
    merge_sha: str | None
    
    # Deployment
    workflow_run_url: str | None
    deployment_status: str | None
    post_deployment_healthy: bool
    
    # Email tracking
    emails_sent: list[str]
    
    # Job selection
    available_jobs: list[dict]  # List of all jobs from Databricks
    user_selected_job_id: str | None  # User's choice: specific job_id or "all"
    
    # Model health monitoring
    model_health_reports: list[dict]

    # ML healing results
    ml_degraded_models: list[dict]
    ml_heal_result: dict | None

    # Generated incident report (populated at end of cycle)
    incident_report: dict | None

    # Loop control
    current_stage: str


# ─── Agent Node Functions ────────────────────────────────────────────────────


async def job_selector_node(state: AEGISState) -> AEGISState:
    """
    Interactive job selection at startup.
    Lists all Databricks jobs and lets user choose which to monitor.
    """
    logger.info("[Workflow] Stage: job_selector")
    
    from databricks.sdk import WorkspaceClient
    from tabulate import tabulate
    
    client = WorkspaceClient(
        host=state["workspace_host"],
        token=state["workspace_token"]
    )
    
    # Fetch all jobs
    logger.info("[JobSelector] Fetching all Databricks jobs...")
    all_jobs = []
    
    try:
        for job in client.jobs.list():
            # Get latest run status if available
            latest_status = "UNKNOWN"
            try:
                runs = list(client.jobs.list_runs(job_id=job.job_id, limit=1))
                if runs:
                    run = runs[0]
                    if run.state and run.state.result_state:
                        latest_status = run.state.result_state.value
            except Exception as e:
                logger.warning(f"[JobSelector] Could not fetch run status for job {job.job_id}: {e}")
        print("🛡️  AEGIS - Autonomous Excellence Guardian & Intelligent System")
        print("=" * 100)
        print(f"\n📋 Found {len(all_jobs)} Databricks jobs:\n")
        
        table_data = [
            [
                job["job_id"],
                job["name"][:50] + ("..." if len(job["name"]) > 50 else ""),
                job["tasks"],
                "✅ SUCCESS" if job["latest_status"] == "SUCCESS" else 
                "❌ FAILED" if job["latest_status"] in ("FAILED", "INTERNAL_ERROR") else 
                "⏳ " + job["latest_status"]
            ]
            for job in all_jobs
        ]
        
        print(tabulate(
            table_data,
            headers=["Job ID", "Job Name", "Tasks", "Latest Status"],
            tablefmt="grid"
        ))
        
        # Prompt user for selection
        print("\n" + "─" * 100)
        print("📌 Select which job(s) to monitor:")
        print("   • Enter a Job ID to monitor a specific job")
        print("   • Enter comma-separated Job IDs to monitor multiple jobs: e.g., 123,456,789")
        print("   • Enter 'all' to monitor all jobs")
        print("   • Press Ctrl+C to exit")
        print("─" * 100 + "\n")
        
        while True:
            try:
                selection = input("Your selection: ").strip()
                
                if selection.lower() == "all":
                    state["user_selected_job_id"] = "all"
                    state["monitor_all_jobs"] = True
                    state["specific_job_id"] = None
                    logger.success(f"[JobSelector] Monitoring ALL {len(all_jobs)} jobs")
                    break
                elif "," in selection:
                    # Multiple job IDs (comma-separated)
                    try:
                        job_ids = [int(x.strip()) for x in selection.split(",")]
                        # Verify all jobs exist
                        valid_job_ids = [jid for jid in job_ids if any(job["job_id"] == jid for job in all_jobs)]
                        invalid_job_ids = [jid for jid in job_ids if jid not in valid_job_ids]
                        
                        if invalid_job_ids:
                            print(f"❌ Job IDs not found: {', '.join(map(str, invalid_job_ids))}. Please try again.")
                        elif valid_job_ids:
                            state["user_selected_job_id"] = ",".join(map(str, valid_job_ids))
                            state["monitor_all_jobs"] = False
                            state["specific_job_id"] = None  # Multiple jobs, not single
                            logger.success(f"[JobSelector] Monitoring {len(valid_job_ids)} jobs: {valid_job_ids}")
                            break
                        else:
                            print("❌ No valid job IDs provided. Please try again.")
                    except ValueError:
                        print("❌ Invalid format. Use comma-separated numbers: e.g., 123,456,789")
                elif selection.isdigit():
                    job_id = int(selection)
                    # Verify job exists
                    if any(job["job_id"] == job_id for job in all_jobs):
                        state["user_selected_job_id"] = str(job_id)
                        state["monitor_all_jobs"] = False
                        state["specific_job_id"] = str(job_id)
                        job_name = next(job["name"] for job in all_jobs if job["job_id"] == job_id)
                        logger.success(f"[JobSelector] Monitoring job {job_id}: {job_name}")
                        break
                    else:
                        print(f"❌ Job ID {job_id} not found. Please try again.")
                else:
                    print("❌ Invalid input. Enter Job ID(s) or 'all'.")
            except KeyboardInterrupt:
                print("\n\n⚠️  Selection cancelled. Exiting AEGIS...")
                import sys
                sys.exit(0)
        
        # ── ML monitoring opt-in ────────────────────────────────────────
        print("\n" + "─" * 100)
        print("🤖 ML Model Monitoring (optional):")
        print("   AEGIS can also check your MLflow-registered models for accuracy drop and data drift.")
        print("   If drift is detected, it will autonomously trigger retraining via Databricks job.")
        print("─" * 100)
        while True:
            try:
                ml_choice = input("Monitor ML models? (y/n): ").strip().lower()
                if ml_choice in ("y", "yes"):
                    state["monitor_ml_models"] = True
                    print("✅ ML model monitoring enabled — will check MLflow registry after job check.\n")
                    break
                elif ml_choice in ("n", "no"):
                    state["monitor_ml_models"] = False
                    print("⏭️  ML model monitoring skipped.\n")
                    break
                else:
                    print("❌ Please enter y or n.")
            except KeyboardInterrupt:
                state["monitor_ml_models"] = False
                print("\n⏭️  ML monitoring skipped.\n")
                break

        print("✅ Selection complete. Starting health monitoring...\n")
        state["current_stage"] = "job_selected"

    except Exception as e:
        logger.error(f"[JobSelector] Failed to list jobs: {e}")
        # Fallback: use configured job_id or monitor all
        if state.get("specific_job_id"):
            logger.warning(f"[JobSelector] Using configured job_id: {state['specific_job_id']}")
            state["user_selected_job_id"] = state["specific_job_id"]
            state["monitor_all_jobs"] = False
        else:
            logger.warning("[JobSelector] Defaulting to monitor all jobs")
            state["user_selected_job_id"] = "all"
            state["monitor_all_jobs"] = True
        state.setdefault("monitor_ml_models", False)
        state["current_stage"] = "job_selected"
    
    return state


async def status_check_node(state: AEGISState) -> AEGISState:
    """Check health of selected job(s) from interactive selection."""
    logger.info("[Workflow] Stage: status_check")
    
    # Parse user's selection from job_selector_node
    user_selection = state.get("user_selected_job_id") or state.get("specific_job_id")
    
    if user_selection == "all":
        monitor_all = True
        specific_job = None
    elif "," in str(user_selection):
        # Multiple specific jobs - check each one
        monitor_all = False
        specific_job = None
        # We'll handle multiple jobs below
    else:
        monitor_all = False
        specific_job = user_selection
    
    agent = StatusCheckerAgent(state["workspace_host"], state["workspace_token"])
    
    # If user selected multiple specific jobs, check each one
    if "," in str(user_selection) and user_selection != "all":
        job_ids = [int(x.strip()) for x in user_selection.split(",")]
        reports = []
        for job_id in job_ids:
            job_reports = await agent.check_health(
                monitor_all_jobs=False,
                specific_job_id=str(job_id),
            )
            reports.extend(job_reports)
    else:
        # Single job or all jobs
        reports = await agent.check_health(
            monitor_all_jobs=monitor_all,
            specific_job_id=str(specific_job) if specific_job else None,
        )
    
    state["job_health_reports"] = reports
    state["healthy_count"] = sum(1 for r in reports if r["status"] == "healthy")
    state["failed_count"] = sum(1 for r in reports if r["status"] == "failed")
    state["has_failures"] = state["failed_count"] > 0

    # ── Model health check (only if user opted in) ──────────────────────
    try:
        if not state.get("monitor_ml_models", False):
            logger.info("[Workflow] ML monitoring skipped (user opted out)")
            state["model_health_reports"] = []
        else:
            model_agent = ModelMonitorAgent(state.get("config", {}))
            model_reports = await model_agent.check_model_health()
            state["model_health_reports"] = model_reports
            degraded = [r for r in model_reports if r.get("status") != "healthy"]
            if degraded:
                logger.warning(
                    f"[Workflow] ⚠️  {len(degraded)} model(s) with drift/degradation detected"
                )
            else:
                logger.success("[Workflow] ✅ All ML models healthy")
    except Exception as e:
        logger.warning(f"[Workflow] Model health check skipped: {e}")
        state["model_health_reports"] = []

    state["current_stage"] = "status_checked"

    return state


async def initial_email_node(state: AEGISState) -> AEGISState:
    """Send initial health check email."""
    logger.info("[Workflow] Stage: initial_email")

    agent = MailSenderAgent()
    await agent.send_stage("initial_health_check", {
        "healthy_count": state["healthy_count"],
        "failed_count": state["failed_count"],
        "job_health_reports": state["job_health_reports"],
        "model_health_reports": state.get("model_health_reports", []),
    })
    
    state["emails_sent"].append("initial_health_check")
    state["current_stage"] = "initial_email_sent"
    
    return state


async def failure_alert_node(state: AEGISState) -> AEGISState:
    """Send failure alert email and run RCA."""
    logger.info("[Workflow] Stage: failure_alert")
    
    # Pick first failed job
    failed_jobs = [r for r in state["job_health_reports"] if r["status"] == "failed"]
    if not failed_jobs:
        logger.warning("[Workflow] No failed jobs found in failure_alert stage")
        state["current_stage"] = "no_failures"
        return state
    
    failed_job = failed_jobs[0]
    state["current_job_id"] = failed_job["job_id"]
    state["current_job_name"] = failed_job["job_name"]
    state["current_error_summary"] = failed_job["error_summary"]
    
    # Generate incident ID (use variable to avoid Python <3.12 nested f-string issue)
    import hashlib
    _hash_input = f"{failed_job['job_id']}{failed_job['last_run_id']}"
    state["current_incident_id"] = f"INC-{hashlib.md5(_hash_input.encode()).hexdigest()[:8].upper()}"
    
    # Run RCA
    rca_agent = RCAAgent(state["config"]["rca"])
    from src.models import DetectedIncident, FailureType
    from datetime import datetime
    incident = DetectedIncident(
        incident_id=state["current_incident_id"],
        job_name=state["current_job_name"],
        failure_type=FailureType.TRANSIENT_FAILURE,
        error_summary=state["current_error_summary"],
        error_logs=state["current_error_summary"],  # Use error_summary as logs
        timestamp=datetime.utcnow(),
    )
    
    from src.diagnosis.context_assembler import ContextAssembler
    from src.knowledge.incident_store import IncidentKnowledgeStore
    _ks = IncidentKnowledgeStore(state["config"].get("knowledge_store", {"persist_dir": "./data/knowledge_store"}))
    assembler = ContextAssembler(
        knowledge_store=_ks,
        workspace_host=state["workspace_host"],
        workspace_token=state["workspace_token"],
    )
    context = await assembler.assemble(incident)
    rca = await rca_agent.diagnose(context)
    
    state["root_cause"] = rca.root_cause
    state["confidence"] = rca.confidence
    state["risk_level"] = rca.risk_level.value

    # ─── GUARDRAIL #1: Confidence Gate ──────────────────────────────────
    # If confidence < threshold, escalate to human instead of auto-fixing
    if rca.confidence < RCA_CONFIDENCE_THRESHOLD:
        logger.warning(
            f"[Workflow] ❌ GUARDRAIL: RCA confidence {rca.confidence:.0f}% < {RCA_CONFIDENCE_THRESHOLD}% threshold. "
            f"Escalating to human instead of autonomous fix."
        )
        AuditLog.record(
            "CONFIDENCE_GATE_BLOCKED",
            incident_id=state["current_incident_id"],
            job_id=state["current_job_id"],
            confidence=rca.confidence,
            threshold=RCA_CONFIDENCE_THRESHOLD,
            root_cause=rca.root_cause,
        )
        # Send escalation email immediately so human is notified with proper context
        _mail = MailSenderAgent()
        await _mail.send_stage("escalation", {
            "incident_id": state["current_incident_id"],
            "job_name": state["current_job_name"],
            "confidence": rca.confidence,
            "root_cause": rca.root_cause,
            "threshold": RCA_CONFIDENCE_THRESHOLD,
        })
        state["fix_status"] = "escalated"
        state["current_stage"] = "escalated_low_confidence"
    else:
        logger.success(
            f"[Workflow] ✅ GUARDRAIL: RCA confidence {rca.confidence:.0f}% ≥ {RCA_CONFIDENCE_THRESHOLD}% — proceeding with autonomous fix"
        )
        AuditLog.record(
            "CONFIDENCE_GATE_PASSED",
            incident_id=state["current_incident_id"],
            job_id=state["current_job_id"],
            confidence=rca.confidence,
            root_cause=rca.root_cause,
        )

    # Send failure alert email
    mail_agent = MailSenderAgent()
    await mail_agent.send_stage("failure_alert", {
        "incident_id": state["current_incident_id"],
        "job_name": state["current_job_name"],
        "error_summary": state["current_error_summary"],
        "root_cause": state["root_cause"],
        "confidence": state["confidence"],
    })
    
    state["emails_sent"].append("failure_alert")
    state["current_stage"] = "failure_alert_sent"
    
    return state


async def fix_in_progress_email_node(state: AEGISState) -> AEGISState:
    """Send fix-in-progress email."""
    logger.info("[Workflow] Stage: fix_in_progress_email")
    
    agent = MailSenderAgent()
    await agent.send_stage("fix_in_progress", {
        "incident_id": state["current_incident_id"],
        "job_name": state["current_job_name"],
        "notebooks_to_fix": ["(discovering from job tasks...)"],
    })
    
    state["emails_sent"].append("fix_in_progress")
    state["current_stage"] = "fix_in_progress_email_sent"
    
    return state


async def job_fixer_node(state: AEGISState) -> AEGISState:
    """Fix the failed job with LLM."""
    logger.info("[Workflow] Stage: job_fixer")
    
    from datetime import datetime
    start_time = datetime.utcnow()
    
    agent = JobFixerAgent(state["workspace_host"], state["workspace_token"], state["config"])
    result = await agent.fix_job(
        job_id=int(state["current_job_id"]),
        error_summary=state["current_error_summary"],
        incident_id=state["current_incident_id"],
    )
    
    end_time = datetime.utcnow()
    state["mttr_seconds"] = (end_time - start_time).total_seconds()
    
    state["fix_status"] = result["status"]
    state["fixed_notebooks"] = result["fixed_notebooks"]
    state["post_fix_run_id"] = result["post_fix_run_id"]
    state["current_stage"] = "job_fixed"
    
    return state


async def fix_complete_email_node(state: AEGISState) -> AEGISState:
    """Send fix-complete email."""
    logger.info("[Workflow] Stage: fix_complete_email")
    
    agent = MailSenderAgent()
    await agent.send_stage("fix_complete", {
        "incident_id": state["current_incident_id"],
        "job_name": state["current_job_name"],
        "post_fix_run_id": state["post_fix_run_id"],
        "mttr_seconds": state["mttr_seconds"],
    })
    
    state["emails_sent"].append("fix_complete")
    state["current_stage"] = "fix_complete_email_sent"
    
    return state


async def pr_create_node(state: AEGISState) -> AEGISState:
    """Create GitHub PR with the fix."""
    logger.info("[Workflow] Stage: pr_create")
    
    agent = PRManagerAgent()
    result = await agent.create_pr(
        incident_id=state["current_incident_id"],
        fixed_notebooks=state["fixed_notebooks"],
        root_cause=state["root_cause"],
        failure_type="code_bug",
    )
    
    state["pr_url"] = result["pr_url"]
    state["pr_number"] = result["pr_number"]
    state["pr_merged"] = False
    state["current_stage"] = "pr_created"
    
    return state


async def pr_raised_email_node(state: AEGISState) -> AEGISState:
    """Send PR-raised email."""
    logger.info("[Workflow] Stage: pr_raised_email")
    
    agent = MailSenderAgent()
    await agent.send_stage("pr_raised", {
        "incident_id": state["current_incident_id"],
        "pr_url": state["pr_url"],
        "pr_number": state["pr_number"],
    })
    
    state["emails_sent"].append("pr_raised")
    state["current_stage"] = "pr_raised_email_sent"
    
    return state


async def pr_wait_approval_node(state: AEGISState) -> AEGISState:
    """Wait for PR approval and merge."""
    logger.info("[Workflow] Stage: pr_wait_approval")
    
    agent = PRManagerAgent()
    result = await agent.wait_for_pr_approval(state["pr_number"])
    
    state["pr_merged"] = result["merged"]
    state["merge_sha"] = result["sha"]
    state["current_stage"] = "pr_approval_checked"
    
    return state


async def deployment_node(state: AEGISState) -> AEGISState:
    """Trigger CD workflow and monitor."""
    logger.info("[Workflow] Stage: deployment")
    
    agent = DeploymentAgent()
    result = await agent.trigger_cd(state["merge_sha"])
    
    state["workflow_run_url"] = result["workflow_run_url"]
    state["deployment_status"] = result["status"]
    state["current_stage"] = "deployment"
    
    return state


async def post_deployment_verification_node(state: AEGISState) -> AEGISState:
    """
    Re-run health check after deployment to verify the fix worked.
    Wait a bit for Databricks to reflect the new deployment.
    """
    logger.info("[Workflow] Stage: post_deployment_verification")
    logger.info("[Workflow] Waiting 60s for Databricks to sync deployed notebooks...")
    
    import asyncio
    await asyncio.sleep(60)
    
    # Re-run status check on the same job
    checker = StatusCheckerAgent(
        host=state["workspace_host"],
        token=state["workspace_token"]
    )
    
    reports = await checker.check_health(
        monitor_all_jobs=False,
        specific_job_id=str(state["current_job_id"]),
    )
    
    # Check if the job is now healthy
    job_now_healthy = False
    for report in reports:
        if report["status"] == "healthy":
            job_now_healthy = True
            break
    
    state["post_deployment_healthy"] = job_now_healthy
    state["current_stage"] = "post_deployment_verification"
    
    if job_now_healthy:
        logger.success(f"[Workflow] ✅ Job {state['current_job_id']} is now HEALTHY after deployment!")
    else:
        logger.warning(f"[Workflow] ⚠️ Job {state['current_job_id']} still FAILED after deployment")
    
    return state


async def final_confirmation_email_node(state: AEGISState) -> AEGISState:
    """Send final confirmation email that entire cycle completed successfully."""
    logger.info("[Workflow] Stage: final_confirmation_email")

    agent = MailSenderAgent()
    await agent.send_stage("final_confirmation", {
        "incident_id": state["current_incident_id"],
        "job_id": state["current_job_id"],
        "job_name": state["current_job_name"],
        "pr_url": state["pr_url"],
        "workflow_run_url": state["workflow_run_url"],
        "post_deployment_healthy": state.get("post_deployment_healthy", False),
        "mttr_seconds": state["mttr_seconds"],
    })

    state["emails_sent"].append("final_confirmation")
    state["current_stage"] = "final_confirmation_sent"

    return state


async def incident_report_node(state: AEGISState) -> AEGISState:
    """Generate and save the structured incident report (runs at end of every cycle)."""
    logger.info("[Workflow] Stage: incident_report")
    try:
        report = generate_incident_report(dict(state))
        state["incident_report"] = report
        state["current_stage"] = "incident_report_generated"
    except Exception as e:
        logger.warning(f"[Workflow] Incident report generation failed (non-fatal): {e}")
        state["incident_report"] = None
    return state


async def deployment_failed_email_node(state: AEGISState) -> AEGISState:
    """Send email when post-deployment verification shows job still failing."""
    logger.info("[Workflow] Stage: deployment_failed_email")

    agent = MailSenderAgent()
    await agent.send_stage("deployment_failed", {
        "incident_id": state["current_incident_id"],
        "job_id": state["current_job_id"],
        "job_name": state["current_job_name"],
        "pr_url": state["pr_url"],
        "workflow_run_url": state["workflow_run_url"],
    })

    state["emails_sent"].append("deployment_failed")
    state["current_stage"] = "deployment_failed_email_sent"

    return state


async def ml_healer_node(state: AEGISState) -> AEGISState:
    """Autonomous ML model retraining and promotion for degraded models."""
    logger.info("[Workflow] Stage: ml_healer")

    from src.agents.ml_healer import MLHealerAgent

    degraded = [r for r in state.get("model_health_reports", []) if r.get("status") != "healthy"]
    state["ml_degraded_models"] = degraded

    if not degraded:
        logger.info("[Workflow] No degraded models — ML healing skipped")
        state["current_stage"] = "ml_no_drift"
        return state

    logger.warning(f"[Workflow] {len(degraded)} degraded model(s) — starting ML healing")
    healer = MLHealerAgent(state["config"])
    result = await healer.heal(degraded)

    state["ml_heal_result"] = result
    state["current_stage"] = "ml_healing_complete"
    logger.info(f"[Workflow] ML healing done | status={result.get('status')} | healed={result.get('healed')}")
    return state


# ─── Conditional Edge Functions ─────────────────────────────────────────────


def route_after_rca(state: AEGISState) -> Literal["fix_flow", "escalate_confidence"]:
    """GUARDRAIL #1: Route based on RCA confidence and escalation flag."""
    if state.get("fix_status") == "escalated":
        return "escalate_confidence"
    return "fix_flow"


def route_after_initial_email(state: AEGISState) -> Literal["fix_flow", "ml_heal", "end"]:
    """Route based on job failures or ML model drift."""
    if state["has_failures"]:
        return "fix_flow"
    degraded = [r for r in state.get("model_health_reports", []) if r.get("status") != "healthy"]
    if degraded:
        return "ml_heal"
    return "end"


def route_after_fix(state: AEGISState) -> Literal["pr_flow", "escalate"]:
    """Route based on fix success."""
    if state["fix_status"] == "success":
        return "pr_flow"
    return "escalate"


def route_after_pr_wait(state: AEGISState) -> Literal["deployment", "escalate"]:
    """Route based on PR merge status."""
    if state["pr_merged"]:
        return "deployment"
    return "escalate"


def route_after_post_deployment(state: AEGISState) -> Literal["success", "failed"]:
    """Route based on post-deployment health check."""
    if state.get("post_deployment_healthy", False):
        return "success"
    return "failed"


# ─── Build Workflow ──────────────────────────────────────────────────────────


def build_aegis_workflow() -> StateGraph:
    """
    Build the LangGraph workflow.
    
    Enhanced Flow (15 nodes):
    START → job_selector (interactive job selection)
    → status_check → initial_email → [if failures]:
    → failure_alert → fix_in_progress_email → job_fixer → fix_complete_email
    → pr_create → pr_raised_email → pr_wait_approval (INDEFINITE WAIT)
    → deployment → post_deployment_verification
    → [if healthy] → final_confirmation_email → END
    → [if still failing] → deployment_failed_email → END
    """
    workflow = StateGraph(AEGISState)
    
    # Add nodes
    workflow.add_node("job_selector", job_selector_node)
    workflow.add_node("status_check", status_check_node)
    workflow.add_node("initial_email", initial_email_node)
    workflow.add_node("ml_healer", ml_healer_node)
    workflow.add_node("failure_alert", failure_alert_node)
    workflow.add_node("fix_in_progress_email", fix_in_progress_email_node)
    workflow.add_node("job_fixer", job_fixer_node)
    workflow.add_node("fix_complete_email", fix_complete_email_node)
    workflow.add_node("pr_create", pr_create_node)
    workflow.add_node("pr_raised_email", pr_raised_email_node)
    workflow.add_node("pr_wait_approval", pr_wait_approval_node)
    workflow.add_node("deployment", deployment_node)
    workflow.add_node("post_deployment_verification", post_deployment_verification_node)
    workflow.add_node("final_confirmation_email", final_confirmation_email_node)
    workflow.add_node("deployment_failed_email", deployment_failed_email_node)
    workflow.add_node("incident_report", incident_report_node)
    
    # Set entry point - start with interactive job selection
    workflow.set_entry_point("job_selector")
    
    # Add edges
    workflow.add_edge("job_selector", "status_check")
    workflow.add_edge("status_check", "initial_email")
    
    workflow.add_conditional_edges(
        "initial_email",
        route_after_initial_email,
        {
            "fix_flow": "failure_alert",
            "ml_heal": "ml_healer",
            "end": END,
        },
    )
    workflow.add_edge("ml_healer", "incident_report")

    # GUARDRAIL #1: confidence gate — failure_alert sets fix_status="escalated" when low confidence
    workflow.add_conditional_edges(
        "failure_alert",
        route_after_rca,
        {
            "fix_flow": "fix_in_progress_email",
            "escalate_confidence": "incident_report",  # email already sent inline in failure_alert_node
        },
    )
    workflow.add_edge("fix_in_progress_email", "job_fixer")
    
    workflow.add_conditional_edges(
        "job_fixer",
        route_after_fix,
        {
            "pr_flow": "fix_complete_email",
            "escalate": END,  # Fix failed, escalate to human
        },
    )
    
    workflow.add_edge("fix_complete_email", "pr_create")
    workflow.add_edge("pr_create", "pr_raised_email")
    workflow.add_edge("pr_raised_email", "pr_wait_approval")
    
    workflow.add_conditional_edges(
        "pr_wait_approval",
        route_after_pr_wait,
        {
            "deployment": "deployment",
            "escalate": END,  # PR rejected or closed
        },
    )
    
    workflow.add_edge("deployment", "post_deployment_verification")
    
    workflow.add_conditional_edges(
        "post_deployment_verification",
        route_after_post_deployment,
        {
            "success": "final_confirmation_email",
            "failed": "deployment_failed_email",
        },
    )
    
    workflow.add_edge("final_confirmation_email", "incident_report")
    workflow.add_edge("deployment_failed_email", "incident_report")
    workflow.add_edge("incident_report", END)
    
    return workflow.compile()
