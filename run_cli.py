"""
AEGIS CLI Runner
Run AEGIS workflow from VS Code terminal with interactive job selection.
"""
import os
import sys
import asyncio
from dotenv import load_dotenv
from databricks.sdk import WorkspaceClient
from loguru import logger
from tabulate import tabulate

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.workflow import build_aegis_workflow, AEGISState

load_dotenv()


def fetch_available_jobs():
    """Fetch all Databricks jobs"""
    client = WorkspaceClient(
        host=os.getenv("DATABRICKS_HOST"),
        token=os.getenv("DATABRICKS_TOKEN")
    )
    
    jobs = []
    for job in client.jobs.list():
        runs = list(client.jobs.list_runs(job_id=job.job_id, limit=1))
        latest_status = runs[0].state.life_cycle_state.value if runs else "UNKNOWN"
        result_state = runs[0].state.result_state.value if runs and runs[0].state.result_state else "UNKNOWN"
        
        jobs.append({
            "job_id": job.job_id,
            "name": job.settings.name,
            "status": latest_status,
            "result_state": result_state,
            "tasks": len(job.settings.tasks) if job.settings.tasks else 0
        })
    
    return jobs


def select_jobs_interactive(jobs):
    """Display jobs and let user select which ones to monitor"""
    logger.info("🔍 Available Databricks Jobs:")
    
    # Display table
    table_data = []
    for i, job in enumerate(jobs, 1):
        status_emoji = "✅" if job["result_state"] == "SUCCESS" else "❌"
        table_data.append([
            i,
            job["job_id"],
            job["name"][:60],
            f"{status_emoji} {job['result_state']}",
            job["tasks"]
        ])
    
    print(tabulate(
        table_data,
        headers=["#", "Job ID", "Name", "Status", "Tasks"],
        tablefmt="rounded_grid"
    ))
    
    print("\n📋 Selection Options:")
    print("  • Enter job numbers (comma-separated): 1,3,5")
    print("  • Enter 'all' to monitor all jobs")
    print("  • Press Enter to monitor only failed jobs")
    
    selection = input("\n👉 Your selection: ").strip()
    
    if selection.lower() == "all":
        return jobs
    elif selection == "":
        failed_jobs = [j for j in jobs if j["result_state"] in ["FAILED", "TIMEDOUT", "CANCELED"]]
        if not failed_jobs:
            logger.warning("No failed jobs found. Monitoring all jobs.")
            return jobs
        logger.info(f"Monitoring {len(failed_jobs)} failed job(s)")
        return failed_jobs
    else:
        try:
            indices = [int(x.strip()) for x in selection.split(",")]
            selected = [jobs[i-1] for i in indices if 0 < i <= len(jobs)]
            logger.info(f"Selected {len(selected)} job(s)")
            return selected
        except (ValueError, IndexError) as e:
            logger.error(f"Invalid selection: {e}")
            logger.info("Defaulting to all jobs")
            return jobs


def run_aegis_workflow(selected_jobs):
    """Execute AEGIS workflow for selected jobs"""
    logger.info("🚀 Starting AEGIS workflow...")
    
    # Determine monitoring mode
    if len(selected_jobs) == 1:
        specific_job_id = selected_jobs[0]["job_id"]
        monitor_all = False
        logger.info(f"Monitoring single job: {specific_job_id}")
    else:
        specific_job_id = None
        monitor_all = True
        logger.info(f"Monitoring {len(selected_jobs)} jobs")
    
    # Build initial state
    initial_state: AEGISState = {
        "workspace_host": os.getenv("DATABRICKS_HOST"),
        "workspace_token": os.getenv("DATABRICKS_TOKEN"),
        "monitor_all_jobs": monitor_all,
        "specific_job_id": specific_job_id,
        "detected_incident": None,
        "failure_context": None,
        "rca_report": None,
        "fix_applied": False,
        "fixed_notebooks": [],
        "pr_url": None,
        "pr_number": None,
        "pr_merged": False,
        "deployment_successful": False,
        "deployment_url": None,
        "post_deploy_healthy": False,
        "final_status": None,
        "emails_sent": [],
        "available_jobs": selected_jobs,
        "user_selected_job_id": ",".join(str(j["job_id"]) for j in selected_jobs),
    }
    
    # Build and run workflow
    workflow = build_aegis_workflow()
    
    logger.info("⚙️ Executing workflow graph...")
    # Use async API since workflow nodes are async
    final_state = asyncio.run(workflow.ainvoke(initial_state))
    
    # Display results
    print("\n" + "="*80)
    logger.success("✅ AEGIS Workflow Completed!")
    print("="*80)
    
    print(f"\n📊 Final Status: {final_state.get('final_status', 'UNKNOWN')}")
    
    if final_state.get("detected_incident"):
        incident = final_state["detected_incident"]
        print(f"\n🚨 Incident Details:")
        print(f"   Job: {incident.job_name}")
        print(f"   Type: {incident.failure_type}")
        print(f"   Summary: {incident.error_summary[:200]}")
    
    if final_state.get("rca_report"):
        rca = final_state["rca_report"]
        print(f"\n🔬 Root Cause Analysis:")
        print(f"   Confidence: {rca.confidence * 100:.0f}%")
        print(f"   Root Cause: {rca.root_cause[:200]}")
    
    if final_state.get("pr_url"):
        print(f"\n🔀 Pull Request: {final_state['pr_url']}")
        print(f"   Merged: {'✅ Yes' if final_state.get('pr_merged') else '❌ No'}")
    
    if final_state.get("deployment_url"):
        print(f"\n🚀 Deployment: {final_state['deployment_url']}")
        print(f"   Status: {'✅ Success' if final_state.get('deployment_successful') else '❌ Failed'}")
    
    print(f"\n📧 Emails Sent: {len(final_state.get('emails_sent', []))}")
    for email_stage in final_state.get('emails_sent', []):
        print(f"   • {email_stage}")
    
    print("\n" + "="*80)
    
    return final_state


def main():
    logger.info("🛡️ AEGIS - Autonomous Error & Gap Intelligence System")
    logger.info("Running from VS Code CLI\n")
    
    # Fetch jobs
    logger.info("Fetching Databricks jobs...")
    jobs = fetch_available_jobs()
    
    if not jobs:
        logger.error("❌ No jobs found in workspace")
        return
    
    logger.success(f"Found {len(jobs)} job(s)\n")
    
    # Interactive selection
    selected_jobs = select_jobs_interactive(jobs)
    
    if not selected_jobs:
        logger.error("❌ No jobs selected")
        return
    
    # Confirmation
    print(f"\n✅ You selected {len(selected_jobs)} job(s):")
    for job in selected_jobs:
        print(f"   • {job['job_id']} - {job['name'][:60]}")
    
    confirm = input("\n🚀 Start AEGIS workflow? [Y/n]: ").strip().lower()
    if confirm and confirm != 'y':
        logger.info("Cancelled by user")
        return
    
    # Run workflow
    final_state = run_aegis_workflow(selected_jobs)
    
    logger.success("\n✅ AEGIS workflow complete!")


if __name__ == "__main__":
    main()
