"""
Debug script to check what error details Databricks API returns
"""
import os
from dotenv import load_dotenv
from databricks.sdk import WorkspaceClient

load_dotenv()

client = WorkspaceClient(
    host=os.environ["DATABRICKS_HOST"],
    token=os.environ["DATABRICKS_TOKEN"]
)

job_id = 470575380114552

print("=" * 80)
print("CHECKING DATABRICKS JOB ERROR DETAILS")
print("=" * 80)

# Get latest run
runs = list(client.jobs.list_runs(job_id=job_id, limit=1))
if not runs:
    print("No runs found!")
    exit(1)

run_light = runs[0]
print(f"\n=== LIGHTWEIGHT RUN (from list_runs) ===")
print(f"Run ID: {run_light.run_id}")
print(f"State: {run_light.state.life_cycle_state}/{run_light.state.result_state}")
print(f"Tasks: {len(run_light.tasks or [])}")

# Get full run details
run = client.jobs.get_run(run_id=run_light.run_id)
print(f"\n=== FULL RUN (from get_run) ===")
print(f"Run ID: {run.run_id}")
print(f"State: {run.state.life_cycle_state}/{run.state.result_state}")
print(f"State Message: {run.state.state_message}")
print(f"\nTasks: {len(run.tasks or [])}")

for i, task in enumerate(run.tasks or [], 1):
    print(f"\n{'=' * 80}")
    print(f"TASK {i}: {task.task_key}")
    print(f"{'=' * 80}")
    print(f"Task Run ID: {task.run_id}")
    print(f"State: {task.state.life_cycle_state if task.state else 'N/A'}/{task.state.result_state if task.state else 'N/A'}")
    print(f"State Message: {task.state.state_message if task.state else 'N/A'}")
    
    # Try to get run output
    try:
        output = client.jobs.get_run_output(run_id=task.run_id)
        print(f"\n--- RUN OUTPUT ---")
        print(f"Error: {output.error}")
        print(f"Error Trace Length: {len(output.error_trace) if output.error_trace else 0}")
        if output.error_trace:
            print(f"\n--- ERROR TRACE ---")
            print(output.error_trace)
    except Exception as e:
        print(f"\n[ERROR] Failed to get run output: {e}")
