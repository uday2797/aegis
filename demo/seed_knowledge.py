"""
AEGIS Knowledge Store Seeder
Pre-populates ChromaDB with 10 realistic historical incidents so that
similarity-based RCA enrichment works from the very first demo run.

Run once before demo:
    python demo/seed_knowledge.py
"""
import asyncio
import sys
import os
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml
from dotenv import load_dotenv
from loguru import logger
from src.models import DetectedIncident, RCAResult, HealResult, FailureType, RiskLevel, HealStatus

load_dotenv()

SEED_INCIDENTS = [
    {
        "incident": DetectedIncident(
            incident_id="INC-SEED-001",
            job_name="nexus_exp_daily_pipeline",
            failure_type=FailureType.SCHEMA_DRIFT,
            error_summary="Schema column 'txn_amount' renamed to 'transaction_amount' in upstream source",
            error_logs="[ERROR] AnalysisException: cannot resolve 'txn_amount' given input columns: [transaction_amount]",
            timestamp=datetime.now(timezone.utc) - timedelta(days=14),
            upstream_jobs=["raw_ingest_job"],
            affected_tables=["nexus_optimized"],
        ),
        "rca": RCAResult(
            incident_id="INC-SEED-001",
            root_cause="Upstream payments API v2.2 renamed txn_amount → transaction_amount without downstream notification",
            confidence=92.0,
            failure_type=FailureType.SCHEMA_DRIFT,
            risk_level=RiskLevel.MEDIUM,
            recommended_action="Apply column mapping patch in staging layer",
            explanation="API changelog confirmed rename. AnalysisException pinpoints exact column.",
            prevention="Add schema contract tests to CI. Enable data catalog change alerts.",
        ),
        "heal": HealResult(
            incident_id="INC-SEED-001",
            status=HealStatus.AUTO_HEALED,
            action_taken="Applied column mapping patch: transaction_amount AS txn_amount in stg_transactions.sql",
            outcome="Pipeline recovered. All downstream tables backfilled. MTTR: 94s.",
            has_code_fix=True,
        ),
    },
    {
        "incident": DetectedIncident(
            incident_id="INC-SEED-002",
            job_name="fraud_model_feature_pipeline",
            failure_type=FailureType.DATA_CORRUPTION,
            error_summary="Critical null spike detected in user_id column (34.2% nulls, threshold 5%)",
            error_logs="[ERROR] Data quality check FAILED: null_count(user_id) = 34.2% (threshold: 5%)",
            timestamp=datetime.now(timezone.utc) - timedelta(days=10),
            upstream_jobs=["raw_ingest_job", "validation_job"],
            affected_tables=["feature_store_fraud"],
        ),
        "rca": RCAResult(
            incident_id="INC-SEED-002",
            root_cause="Upstream microservice returned HTTP 206 Partial Content — 34% of records missing user_id",
            confidence=94.0,
            failure_type=FailureType.DATA_CORRUPTION,
            risk_level=RiskLevel.LOW,
            recommended_action="Rollback Delta table to version N-1 and retrigger pipeline",
            explanation="Row count drop and null spike co-occur with upstream 206 response. Delta time-travel enables clean rollback.",
            prevention="Add row-count anomaly check at ingestion. Set HTTP response validation on upstream connector.",
        ),
        "heal": HealResult(
            incident_id="INC-SEED-002",
            status=HealStatus.AUTO_HEALED,
            action_taken="Rolled back Delta table to version N-1. Retriggered pipeline with clean data.",
            outcome="342,000 affected rows recovered. Pipeline completed successfully. MTTR: 112s.",
        ),
    },
    {
        "incident": DetectedIncident(
            incident_id="INC-SEED-003",
            job_name="customer_segmentation_training",
            failure_type=FailureType.TRANSIENT_FAILURE,
            error_summary="Transient S3 network timeout during data read phase",
            error_logs="[ERROR] java.net.SocketTimeoutException: Read timed out at S3 endpoint",
            timestamp=datetime.now(timezone.utc) - timedelta(days=7),
            upstream_jobs=[],
            affected_tables=["model_training_data"],
        ),
        "rca": RCAResult(
            incident_id="INC-SEED-003",
            root_cause="S3 endpoint latency spike (P99: 4200ms vs baseline 180ms) caused job read timeout",
            confidence=96.0,
            failure_type=FailureType.TRANSIENT_FAILURE,
            risk_level=RiskLevel.LOW,
            recommended_action="Retry with exponential backoff — no data fix required",
            explanation="No data integrity issues. Pure infra transient. S3 endpoint recovered within 90s.",
            prevention="Configure job-level retry policy (max_retries=3, backoff=30s). Add S3 endpoint health monitoring.",
        ),
        "heal": HealResult(
            incident_id="INC-SEED-003",
            status=HealStatus.AUTO_HEALED,
            action_taken="Retried job with exponential backoff. Completed on attempt 2.",
            outcome="Job succeeded on retry. No data loss. MTTR: 67s.",
        ),
    },
    {
        "incident": DetectedIncident(
            incident_id="INC-SEED-004",
            job_name="fraud_model_feature_pipeline",
            failure_type=FailureType.MODEL_DRIFT,
            error_summary="Significant prediction distribution drift detected (PSI=0.28, threshold=0.20)",
            error_logs="[WARN] Model drift: PSI=0.28 for fraud_detection_v3. Prediction mean: 0.82 → 0.44",
            timestamp=datetime.now(timezone.utc) - timedelta(days=5),
            upstream_jobs=[],
            affected_tables=["feature_store_fraud"],
            metrics={"psi_score": 0.28},
        ),
        "rca": RCAResult(
            incident_id="INC-SEED-004",
            root_cause="Concept drift — transaction patterns shifted post-holiday season, model stale after 40 days",
            confidence=89.0,
            failure_type=FailureType.MODEL_DRIFT,
            risk_level=RiskLevel.MEDIUM,
            recommended_action="Rollback to fraud_detection_v2 and trigger retraining on last 30 days",
            explanation="PSI=0.28 indicates significant distribution shift. Model retrained 40 days ago, predates seasonal shift.",
            prevention="Schedule automatic retraining when PSI > 0.15. Add shadow scoring to detect drift 24h earlier.",
        ),
        "heal": HealResult(
            incident_id="INC-SEED-004",
            status=HealStatus.AUTO_HEALED,
            action_taken="Rolled back to fraud_detection_v2 (precision: 91%). Queued retraining job.",
            outcome="Model serving restored. Retraining completed in 3.8h. v4 deployed with PSI=0.04. MTTR: 98s.",
        ),
    },
    {
        "incident": DetectedIncident(
            incident_id="INC-SEED-005",
            job_name="nexus_exp_daily_pipeline",
            failure_type=FailureType.UPSTREAM_DELAY,
            error_summary="SLA breach: job running 3x longer than P95 baseline due to upstream delay",
            error_logs="[WARN] SLA breach detected. Runtime: 920s vs P95 baseline: 300s. Upstream raw_ingest_job delayed.",
            timestamp=datetime.now(timezone.utc) - timedelta(days=3),
            upstream_jobs=["raw_ingest_job"],
            affected_tables=["sep_optimized"],
        ),
        "rca": RCAResult(
            incident_id="INC-SEED-005",
            root_cause="Upstream raw_ingest_job delayed 28 minutes due to source database slow query",
            confidence=91.0,
            failure_type=FailureType.UPSTREAM_DELAY,
            risk_level=RiskLevel.LOW,
            recommended_action="Monitor upstream completion, retrigger downstream with adjusted SLA",
            explanation="Runtime spike correlates exactly with upstream job delay. No data quality issues.",
            prevention="Decouple downstream using event-driven triggers. Add upstream SLA alert at 1.5x baseline.",
        ),
        "heal": HealResult(
            incident_id="INC-SEED-005",
            status=HealStatus.AUTO_HEALED,
            action_taken="Monitored upstream completion. Retriggered downstream pipeline at +28min.",
            outcome="All downstream jobs completed. Dashboard SLA breach window: 28 minutes. MTTR: 83s.",
        ),
    },
    {
        "incident": DetectedIncident(
            incident_id="INC-SEED-006",
            job_name="nexus_exp_daily_pipeline",
            failure_type=FailureType.SCHEMA_DRIFT,
            error_summary="Column 'amount' type changed from DECIMAL(10,2) to STRING in upstream source",
            error_logs="[ERROR] Cannot cast StringType to DecimalType(10,2) in column: amount",
            timestamp=datetime.now(timezone.utc) - timedelta(days=21),
            upstream_jobs=["raw_ingest_job"],
            affected_tables=["nexus_optimized", "nexus_optimized_downstream"],
        ),
        "rca": RCAResult(
            incident_id="INC-SEED-006",
            root_cause="Upstream ERP system changed amount column type from DECIMAL to STRING (included currency symbol)",
            confidence=90.0,
            failure_type=FailureType.SCHEMA_DRIFT,
            risk_level=RiskLevel.MEDIUM,
            recommended_action="Add CAST and REGEXP_REPLACE transformation in staging layer",
            explanation="Type mismatch at column 'amount'. ERP upgrade changelog confirms type change.",
            prevention="Add column type contracts in Great Expectations. Monitor schema version in data catalog.",
        ),
        "heal": HealResult(
            incident_id="INC-SEED-006",
            status=HealStatus.AUTO_HEALED,
            action_taken="Generated type-cast patch: CAST(REGEXP_REPLACE(amount, '[^0-9.]', '') AS DECIMAL(10,2))",
            outcome="Pipeline recovered. Type transformation applied to staging. MTTR: 107s.",
            has_code_fix=True,
        ),
    },
    {
        "incident": DetectedIncident(
            incident_id="INC-SEED-007",
            job_name="customer_segmentation_training",
            failure_type=FailureType.DATA_QUALITY,
            error_summary="Data quality failure: negative values in 'purchase_amount' column (12.4% of rows)",
            error_logs="[ERROR] Expectation failed: column 'purchase_amount' min_value >= 0. Got min: -9842.50",
            timestamp=datetime.now(timezone.utc) - timedelta(days=18),
            upstream_jobs=["validation_job"],
            affected_tables=["model_training_data"],
            metrics={"null_pct": 0, "row_count_drop_pct": 0},
        ),
        "rca": RCAResult(
            incident_id="INC-SEED-007",
            root_cause="Upstream refund processing bug injected negative purchase amounts into training dataset",
            confidence=87.0,
            failure_type=FailureType.DATA_QUALITY,
            risk_level=RiskLevel.LOW,
            recommended_action="Quarantine corrupted partition and backfill from source after upstream fix",
            explanation="Negative values in purchase_amount correlate with refund processing deployment at 02:00 UTC.",
            prevention="Add non-negative value constraint check at ingestion boundary. Block bad data before it reaches feature store.",
        ),
        "heal": HealResult(
            incident_id="INC-SEED-007",
            status=HealStatus.AUTO_HEALED,
            action_taken="Quarantined partition 2024-06-18/batch_002. Triggered backfill from upstream after hotfix.",
            outcome="Bad data isolated. 124,000 rows cleaned. Model training rerun successfully. MTTR: 134s.",
        ),
    },
    {
        "incident": DetectedIncident(
            incident_id="INC-SEED-008",
            job_name="fraud_model_feature_pipeline",
            failure_type=FailureType.CONFIG_MISMATCH,
            error_summary="Spark executor OOM: GC overhead limit exceeded on feature computation job",
            error_logs="[ERROR] java.lang.OutOfMemoryError: GC overhead limit exceeded\n  executor memory: 4g (insufficient for 8M row join)",
            timestamp=datetime.now(timezone.utc) - timedelta(days=12),
            upstream_jobs=[],
            affected_tables=["feature_store_fraud"],
        ),
        "rca": RCAResult(
            incident_id="INC-SEED-008",
            root_cause="Executor memory (4g) insufficient after dataset grew from 2M to 8M rows — config not updated",
            confidence=93.0,
            failure_type=FailureType.CONFIG_MISMATCH,
            risk_level=RiskLevel.LOW,
            recommended_action="Increase executor memory to 8g, add 2g overhead, tune shuffle partitions",
            explanation="OOM correlates directly with dataset size increase. Config last updated when data was 2M rows.",
            prevention="Add data-volume-aware Spark config in job definition. Alert when dataset size increases >50% vs baseline.",
        ),
        "heal": HealResult(
            incident_id="INC-SEED-008",
            status=HealStatus.AUTO_HEALED,
            action_taken="Updated Spark config: executor.memory=8g, memoryOverhead=2g, shuffle.partitions=400",
            outcome="Job completed successfully with new config. No OOM recurrence. MTTR: 89s.",
            has_code_fix=True,
        ),
    },
    {
        "incident": DetectedIncident(
            incident_id="INC-SEED-009",
            job_name="customer_segmentation_training",
            failure_type=FailureType.TRANSIENT_FAILURE,
            error_summary="Database connection reset during feature join phase",
            error_logs="[ERROR] com.mysql.jdbc.exceptions.jdbc4.CommunicationsException: Connection reset by peer",
            timestamp=datetime.now(timezone.utc) - timedelta(days=9),
            upstream_jobs=[],
            affected_tables=["model_training_data"],
        ),
        "rca": RCAResult(
            incident_id="INC-SEED-009",
            root_cause="MySQL connection pool exhausted during maintenance window — transient, no data impact",
            confidence=94.0,
            failure_type=FailureType.TRANSIENT_FAILURE,
            risk_level=RiskLevel.LOW,
            recommended_action="Retry with backoff — connection pool recovered within 2 minutes",
            explanation="Connection reset during scheduled DB maintenance window (02:00-02:15 UTC). No data corruption.",
            prevention="Schedule jobs outside maintenance windows. Implement JDBC connection retry with exponential backoff.",
        ),
        "heal": HealResult(
            incident_id="INC-SEED-009",
            status=HealStatus.AUTO_HEALED,
            action_taken="Waited 90s for connection pool recovery, retried job successfully.",
            outcome="Job succeeded on retry. MTTR: 103s.",
        ),
    },
    {
        "incident": DetectedIncident(
            incident_id="INC-SEED-010",
            job_name="nexus_exp_daily_pipeline",
            failure_type=FailureType.DATA_CORRUPTION,
            error_summary="Empty date column detected: 'event_date' is NULL for 100% of rows in latest partition",
            error_logs="[ERROR] Data quality FAILED: completeness(event_date) = 0.0 (expected >= 0.99)",
            timestamp=datetime.now(timezone.utc) - timedelta(days=6),
            upstream_jobs=["raw_ingest_job"],
            affected_tables=["nexus_optimized"],
            metrics={"null_pct": 100, "row_count_drop_pct": 0},
        ),
        "rca": RCAResult(
            incident_id="INC-SEED-010",
            root_cause="Upstream ETL bug: date parsing failure caused all event_date values to be NULL in latest load",
            confidence=96.0,
            failure_type=FailureType.DATA_CORRUPTION,
            risk_level=RiskLevel.LOW,
            recommended_action="Rollback latest partition to previous version and retrigger after upstream fix",
            explanation="100% null rate on event_date confirms complete parsing failure. Upstream deployment at 23:45 UTC introduced bug.",
            prevention="Add completeness check on all date columns at ingestion. Block partition writes if critical column completeness < 99%.",
        ),
        "heal": HealResult(
            incident_id="INC-SEED-010",
            status=HealStatus.AUTO_HEALED,
            action_taken="Rolled back corrupted partition. Triggered upstream fix notification. Backfill queued.",
            outcome="Clean partition restored. Pipeline on hold pending upstream fix. MTTR: 78s.",
        ),
    },
]


async def seed():
    config = yaml.safe_load(open("config/config.yaml"))
    from src.knowledge.incident_store import IncidentKnowledgeStore
    store = IncidentKnowledgeStore(config["knowledge_store"])

    logger.info(f"Seeding knowledge store with {len(SEED_INCIDENTS)} historical incidents...")
    for entry in SEED_INCIDENTS:
        await store.store(entry["incident"], entry["rca"], entry["heal"])
        logger.success(f"  Seeded {entry['incident'].incident_id} ({entry['incident'].failure_type.value})")

    logger.success(f"\nKnowledge store seeded with {len(SEED_INCIDENTS)} incidents.")
    logger.info("Similarity search will now return relevant history during RCA.")


if __name__ == "__main__":
    asyncio.run(seed())
