# Databricks notebook source
# MAGIC %md
# MAGIC # AEGIS ML Model Retraining Pipeline
# MAGIC
# MAGIC Triggered by **AEGIS MLHealerAgent** when model drift is detected.
# MAGIC
# MAGIC Steps:
# MAGIC 1. Load raw features from Delta table
# MAGIC 2. Engineer features + split train/test
# MAGIC 3. Train GradientBoosting classifier
# MAGIC 4. Compute PSI to measure feature drift
# MAGIC 5. Log all metrics + model to MLflow
# MAGIC 6. Register new model version — AEGIS will promote it if accuracy improves

# COMMAND ----------

import os
import json
import numpy as np
import pandas as pd
import mlflow
import mlflow.sklearn
from datetime import datetime, timezone
from mlflow.tracking import MlflowClient
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    accuracy_score, f1_score, precision_score, recall_score, roc_auc_score
)
from sklearn.preprocessing import StandardScaler
from pyspark.sql import SparkSession

# COMMAND ----------

# Parameters (passed by AEGIS or set manually)
dbutils.widgets.text("model_name", "sales_forecast_v3", "Model Name")
dbutils.widgets.text("trigger", "manual", "Trigger Source")
dbutils.widgets.text("feature_table", "default.aegis_ml_features", "Feature Table")
dbutils.widgets.text("label_col", "target", "Label Column")

MODEL_NAME    = dbutils.widgets.get("model_name")
TRIGGER       = dbutils.widgets.get("trigger")
FEATURE_TABLE = dbutils.widgets.get("feature_table")
LABEL_COL     = dbutils.widgets.get("label_col")

print(f"[AEGIS ML] model={MODEL_NAME} | trigger={TRIGGER}")
print(f"[AEGIS ML] feature_table={FEATURE_TABLE} | label_col={LABEL_COL}")

# COMMAND ----------

# ── Load or generate feature data ───────────────────────────────────────────

spark = SparkSession.builder.getOrCreate()

try:
    df = spark.table(FEATURE_TABLE).toPandas()
    print(f"[AEGIS ML] Loaded {len(df):,} rows from {FEATURE_TABLE}")
    use_synthetic = False
except Exception as e:
    print(f"[AEGIS ML] Table {FEATURE_TABLE} not found ({e}) — using synthetic data")
    use_synthetic = True

if use_synthetic:
    np.random.seed(42)
    n = 10_000
    df = pd.DataFrame({
        "feature_1_revenue":         np.random.normal(5000, 1500, n),
        "feature_2_sessions":        np.random.poisson(12, n).astype(float),
        "feature_3_avg_order_value": np.random.normal(85, 30, n),
        "feature_4_days_since_last": np.random.exponential(14, n),
        "feature_5_product_views":   np.random.poisson(25, n).astype(float),
        "feature_6_cart_abandons":   np.random.poisson(3, n).astype(float),
        "feature_7_email_opens":     np.random.binomial(10, 0.4, n).astype(float),
        "feature_8_discount_pct":    np.random.uniform(0, 0.30, n),
        LABEL_COL: (np.random.rand(n) > 0.42).astype(int),
    })
    print(f"[AEGIS ML] Synthetic dataset: {n:,} rows | class balance: {df[LABEL_COL].mean():.2%}")

# COMMAND ----------

# ── Feature engineering ──────────────────────────────────────────────────────

feature_cols = [c for c in df.columns if c != LABEL_COL]
X = df[feature_cols].fillna(df[feature_cols].median())
y = df[LABEL_COL]

# Compute reference distribution (first 20% of data) for PSI calculation
n_ref = max(int(len(X) * 0.20), 200)
X_ref = X.iloc[:n_ref]
X_curr = X.iloc[n_ref:]


def _psi_single(ref_col: np.ndarray, curr_col: np.ndarray, bins: int = 10) -> float:
    """Population Stability Index for one feature."""
    ref_col = ref_col[np.isfinite(ref_col)]
    curr_col = curr_col[np.isfinite(curr_col)]
    if len(ref_col) == 0 or len(curr_col) == 0:
        return 0.0
    breakpoints = np.percentile(ref_col, np.linspace(0, 100, bins + 1))
    breakpoints = np.unique(breakpoints)
    if len(breakpoints) < 2:
        return 0.0

    ref_pct  = np.histogram(ref_col,  bins=breakpoints)[0] / len(ref_col)
    curr_pct = np.histogram(curr_col, bins=breakpoints)[0] / len(curr_col)

    # Clip to avoid log(0)
    ref_pct  = np.clip(ref_pct,  1e-6, 1)
    curr_pct = np.clip(curr_pct, 1e-6, 1)

    psi = np.sum((curr_pct - ref_pct) * np.log(curr_pct / ref_pct))
    return float(psi)


psi_scores = {c: _psi_single(X_ref[c].values, X_curr[c].values) for c in feature_cols}
overall_psi = float(np.mean(list(psi_scores.values())))
most_drifted = max(psi_scores, key=psi_scores.get)

print(f"[AEGIS ML] PSI — overall={overall_psi:.4f} | worst feature: {most_drifted}={psi_scores[most_drifted]:.4f}")

# COMMAND ----------

# ── Scale + split ────────────────────────────────────────────────────────────

scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

X_train, X_test, y_train, y_test = train_test_split(
    X_scaled, y, test_size=0.20, random_state=42, stratify=y
)
print(f"[AEGIS ML] Train={len(X_train):,} | Test={len(X_test):,}")

# COMMAND ----------

# ── MLflow experiment setup ──────────────────────────────────────────────────

EXPERIMENT_NAME = f"/AEGIS/{MODEL_NAME}"
mlflow.set_experiment(EXPERIMENT_NAME)

# Fetch baseline accuracy from the current Production model (if exists)
baseline_accuracy = 0.0
try:
    client = MlflowClient()
    prod_versions = client.get_latest_versions(MODEL_NAME, stages=["Production"])
    if prod_versions:
        prod_run = client.get_run(prod_versions[0].run_id)
        baseline_accuracy = float(prod_run.data.metrics.get("accuracy", 0.0))
        print(f"[AEGIS ML] Production baseline accuracy: {baseline_accuracy:.2%}")
except Exception as e:
    print(f"[AEGIS ML] Could not fetch Production baseline: {e}")

# COMMAND ----------

# ── Train ────────────────────────────────────────────────────────────────────

params = {
    "n_estimators":  150,
    "max_depth":     5,
    "learning_rate": 0.08,
    "subsample":     0.85,
    "min_samples_split": 20,
    "random_state":  42,
}

with mlflow.start_run(run_name=f"aegis_retrain_{TRIGGER}") as run:
    mlflow.log_params(params)
    mlflow.log_param("trigger", TRIGGER)
    mlflow.log_param("feature_table", FEATURE_TABLE)
    mlflow.log_param("n_train", len(X_train))
    mlflow.log_param("n_test", len(X_test))
    mlflow.log_param("use_synthetic_data", use_synthetic)

    model = GradientBoostingClassifier(**params)
    model.fit(X_train, y_train)

    y_pred  = model.predict(X_test)
    y_proba = model.predict_proba(X_test)[:, 1]

    accuracy  = accuracy_score(y_test, y_pred)
    f1        = f1_score(y_test, y_pred, average="weighted")
    precision = precision_score(y_test, y_pred, average="weighted", zero_division=0)
    recall    = recall_score(y_test, y_pred, average="weighted")
    try:
        roc_auc = roc_auc_score(y_test, y_proba)
    except Exception:
        roc_auc = 0.0

    mlflow.log_metric("accuracy",  accuracy)
    mlflow.log_metric("f1_score",  f1)
    mlflow.log_metric("precision", precision)
    mlflow.log_metric("recall",    recall)
    mlflow.log_metric("roc_auc",   roc_auc)
    mlflow.log_metric("psi_score", overall_psi)
    mlflow.log_metric("baseline_accuracy", baseline_accuracy)

    mlflow.set_tag("baseline_accuracy", str(round(baseline_accuracy, 4)))
    mlflow.set_tag("model_name", MODEL_NAME)
    mlflow.set_tag("trigger_source", TRIGGER)
    mlflow.set_tag("retrain_timestamp", datetime.now(timezone.utc).isoformat())

    # Log per-feature PSI scores as JSON artifact
    psi_path = "/tmp/psi_scores.json"
    with open(psi_path, "w") as f:
        json.dump({"overall_psi": overall_psi, "per_feature": psi_scores}, f, indent=2)
    mlflow.log_artifact(psi_path, "drift_report")

    # Log and register model
    mlflow.sklearn.log_model(
        sk_model=model,
        artifact_path="model",
        registered_model_name=MODEL_NAME,
        input_example=pd.DataFrame(X_test[:5], columns=feature_cols),
    )

    run_id = run.info.run_id
    print(f"[AEGIS ML] Run ID: {run_id}")
    print(f"[AEGIS ML] Accuracy:  {accuracy:.4f}")
    print(f"[AEGIS ML] F1:        {f1:.4f}")
    print(f"[AEGIS ML] ROC-AUC:   {roc_auc:.4f}")
    print(f"[AEGIS ML] PSI Score: {overall_psi:.4f}")

# COMMAND ----------

# ── Summary ──────────────────────────────────────────────────────────────────

improvement = accuracy - baseline_accuracy

print("\n" + "="*55)
print("   AEGIS ML RETRAINING COMPLETE")
print("="*55)
print(f"  Model:       {MODEL_NAME}")
print(f"  Run ID:      {run_id}")
print(f"  Accuracy:    {accuracy:.2%}")
print(f"  Baseline:    {baseline_accuracy:.2%}")
print(f"  Improvement: {improvement:+.2%}")
print(f"  PSI Score:   {overall_psi:.4f}  ({'DRIFTED' if overall_psi > 0.20 else 'stable'})")
print(f"  F1 Score:    {f1:.2%}")
print(f"  ROC-AUC:     {roc_auc:.2%}")
print("="*55)
print("\nAEGIS will now evaluate whether to promote this model to Production.")

if improvement >= 0.005:
    print(f"\n✅ Model improved by {improvement:+.2%} — AEGIS should promote it.")
else:
    print(f"\n⚠️  Improvement {improvement:+.2%} below threshold — AEGIS may keep existing model.")

dbutils.notebook.exit(json.dumps({
    "status": "success",
    "model_name": MODEL_NAME,
    "run_id": run_id,
    "accuracy": round(accuracy, 4),
    "baseline_accuracy": round(baseline_accuracy, 4),
    "improvement": round(improvement, 4),
    "psi_score": round(overall_psi, 4),
    "f1_score": round(f1, 4),
}))
