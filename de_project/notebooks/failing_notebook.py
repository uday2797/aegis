# Databricks notebook source
# MAGIC %md
# MAGIC # Validate — Data Quality Checks
# MAGIC Validates data quality after transformation.
# MAGIC
# MAGIC ⚠️ This notebook contains intentional bugs for AEGIS self-healing demo.

# COMMAND ----------

# DBTITLE 1,Import error - typo in library name
import pandsa as pd
print("Starting data quality validation...")

# COMMAND ----------

# DBTITLE 1,Undefined variable error
result = undefined_variable * 10
print(f"Result: {result}")

# COMMAND ----------

# DBTITLE 1,Division by zero
value = 100 / 0
print(f"Value: {value}")
