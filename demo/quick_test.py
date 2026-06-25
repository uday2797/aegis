"""
AEGIS Quick Test — runs all 5 failure types without interactive pauses.
Use this to validate the full system works before the live demo.
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml
from dotenv import load_dotenv
from loguru import logger
from src.main import AEGISOrchestrator

load_dotenv()


ALL_FAILURE_TYPES = [
    {"type": "schema_drift"},
    {"type": "data_corruption", "null_pct": 34.2},
    {"type": "transient_failure"},
    {"type": "model_drift", "psi_score": 0.31},
    {"type": "upstream_delay"},
]


async def run_all_tests():
    logger.info("AEGIS Quick Test — validating all failure types")
    config = yaml.safe_load(open("config/config.yaml"))
    orchestrator = AEGISOrchestrator(config)
    passed = 0

    for i, failure in enumerate(ALL_FAILURE_TYPES, 1):
        logger.info(f"Test {i}/{len(ALL_FAILURE_TYPES)}: {failure['type']}")
        orchestrator.inject_failure(failure)
        try:
            report = await orchestrator.run_once()
            if report:
                logger.success(f"  PASS | MTTR={report.mttr_seconds:.0f}s | auto_healed={report.auto_healed}")
                passed += 1
            else:
                logger.warning("  SKIP | No incident returned")
        except Exception as e:
            logger.error(f"  FAIL | {e}")

    logger.info(f"\nResults: {passed}/{len(ALL_FAILURE_TYPES)} tests passed")


if __name__ == "__main__":
    asyncio.run(run_all_tests())
