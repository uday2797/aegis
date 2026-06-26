"""
AEGIS LangGraph Multi-Agent Workflow
Orchestrates the full autonomous reliability lifecycle.

Workflow Stages:
1. Status Check → Email (healthy or failed)
2. If failed → RCA → Fix → Verify
3. Create PR → Email (PR raised)
4. Wait for PR approval
5. Trigger CD → Email (deployment complete)
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
from src.diagnosis.rca_agent import RCAAgent


# ─── State Definition ────────────────────────────────────────────────────────


class AEGISState(TypedDict):
    """Global state shared across all agents."""
    
    # Configuration
    workspace_host: str
    workspace_token: str
    monitor_all_jobs: bool
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
    
    # Email tracking
    emails_sent: list[str]
    
    # Loop control
    current_stage: str


# ─── Agent Node Functions ────────────────────────────────────────────────────


async def status_check_node(state: AEGISState) -> AEGISState:
    """Check health of all monitored jobs."""
    logger.info("[Workflow] Stage: status_check")
    
    agent = StatusCheckerAgent(state["workspace_host"], state["workspace_token"])
    reports = await agent.check_health(
        monitor_all_jobs=state["monitor_all_jobs"],
        specific_job_id=state["specific_job_id"],
        dab_bundle_name=state["dab_bundle_name"],
    )
    
    state["job_health_reports"] = reports
    state["healthy_count"] = sum(1 for r in reports if r["status"] == "healthy")
    state["failed_count"] = sum(1 for r in reports if r["status"] == "failed")
    state["has_failures"] = state["failed_count"] > 0
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
    
    # Generate incident ID
    import hashlib
    state["current_incident_id"] = f"INC-{hashlib.md5(f'{failed_job['job_id']}{failed_job['last_run_id']}'.encode()).hexdigest()[:8].upper()}"
    
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
    assembler = ContextAssembler(knowledge_store=None)
    context = await assembler.assemble(incident)
    rca = await rca_agent.diagnose(context)
    
    state["root_cause"] = rca.root_cause
    state["confidence"] = rca.confidence
    state["risk_level"] = rca.risk_level.value
    
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
    
    agent = JobFixerAgent(state["workspace_host"], state["workspace_token"], state["config"]["healing"])
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
    result = await agent.wait_for_pr_approval(state["pr_number"], timeout_minutes=60)
    
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
    state["current_stage"] = "deployment_complete"
    
    return state


async def deployment_complete_email_node(state: AEGISState) -> AEGISState:
    """Send deployment-complete email."""
    logger.info("[Workflow] Stage: deployment_complete_email")
    
    agent = MailSenderAgent()
    await agent.send_stage("deployment_complete", {
        "incident_id": state["current_incident_id"],
        "workflow_run_url": state["workflow_run_url"],
        "healthy_count": state["healthy_count"] + 1,  # All fixed now
    })
    
    state["emails_sent"].append("deployment_complete")
    state["current_stage"] = "deployment_complete_email_sent"
    
    return state


# ─── Conditional Edge Functions ─────────────────────────────────────────────


def route_after_initial_email(state: AEGISState) -> Literal["fix_flow", "end"]:
    """Route based on whether failures exist."""
    if state["has_failures"]:
        return "fix_flow"
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


# ─── Build Workflow ──────────────────────────────────────────────────────────


def build_aegis_workflow() -> StateGraph:
    """
    Build the LangGraph workflow.
    
    Flow:
    START → status_check → initial_email → [if failures] → failure_alert → fix_in_progress_email
    → job_fixer → fix_complete_email → pr_create → pr_raised_email → pr_wait_approval
    → deployment → deployment_complete_email → END
    """
    workflow = StateGraph(AEGISState)
    
    # Add nodes
    workflow.add_node("status_check", status_check_node)
    workflow.add_node("initial_email", initial_email_node)
    workflow.add_node("failure_alert", failure_alert_node)
    workflow.add_node("fix_in_progress_email", fix_in_progress_email_node)
    workflow.add_node("job_fixer", job_fixer_node)
    workflow.add_node("fix_complete_email", fix_complete_email_node)
    workflow.add_node("pr_create", pr_create_node)
    workflow.add_node("pr_raised_email", pr_raised_email_node)
    workflow.add_node("pr_wait_approval", pr_wait_approval_node)
    workflow.add_node("deployment", deployment_node)
    workflow.add_node("deployment_complete_email", deployment_complete_email_node)
    
    # Set entry point
    workflow.set_entry_point("status_check")
    
    # Add edges
    workflow.add_edge("status_check", "initial_email")
    
    workflow.add_conditional_edges(
        "initial_email",
        route_after_initial_email,
        {
            "fix_flow": "failure_alert",
            "end": END,
        },
    )
    
    workflow.add_edge("failure_alert", "fix_in_progress_email")
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
            "escalate": END,  # PR rejected or timeout
        },
    )
    
    workflow.add_edge("deployment", "deployment_complete_email")
    workflow.add_edge("deployment_complete_email", END)
    
    return workflow.compile()
