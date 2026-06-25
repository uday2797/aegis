"""AEGIS Production Run — polls real Databricks, no injection."""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml
from dotenv import load_dotenv
load_dotenv()

from src.main import AEGISOrchestrator


async def run():
    config = yaml.safe_load(open("config/config.yaml"))
    orchestrator = AEGISOrchestrator(config)

    print()
    print("=== AEGIS PRODUCTION RUN — polling real Databricks job 367630218921042 ===")
    print()

    report = await orchestrator.run_once()

    if report:
        healed = "AUTO-HEALED ✅" if report.auto_healed else "ESCALATED ⚠️"
        print()
        print("=" * 60)
        print(f"  Job Name  : {report.job_name}")
        print(f"  Incident  : {report.incident_id}")
        print(f"  Status    : {healed}")
        print(f"  MTTR      : {report.mttr_seconds:.0f}s")
        print(f"  Root Cause: {report.root_cause}")
        print(f"  Action    : {report.action_taken}")
        print(f"  Outcome   : {report.outcome}")
        if report.pr_url and report.pr_url != "none":
            print(f"  GitHub PR : {report.pr_url}")
        print("=" * 60)
    else:
        print("No failure detected in Databricks — job is currently healthy or already resolved.")


if __name__ == "__main__":
    asyncio.run(run())
