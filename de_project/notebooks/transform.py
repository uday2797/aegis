# Databricks notebook source
# MAGIC %md
# MAGIC # 02 - Data Transformation
# MAGIC Applies business rules and enriches the raw transaction data.

# COMMAND ----------

import pandas as pd
import random
from datetime import datetime

print(f"[{datetime.now().isoformat()}] Starting transformation...")

# COMMAND ----------

# DBTITLE 1,Simulate reading from staging
random.seed(42)

df = pd.DataFrame({
    "id": list(range(1, 1001)),
    "amount": [round(random.uniform(10, 5000), 2) for _ in range(1000)],
    "category": [random.choice(["retail", "food", "travel", "tech"]) for _ in range(1000)],
    "user_id": [random.randint(1000, 9999) for _ in range(1000)],
    "status": [random.choice(["completed", "pending", "failed"]) for _ in range(1000)],
})

# COMMAND ----------

# DBTITLE 1,Apply business transformations
df["is_high_value"] = df["amount"] > 2500

df["risk_score"] = (
    (df["amount"] / 5000 * 0.6) +
    ((df["status"] == "failed").astype(int) * 0.4)
).round(3)

if not df.empty:
    summary = (
        df.groupby("category", as_index=False)
          .agg({
              "id": "count",
              "amount": "sum",
              "risk_score": "mean"
          })
          .rename(columns={
              "id": "total_txn",
              "amount": "total_amount",
              "risk_score": "avg_risk"
          })
    )

    print("Category summary:")
    print(summary.to_string(index=False))
else:
    print("Dataframe is empty, skipping aggregation.")

# COMMAND ----------

# DBTITLE 1,Write to curated layer (simulated)
print(f"\n[TRANSFORM] Writing {len(df)} enriched rows to curated.transactions")
print("[TRANSFORM] Completed - curated layer updated")