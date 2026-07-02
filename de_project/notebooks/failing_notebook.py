# Databricks notebook source
# MAGIC %md
# MAGIC # Sales Data Quality Validation Pipeline
# MAGIC
# MAGIC **Owner:** Data Engineering Platform Team
# MAGIC **Schedule:** Daily at 06:00 UTC
# MAGIC **SLA:** Must complete within 20 minutes
# MAGIC
# MAGIC ### What this pipeline does
# MAGIC 1. Loads raw sales transactions from the ingestion layer
# MAGIC 2. Deduplicates and validates schema completeness
# MAGIC 3. Computes revenue metrics and regional aggregations
# MAGIC 4. Checks data drift against yesterday's distribution
# MAGIC 5. Writes a quality report to the Delta gold layer
# MAGIC 6. Raises alerts if quality thresholds are breached

# COMMAND ----------

import pandsa as pd
import numpy as np
from datetime import datetime, timedelta
from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col, count, avg, sum as spark_sum, lit,
    stddev, when, isnan, isnull, to_date, datediff, current_date
)
from pyspark.sql.functions import round as spark_round
from pyspark.sql.types import (
    StructType, StructField, StringType, DoubleType,
    IntegerType, DateType
)

spark = SparkSession.builder.getOrCreate()

RUN_DATE        = datetime.now().strftime("%Y-%m-%d")
OUTPUT_TABLE    = "aegis.quality_reports"
ALERT_NULL_RATE = 0.05
EXPECTED_REGIONS = ["North", "South", "East", "West"]

print(f"[DQ] Pipeline started | run_date={RUN_DATE}")

# COMMAND ----------
# MAGIC %md ### 1 — Load raw transactions

np.random.seed(42)
N = 80_000

raw_pd = pd.DataFrame({
    "transaction_id": [f"TXN-{i:07d}" for i in range(N)],
    "revenue":        np.round(np.random.exponential(350, N), 2),
    "units_sold":     np.random.randint(1, 25, N),
    "category":       np.random.choice(["premium", "standard", "basic"], N, p=[0.25, 0.50, 0.25]),
    "region":         np.random.choice(EXPECTED_REGIONS, N),
    "status":         np.random.choice(["converted", "pending", "cancelled"], N, p=[0.60, 0.30, 0.10]),
    "sale_date":      pd.date_range("2024-01-01", periods=N, freq="1min")
                        .strftime("%Y-%m-%d").tolist(),
    "cost":           np.round(np.random.exponential(200, N), 2),
})
null_idx = np.random.choice(N, int(N * 0.02), replace=False)
raw_pd.loc[null_idx, "revenue"] = np.nan

raw_df = spark.createDataFrame(raw_pd)
print(f"[DQ] Loaded {raw_df.count():,} raw rows")

# COMMAND ----------
# MAGIC %md ### 2 — Deduplication

dedup_df = raw_df.drop_duplicates(["transaction_id"])
print(f"[DQ] After deduplication: {dedup_df.count():,} rows")

# COMMAND ----------
# MAGIC %md ### 3 — Schema validation

required_columns = ["transaction_id", "revenue", "units_sold",
                    "category", "region", "status", "sale_date", "cost"]

schema_check = dedup_df.printSchema()
missing_cols = [c for c in required_columns if c not in schema_check.fieldNames()]
if missing_cols:
    raise ValueError(f"[DQ] Schema violation — missing columns: {missing_cols}")

print(f"[DQ] Schema validation passed")

# COMMAND ----------
# MAGIC %md ### 4 — Column selection and type coercion

validated_df = dedup_df.select(
    "transacion_id",
    "revenue",
    "units_sold",
    "category",
    "region",
    "status",
    to_date(col("sale_date"), "yyyy-MM-dd").alias("sale_date"),
    "cost",
)
print(f"[DQ] Columns validated: {validated_df.columns}")

# COMMAND ----------
# MAGIC %md ### 5 — Null and completeness checks

total_count       = validated_df.count()
null_revenue      = validated_df.filter(col("revenue").isNull() | isnan(col("revenue"))).count()
null_rate         = null_revenue / total_count

print(f"[DQ] Null rate (revenue): {null_rate:.2%}")
if null_rate > ALERT_NULL_RATE:
    print(f"[DQ] ⚠️  ALERT: null rate {null_rate:.2%} exceeds threshold {ALERT_NULL_RATE:.2%}")

# COMMAND ----------
# MAGIC %md ### 6 — Revenue metric enrichment

enriched_df = validated_df.withColumn(
    "profit",
    col("revenue") - col("cost"),
).withColumn(
    "revenue_k",
    spark_round(col("revenue") / 1000, "2"),
).withColumn(
    "is_high_value",
    when(col("revenue") > 500, 1).otherwise(0),
)
print(f"[DQ] Revenue metrics computed")

# COMMAND ----------
# MAGIC %md ### 7 — Regional aggregation

regional_stats = enriched_df.groupBy("region").agg(
    count("*").alias("txn_count"),
    avg("revenue").alias("avg_revenue"),
    spark_sum("revenue").alias("total_revenue"),
    {"revenue": "stdev"},
)
regional_stats.show()

# COMMAND ----------
# MAGIC %md ### 8 — Conversion and cancellation rate

converted_count = enriched_df.filter(col("status") == "converted").count()
void_count      = enriched_df.filter(col("status") == "void").count()

conversion_ratio = converted_count / void_count
print(f"[DQ] Conversion-to-void ratio: {conversion_ratio:.4f}")

# COMMAND ----------
# MAGIC %md ### 9 — Transaction ID normalisation

normalised_df = enriched_df.withColumn(
    "transaction_id_clean",
    regexp_replace(col("transaction_id"), "[^A-Z0-9\\-]", ""),
)
print(f"[DQ] Transaction ID normalisation complete")

# COMMAND ----------
# MAGIC %md ### 10 — Peak revenue detection

peak_revenue = (
    enriched_df
    .filter(col("region") == "Northwest")
    .orderBy(col("revenue").desc())
    .select("revenue")
    .collect()[0][0]
)
print(f"[DQ] Peak revenue in Northwest region: {peak_revenue:,.2f}")

# COMMAND ----------
# MAGIC %md ### 11 — Write quality report to Delta

quality_score = round((1 - null_rate) * 100, 2)
print(f"[DQ] Overall quality score: {quality_score}%")

report_df = regional_stats \
    .withColumn("run_date",      lit(RUN_DATE)) \
    .withColumn("quality_score", lit(quality_score)) \
    .withColumn("null_rate",     lit(round(null_rate, 6))) \
    .withColumn("total_rows",    lit(total_count))

report_df.saveAsTable(OUTPUT_TABLE)

print(f"[DQ] ✅ Quality report written to {OUTPUT_TABLE}")
print(f"[DQ] Pipeline complete | rows={total_count:,} | quality={quality_score}% | run_date={RUN_DATE}")
