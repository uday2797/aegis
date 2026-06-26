# Databricks notebook source
# MAGIC %md
# MAGIC # Validate — Data Quality Checks
# MAGIC Validates data quality after transformation.

# COMMAND ----------

# DBTITLE 1,Import required libraries
import pandas as pd
print("Starting data quality validation...")

# COMMAND ----------

# DBTITLE 1,Variable calculation
defined_variable = 5
result = defined_variable * 10
print(f"Result: {result}")

# COMMAND ----------

# DBTITLE 1,Safe division
value = 100 / 1
print(f"Value: {value}")