# Databricks notebook source
# MAGIC %md
# MAGIC # 01 — Data Ingestion
# MAGIC Ingests raw transaction data from the source system.

# COMMAND ----------

import pandas as pd
from datetime import datetime, timedelta
import random

print(f"[{datetime.now().isoformat()}] Starting data ingestion...")

# COMMAND ----------

# DBTITLE 1,Simulate source data read
random.seed(42)
data = {
    "id":        list(range(1, 1001)),
    "amount":    [round(random.uniform(10, 5000), 2) for _ in range(1000)],
    "category":  [random.choice(["retail", "food", "travel", "tech"]) for _ in range(1000)],
    "user_id":   [random.randint(1000, 9999) for _ in range(1000)],
    "timestamp": [datetime.now() - timedelta(seconds=i * 30) for i in range(1000)],
    "status":    [random.choice(["completed", "pending", "failed"]) for _ in range(1000)],
}

df = pd.DataFrame(data)
print(f"Ingested {len(df)} rows from source")
print(df.dtypes)
print(df.head(3))

# COMMAND ----------

# DBTITLE 1,Persist to Delta (simulated)
print(f"[INGEST] Writing {len(df)} rows to staging layer...")
print("[INGEST] ✅ Completed — rows written to staging.transactions_raw")