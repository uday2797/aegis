# AEGIS Auto-Generated Schema Fix
# Incident: INC-0A7A0202
# Root Cause: Column renamed from txn_amount to transaction_amount

-- models/staging/stg_transactions.sql
SELECT
    transaction_amount AS txn_amount,  -- AEGIS fix: mapped renamed column
    user_id,
    ts,
    merchant_id
FROM {{ source("payments", "transactions") }}
