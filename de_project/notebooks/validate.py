# Databricks notebook source
# MAGIC %md
# MAGIC # Validate — Data Quality Checks
# MAGIC Validates data quality after transformation.
# MAGIC
# MAGIC ⚠️ This notebook contains intentional bugs for AEGIS self-healing demo.

# COMMAND ----------

# DBTITLE 1,Import error - typo in library name
import pandas as pd
print("Starting data quality validation...")

# COMMAND ----------

# DBTITLE 1,Undefined variable error
defined_variable = 5  # Define the variable
result = defined_variable * 10
print(f"Result: {result}")

# COMMAND ----------

# DBTITLE 1,Division by zero
value = 100 / 1  # Avoid division by zero
print(f"Value: {value}")