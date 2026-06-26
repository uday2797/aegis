# AEGIS — Autonomous Data Pipeline Self-Healing Agent

> **"When your data pipeline breaks at 3am, AEGIS fixes it before you even wake up."**

**Hackathon:** AI-Autonomous Reliability Engineer | Data DevOps & MLOps Track  
**Theme:** Self-Healing Data & ML Systems

---

## What problem does this solve?

Every data engineering team has woken up at 3am because a Databricks job failed. Someone has to:

1. Find the failed job
2. Read the error log
3. Figure out why it broke
4. Write a fix
5. Test the fix
6. Deploy it
7. Verify it works
8. Write an incident report

**AEGIS automates all of that. You sleep. AEGIS works.**

---

## How it works

```
Databricks job fails
        ↓
AEGIS detects the failure (real Databricks API)
        ↓
GPT-5.5 reads the full error trace + recent pipeline history
        ↓
Root cause identified with confidence score
        ↓
Confidence gate: if < 70% → escalate to human, else continue
        ↓
GPT-5.5 deep-scans notebook → lists ALL bugs → fixes everything
        ↓
Syntax check + lint + PEP8 auto-format before uploading
        ↓
Fixed notebook uploaded to Databricks, job re-run to verify
        ↓
If re-run passes → GitHub PR created with the fix
        ↓
AEGIS waits for human to review + merge PR
        ↓
CI/CD triggers Databricks deployment automatically
        ↓
Post-deployment health check confirms job is healthy
        ↓
Structured incident report saved to data/reports/
        ↓
8-stage email notifications sent at every step
```

---

## 8-Stage Email Notifications

| # | When | What it says |
|---|---|---|
| 1 | Health check done | "✅ All 8 jobs healthy" or "⚠️ 1 job failed" |
| 2 | Failure found | "Job X failed. Root cause: [AI explanation]. Confidence: 99%" |
| 3 | Fix started | "🔧 AI is fixing the broken notebook right now..." |
| 4 | Fix done | "✅ Job fixed and running successfully. Time taken: 2 min" |
| 5 | PR created | "📝 Code fix ready for review: [GitHub link]" |
| 6 | Deployed | "🚀 Fix deployed to production" |
| 7 | All clear | "🎉 Full cycle complete. Job is healthy again." |
| 8 | Escalation | "❌ AEGIS couldn't fix this. Human help needed." |

---

## Guardrails (Safety First)

AEGIS never acts recklessly. Every fix goes through mandatory safety checks:

| Guardrail | What it does |
|---|---|
| **Confidence Gate** | If AI is less than 70% confident → escalates to human instead of guessing |
| **Syntax Validation** | Checks fixed code is valid Python before uploading (won't upload broken code) |
| **Lint Check** | Pyflakes scan catches undefined variables, unused imports |
| **PEP8 Auto-Format** | autopep8 formats code to professional Python standards |
| **Rollback** | If the fix makes things worse → restores original notebook automatically |
| **Rate Limiter** | Max 5 job triggers per 10 minutes — protects your cloud bill |
| **Audit Log** | Every action appended to `data/audit_log.jsonl` (append-only, tamper-evident) |
| **PR Gate** | Code only reaches production after a human approves it on GitHub |

---

## The 8 Agents

| Agent | Job |
|---|---|
| **StatusCheckerAgent** | Polls real Databricks jobs, extracts error traces from failed tasks |
| **ModelMonitorAgent** | Queries MLflow registry for accuracy drops and data drift (PSI score) |
| **RCAAgent** | GPT-5.5 root cause analysis using error logs + past incident context |
| **JobFixerAgent** | Deep-scans notebook, lists all bugs, fixes everything in one pass, uploads |
| **PRManagerAgent** | Creates GitHub PR with the fix, polls until merged |
| **DeploymentAgent** | Triggers GitHub Actions CD workflow, monitors to completion |
| **MailSenderAgent** | Sends 8-stage Gmail notifications throughout the lifecycle |
| **IncidentReport** | Auto-generates structured JSON report at end of every cycle |

---

## ML Model Drift Detection

AEGIS monitors ML model health — not just job failures.

**Detected signals:**
- Accuracy drops > 5% from baseline
- Data drift: PSI score > 0.20 (input distribution shifted)
- Absolute accuracy below 75% (critical floor)

**How it works:**
- Queries your MLflow registry (`MLFLOW_TRACKING_URI`) for real model metrics
- Falls back to realistic simulation when MLflow is not configured

**Example output:**
```
⚠️  sales_forecast_v3:  accuracy dropped 8.3%: 92.4% → 84.1%, PSI=0.27
✅  churn_classifier_v2: healthy (accuracy=88.2%, PSI=0.04)
```

---

## Auto-Generated Incident Report

At the end of every cycle, AEGIS saves a structured JSON report to `data/reports/`.

| Field | Example |
|---|---|
| Incident ID | `INC-7BC959AE` |
| Job name | `[AEGIS Test] Data Quality Validation` |
| Root cause | `df.cache() not supported on Serverless compute` |
| RCA confidence | `99%` |
| Action taken | `GPT-5.5 autonomous notebook repair` |
| Fix result | `SUCCESS` |
| MTTR | `2 minutes 3 seconds` |
| GitHub PR | `https://github.com/uday2797/aegis/pull/4` |
| Prevention tip | `Remove df.cache() on Serverless; use Delta table writes instead` |
| Guardrails triggered | List of every safety check that ran |
| ML model health | Accuracy and drift status at time of incident |

---

## Performance (Measured on real Databricks)

| Metric | Value |
|---|---|
| Time to detect failure | ~5 seconds |
| Time to run RCA | ~10 seconds |
| Time for AI to fix notebook | ~77 seconds |
| Time to verify fix | ~22 seconds |
| **Total: broken → fixed** | **~2 minutes** |
| Human intervention required | **Zero** |

---

## Quick Start

### Prerequisites
- Python 3.10+
- VPN connected (for EPAM DIAL API access)
- `.env` file with your credentials (copy from `.env.example`)

### Install
```powershell
pip install -r requirements.txt
```

### Run
```powershell
$env:PYTHONPATH="C:\path\to\aegis"
python demo/production_multi_agent.py
```

### What you'll see
```
============================================================
🛡️  AEGIS - Autonomous Excellence Guardian & Intelligent System
============================================================

📋 Found 8 Databricks jobs:
+---------------+------------------------------------+--------+---------------+
| Job ID        | Job Name                           | Tasks  | Latest Status |
+---------------+------------------------------------+--------+---------------+
| 825205099813  | Data Quality Validation - Failing  | 1      | ❌ FAILED    |
| 470575380114  | Data Processing Pipeline           | 3      | ✅ SUCCESS   |
+---------------+------------------------------------+--------+---------------+

Your selection: 825205099813
```

Then AEGIS runs the full lifecycle automatically. At the end:
```
📋 Incident Report: data/reports/RPT-INC-7BC959AE-20260626T163022.json
```

---

## Project Structure

```
aegis/
│
├── demo/
│   └── production_multi_agent.py   ← START HERE
│
├── src/
│   ├── workflow.py                 ← 15-node LangGraph orchestration
│   ├── agents/
│   │   ├── status_checker.py       ← Real Databricks job health checks
│   │   ├── model_monitor.py        ← MLflow model drift detection
│   │   ├── mail_sender.py          ← 8-stage Gmail notifications
│   │   ├── job_fixer.py            ← GPT-5.5 notebook repair
│   │   ├── pr_manager.py           ← GitHub PR creation + approval wait
│   │   └── deployment.py           ← CI/CD trigger + monitoring
│   ├── diagnosis/
│   │   ├── rca_agent.py            ← LLM root cause analysis
│   │   └── context_assembler.py    ← Assembles real Databricks context for LLM
│   ├── guardrails/
│   │   ├── audit_log.py            ← Append-only action log
│   │   ├── rate_limiter.py         ← Prevents runaway job triggers
│   │   └── validators.py           ← Syntax + lint + PEP8 validation
│   ├── reporting/
│   │   └── incident_report.py      ← Structured JSON incident report
│   └── knowledge/
│       └── incident_store.py       ← Past incident memory (ChromaDB)
│
├── de_project/
│   ├── databricks.yml              ← DAB bundle configuration
│   └── notebooks/
│       ├── failing_notebook.py     ← Demo: intentionally broken notebook
│       ├── 01_ingest.py            ← Ingestion pipeline
│       └── 02_transform.py         ← Transformation pipeline
│
├── data/
│   ├── audit_log.jsonl             ← Every action AEGIS took
│   ├── knowledge_store/            ← ChromaDB vector store (past incidents)
│   └── reports/                    ← Incident reports (one JSON per cycle)
│
├── .github/workflows/
│   ├── ci.yml                      ← Lint + DAB bundle validate on PR
│   └── cd.yml                      ← Deploy on merge
│
├── config/config.yaml              ← All thresholds and settings
├── .env                            ← Your secrets (never committed)
├── requirements.txt
└── docker-compose.yml
```

---

## Environment Variables

```bash
# EPAM DIAL API (GPT-5.5 for RCA and notebook repair)
DIAL_API_KEY=dial-xxx
DIAL_API_ENDPOINT=https://ai-proxy.lab.epam.com
DIAL_DEPLOYMENT=gpt-5.5-2026-04-24
DIAL_API_VERSION=2025-04-01-preview

# Databricks (real workspace — no simulation)
DATABRICKS_HOST=https://dbc-xxx.azuredatabricks.net
DATABRICKS_TOKEN=dapixxx
DATABRICKS_JOB_ID=                 # optional: pre-select a specific job

# GitHub (PR creation and CD trigger)
GITHUB_TOKEN=ghp_xxx
GITHUB_REPO_OWNER=your-username
GITHUB_REPO_NAME=aegis

# Gmail (8-stage notifications)
GMAIL_SENDER=your-email@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
GMAIL_RECIPIENTS=recipient@example.com

# MLflow (optional — real model drift monitoring)
MLFLOW_TRACKING_URI=https://your-mlflow-server
```

---

## Technology Stack

| What | Tool |
|---|---|
| AI model | GPT-5.5 via EPAM DIAL |
| Agent orchestration | LangGraph (15-node state machine) |
| Data platform | Databricks (real API, no simulation) |
| Model monitoring | MLflow |
| Notifications | Gmail SMTP (8 stages) |
| Code hosting + CI/CD | GitHub Actions |
| Code validation | pyflakes + autopep8 |
| Knowledge store | ChromaDB (past incident memory) |
| Language | Python 3.10+ |

---

## What makes AEGIS different

Most monitoring tools just **alert** you. AEGIS **fixes it**.

| Capability | Other tools | AEGIS |
|---|---|---|
| Detect job failures | ✅ | ✅ |
| Explain what broke | ✅ | ✅ |
| Fix it automatically | ❌ | ✅ |
| Fix ALL bugs in one pass (not just the triggering error) | ❌ | ✅ |
| Validate fix before deploying | ❌ | ✅ |
| Rollback if fix makes things worse | ❌ | ✅ |
| Detect ML model drift | ❌ | ✅ |
| Generate structured incident report | ❌ | ✅ |
| Learn from past incidents | ❌ | ✅ |
| Keep human in control (PR gate) | ❌ | ✅ |
| Full audit trail of every action | ❌ | ✅ |

---

## The Full Loop

```
DETECT → DIAGNOSE → DECIDE → HEAL → VERIFY → DEPLOY → REPORT → LEARN
```

| Stage | What Happens |
|---|---|
| **Detect** | Real Databricks API — polls job run states, extracts error traces |
| **Diagnose** | GPT-5.5 RCA using error logs + live pipeline activity + past incident memory |
| **Decide** | Confidence gate: auto-heal if ≥ 70% confident, else escalate to human |
| **Heal** | Deep scan entire notebook → list all bugs → fix everything → PEP8 format |
| **Verify** | Syntax check + lint + re-run job on Databricks — rollback if it still fails |
| **Deploy** | GitHub PR → human approval → CI/CD → post-deployment health check |
| **Report** | Structured JSON: root cause, MTTR, fix diff, guardrails triggered, ML health |
| **Learn** | Resolved incident stored in ChromaDB for future RCA enrichment |

---

*AEGIS — Because your data systems deserve an engineer that never sleeps.*
