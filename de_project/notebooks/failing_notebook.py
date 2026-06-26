# Databricks notebook source
# MAGIC %md
# MAGIC # Data Processing Pipeline - Quality Validation
# MAGIC This notebook validates transformed data quality and performs aggregations.
# MAGIC
# MAGIC ⚠️ Contains intentional bugs for AEGIS self-healing demonstration.

# COMMAND ----------

# DBTITLE 1,Import Libraries
import pandsa as pd  # BUG 1: Typo in pandas import
import numpy as np
from pyspark.sql import functions as F
from pyspark.sql.types import StructType, StructField, StringType, IntegerType, DoubleType

print("Starting data quality validation pipeline...")

# COMMAND ----------

# DBTITLE 1,Load Transformed Data
# BUG 2: Wrong table name - should be 'transformed_sales_data'
df = spark.table("transformed_sales_dataa")
print(f"Loaded {df.count()} records")

# COMMAND ----------

# DBTITLE 1,Calculate Revenue Metrics
# BUG 3: Using wrong column name - 'price' doesn't exist, should be 'unit_price'
revenue_df = df.withColumn(
    "total_revenue",
    F.col("quantity") * F.col("price")
)

# BUG 4: Dividing by column that may contain zeros
revenue_df = revenue_df.withColumn(
    "profit_margin",
    F.col("profit") / F.col("quantity")  # Will fail when quantity is 0
)

# COMMAND ----------

# DBTITLE 1,Apply Business Rules
# BUG 5: Logic error - condition is reversed
# Should filter records WHERE revenue >= 1000, not < 1000
high_value_transactions = revenue_df.filter(F.col("total_revenue") < 1000)

print(f"High value transactions: {high_value_transactions.count()}")

# COMMAND ----------

# DBTITLE 1,Aggregate by Customer
# BUG 6: Grouping by wrong column - 'customer_name' instead of 'customer_id'
customer_summary = revenue_df.groupBy("customer_name").agg(
    F.sum("total_revenue").alias("total_spent"),
    F.avg("profit_margin").alias("avg_margin"),
    F.count("*").alias("transaction_count")
)

# COMMAND ----------

# DBTITLE 1,Calculate Year-over-Year Growth
# BUG 7: Undefined variable - 'previous_year_revenue' never defined
yoy_growth = (current_year_revenue - previous_year_revenue) / previous_year_revenue * 100
print(f"YoY Growth: {yoy_growth}%")

# COMMAND ----------

# DBTITLE 1,Write Results
# BUG 8: Writing to wrong path without proper error handling
output_path = "/mnt/data/quality_reports"
customer_summary.write.mode("overwrite").parquet(output_path)

# BUG 9: Division by zero in final calculation
success_rate = total_processed / 0
print(f"Success rate: {success_rate}%")
