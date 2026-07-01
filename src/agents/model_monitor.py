"""
AEGIS Model Monitor Agent
Detects model performance degradation and drift using MLflow metrics.

Falls back to simulated drift detection if MLflow is not configured,
which is useful for hackathon demos and testing.
"""
import os
import random
from datetime import datetime, timezone
from loguru import logger


# Thresholds for model health
ACCURACY_DROP_THRESHOLD = 0.05   # flag if accuracy drops > 5% from baseline
PSI_DRIFT_THRESHOLD = 0.20       # Population Stability Index > 0.20 = drift
MIN_ACCEPTABLE_ACCURACY = 0.75   # absolute floor


class ModelMonitorAgent:
    """
    Monitors ML model health via MLflow.

    Checks:
    - Accuracy / F1 regression vs baseline
    - Data drift (PSI score)
    - Prediction distribution shift

    Falls back to realistic simulation when MLflow is not available.
    """

    def __init__(self, config: dict):
        self.config = config
        self.mlflow_uri = os.environ.get(
            "MLFLOW_TRACKING_URI",
            config.get("mlflow_uri", ""),
        )
        self._mlflow_available = self._check_mlflow()

    def _check_mlflow(self) -> bool:
        """Return True if MLflow is reachable."""
        if not self.mlflow_uri:
            return False
        try:
            import mlflow
            mlflow.set_tracking_uri(self.mlflow_uri)
            mlflow.search_experiments(max_results=1)
            logger.info(f"[ModelMonitor] Connected to MLflow at {self.mlflow_uri}")
            return True
        except Exception as e:
            logger.debug(f"[ModelMonitor] MLflow not available: {e} — using simulation")
            return False

    async def check_model_health(self) -> list[dict]:
        """
        Check health of all registered models.

        Returns list of model health reports:
        {
            "model_name": str,
            "version": str,
            "baseline_accuracy": float,
            "current_accuracy": float,
            "accuracy_drop": float,
            "psi_score": float,
            "status": "healthy" | "degraded" | "critical",
            "alert": str | None,
        }
        """
        if self._mlflow_available:
            return await self._check_mlflow_models()
        else:
            return self._simulate_model_health()

    async def _check_mlflow_models(self) -> list[dict]:
        """Query real MLflow registry for model metrics."""
        reports = []
        try:
            import mlflow
            from mlflow.tracking import MlflowClient

            client = MlflowClient()
            registered_models = client.search_registered_models(max_results=10)

            for rm in registered_models:
                latest_versions = client.get_latest_versions(rm.name, stages=["Production"])
                if not latest_versions:
                    continue

                version = latest_versions[0]
                run = client.get_run(version.run_id)
                metrics = run.data.metrics

                current_acc = metrics.get("accuracy") or metrics.get("val_accuracy") or 0.0
                baseline_acc = float(
                    (run.data.tags or {}).get("baseline_accuracy", current_acc + 0.02)
                )
                psi = metrics.get("psi_score", 0.0)
                drop = baseline_acc - current_acc

                status = "healthy"
                alert = None
                if current_acc < MIN_ACCEPTABLE_ACCURACY:
                    status = "critical"
                    alert = f"Accuracy {current_acc:.2%} below minimum threshold {MIN_ACCEPTABLE_ACCURACY:.2%}"
                elif drop > ACCURACY_DROP_THRESHOLD:
                    status = "degraded"
                    alert = f"Accuracy dropped {drop:.2%} from baseline {baseline_acc:.2%} → {current_acc:.2%}"
                elif psi > PSI_DRIFT_THRESHOLD:
                    status = "degraded"
                    alert = f"Data drift detected: PSI={psi:.3f} > threshold {PSI_DRIFT_THRESHOLD}"

                reports.append({
                    "model_name": rm.name,
                    "version": version.version,
                    "baseline_accuracy": round(baseline_acc, 4),
                    "current_accuracy": round(current_acc, 4),
                    "accuracy_drop": round(drop, 4),
                    "psi_score": round(psi, 4),
                    "status": status,
                    "alert": alert,
                    "source": "mlflow",
                })

            logger.info(f"[ModelMonitor] Checked {len(reports)} MLflow model(s)")
        except Exception as e:
            logger.warning(f"[ModelMonitor] MLflow query failed: {e}")

        return reports

    def _simulate_model_health(self) -> list[dict]:
        """
        Realistic simulation of model health for demo/hackathon purposes.
        Occasionally injects a degradation scenario to demonstrate detection.
        """
        # Seed with minute-level time so results are stable within a minute
        # but change between runs — makes demo reproducible yet interesting
        seed = int(datetime.now(tz=timezone.utc).timestamp()) // 120  # changes every 2 min
        rng = random.Random(seed)

        force_drift = os.environ.get("AEGIS_FORCE_ML_DRIFT", "").lower() in ("1", "true", "yes")
        models = [
            {
                "name": "sales_forecast_v3",
                "baseline": 0.924,
                "inject_degradation": force_drift or rng.random() < 0.35,
            },
            {
                "name": "churn_classifier_v2",
                "baseline": 0.881,
                "inject_degradation": False,  # always healthy — shows contrast
            },
        ]

        reports = []
        for m in models:
            if m["inject_degradation"]:
                # Simulate accuracy drop + data drift
                drop = rng.uniform(0.06, 0.12)
                current_acc = m["baseline"] - drop
                psi = rng.uniform(0.22, 0.35)
                status = "degraded"
                alert = (
                    f"⚠️  Model accuracy dropped {drop:.1%}: "
                    f"{m['baseline']:.1%} → {current_acc:.1%}. "
                    f"Data drift PSI={psi:.3f} detected."
                )
            else:
                drift = rng.uniform(-0.008, 0.008)
                current_acc = m["baseline"] + drift
                psi = rng.uniform(0.02, 0.08)
                status = "healthy"
                alert = None

            reports.append({
                "model_name": m["name"],
                "version": "latest",
                "baseline_accuracy": m["baseline"],
                "current_accuracy": round(current_acc, 4),
                "accuracy_drop": round(m["baseline"] - current_acc, 4),
                "psi_score": round(psi, 4),
                "status": status,
                "alert": alert,
                "source": "simulated",
            })

        degraded = [r for r in reports if r["status"] != "healthy"]
        if degraded:
            logger.warning(
                f"[ModelMonitor] ⚠️  {len(degraded)} model(s) degraded: "
                + ", ".join(r["model_name"] for r in degraded)
            )
        else:
            logger.success(f"[ModelMonitor] ✅ All {len(reports)} models healthy")

        return reports
