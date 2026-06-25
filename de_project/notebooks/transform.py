# Databricks notebook source
# MAGIC %md
# MAGIC # 02 — Data Transformation
# MAGIC Applies business rules and enriches the raw transaction data.

# COMMAND ----------

import pandas as pd
import numpy as np
from datetime import datetime

print(f"[{datetime.now().isoformat()}] Starting transformation...")

# COMMAND ----------

# DBTITLE 1,Simulate reading from staging
import random
random.seed(42)
df = pd.DataFrame({
    "id":       range(1, 1001),
    "amount":   [round(random.uniform(10, 5000), 2) for _ in range(1000)],
    "category": [random.choice(["retail", "food", "travel", "tech"]) for _ in range(1000)],
    "user_id":  [random.randint(1000, 9999) for _ in range(1000)],
    "status":   [random.choice(["completed", "pending", "failed"]) for _ in range(1000)],
})

# COMMAND ----------

# DBTITLE 1,Apply business transformations
# Mark high-value transactions
df["is_high_value"] = df["amount"] > 2500

# Compute risk score
df["risk_score"] = (df["amount"] / 5000 * 0.6 +
                    (df["status"] == "failed").astype(int) * 0.4).round(3)

# Aggregate by category
summary = (df.groupby("category")
             .agg(total_txn=("id", "count"),
                  total_amount=("amount", "sum"),
                  avg_risk=("risk_score", "mean"))
             .reset_index())

print("Category summary:")
print(summary.to_string())

# COMMAND ----------

# DBTITLE 1,Write to curated layer (simulated)
print(f"\n[TRANSFORM] Writing {len(df)} enriched rows to curated.transactions")
print("[TRANSFORM] ✅ Completed — curated layer updated")