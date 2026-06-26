"""
AEGIS Production Run (Multi-Agent LangGraph)
Full autonomous reliability lifecycle with email notifications at each stage.

Usage:
    python demo/production_multi_agent.py

Environment Variables:
    DATABRICKS_HOST, DATABRICKS_TOKEN    — Databricks workspace
    DATABRICKS_JOB_ID                    — (optional) specific job to monitor
    DAB_BUNDLE_NAME                      — (optional) filter jobs by bundle name
    DIAL_API_KEY, DIAL_API_ENDPOINT      — GPT-4o for RCA and notebook repair
    GITHUB_TOKEN, GITHUB_REPO_OWNER, GITHUB_REPO_NAME  — PR creation
    GMAIL_SENDER, GMAIL_APP_PASSWORD, GMAIL_RECIPIENTS — Email notifications
"""
import os
import asyncio
import yaml
from dotenv import load_dotenv
from loguru import logger
from rich.console import Console
from rich.panel import Panel

from src.workflow import build_aegis_workflow

load_dotenv()
console = Console()


def load_config(path: str = "config/config.yaml") -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


async def main():
    console.print(Panel(
        "[bold cyan]🛡️  AEGIS MULTI-AGENT PRODUCTION RUN[/bold cyan]\n"
        "LangGraph-powered autonomous reliability with 6-stage email notifications",
        border_style="cyan"
    ))
    
    # Load configuration
    config = load_config()
    
    # Determine monitoring mode
    specific_job_id = os.environ.get("DATABRICKS_JOB_ID")
    monitor_all_jobs = not specific_job_id  # If no specific job, monitor all
    dab_bundle_name = os.environ.get("DAB_BUNDLE_NAME", "aegis-de-project")
    
    if specific_job_id:
        logger.info(f"Monitoring mode: SINGLE JOB (job_id={specific_job_id})")
    elif dab_bundle_name:
        logger.info(f"Monitoring mode: DAB BUNDLE (bundle={dab_bundle_name})")
    else:
        logger.info("Monitoring mode: ALL JOBS IN WORKSPACE")
    
    # Build workflow
    workflow = build_aegis_workflow()
    
    # Initial state
    initial_state = {
        "workspace_host": os.environ["DATABRICKS_HOST"],
        "workspace_token": os.environ["DATABRICKS_TOKEN"],
        "monitor_all_jobs": monitor_all_jobs,
        "specific_job_id": specific_job_id,
        "dab_bundle_name": dab_bundle_name if monitor_all_jobs else None,
        "config": config,
        
        # Initialize empty fields
        "job_health_reports": [],
        "has_failures": False,
        "healthy_count": 0,
        "failed_count": 0,
        "current_incident_id": None,
        "current_job_id": None,
        "current_job_name": None,
        "current_error_summary": None,
        "root_cause": None,
        "confidence": 0.0,
        "risk_level": "unknown",
        "fix_status": None,
        "fixed_notebooks": [],
        "post_fix_run_id": None,
        "mttr_seconds": 0.0,
        "pr_url": None,
        "pr_number": 0,
        "pr_merged": False,
        "merge_sha": None,
        "workflow_run_url": None,
        "deployment_status": None,
        "post_deployment_healthy": False,
        "emails_sent": [],
        "available_jobs": [],
        "user_selected_job_id": None,
        "model_health_reports": [],
        "incident_report": None,
        "current_stage": "init",
    }
    
    # Run workflow
    logger.info("Starting LangGraph multi-agent workflow...")
    final_state = await workflow.ainvoke(initial_state)
    
    # Display summary
    console.print("\n" + "="*60)
    console.print("[bold]AEGIS MULTI-AGENT RUN COMPLETE[/bold]")
    console.print("="*60)
    console.print(f"Final Stage: {final_state['current_stage']}")
    console.print(f"Healthy Jobs: {final_state['healthy_count']}")
    console.print(f"Failed Jobs: {final_state['failed_count']}")

    # Model health summary
    model_reports = final_state.get("model_health_reports", [])
    if model_reports:
        degraded = [r for r in model_reports if r.get("status") != "healthy"]
        if degraded:
            console.print(f"[bold yellow]⚠️  Model Drift: {len(degraded)} model(s) degraded[/bold yellow]")
            for r in degraded:
                console.print(f"   • {r['model_name']}: {r.get('alert', 'degraded')}")
        else:
            console.print(f"[green]✅ ML Models: all {len(model_reports)} healthy[/green]")

    if final_state.get("current_incident_id"):
        console.print(f"Incident: {final_state['current_incident_id']}")
        console.print(f"Fix Status: {final_state['fix_status']}")
        console.print(f"MTTR: {final_state['mttr_seconds']:.0f}s")
        if final_state.get("pr_url"):
            console.print(f"PR: {final_state['pr_url']}")
        if final_state.get("workflow_run_url"):
            console.print(f"Deployment: {final_state['workflow_run_url']}")
    console.print(f"Emails Sent: {', '.join(final_state['emails_sent'])}")

    # Incident report path
    if final_state.get("incident_report"):
        report_id = final_state["incident_report"].get("report_id", "")
        console.print(f"[bold cyan]📋 Incident Report: data/reports/{report_id}.json[/bold cyan]")

    console.print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
