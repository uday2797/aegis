# AEGIS — Autonomous Excellence Guardian & Intelligent System

> **"When your data pipeline breaks at 3am, AEGIS fixes it before you even wake up."**

**Hackathon:** AI-Autonomous Reliability Engineer | Data DevOps & MLOps Track  
**Theme:** Self-Healing Data & ML Systems

---

## What problem does this solve?

Every data engineering team has woken up at 3am because a Databricks job failed. The manual process is painful:

1. Find the failed job in Databricks
2. Read the error log
3. Figure out root cause
4. Write a fix
5. Test it
6. Deploy it
7. Verify it works
8. Write an incident report

**AEGIS automates all of that — jobs, ML models, and everything in between.**

---

## What AEGIS is capable of

### Job Self-Healing

- Connects to your real Databricks workspace via the SDK
- Lists all available jobs and lets you select which ones to monitor (single / multiple / all)
- Reads the actual error from the failed Databricks run (not predefined patterns)
- Fetches the actual notebook source code from Databricks
- Sends the real error + real code to GPT-5.5, which deep-scans the notebook, identifies every bug, and returns a fully fixed version
- Validates the fix (Python syntax check + lint + PEP8 auto-format) before uploading
- Uploads the fixed notebook back to Databricks and re-runs the job to verify
- If the re-run still fails: extracts the new error, retries the fix up to 3 times — each time feeding the latest error back to GPT-5.5
- If the fix still fails after 3 retries: rolls back the notebook to its original version and escalates to a human
- If the re-run passes: creates a GitHub PR with the fixed code, waits for your approval, then triggers CD to deploy

### ML Model Monitoring & Auto-Retraining (opt-in)

At startup, AEGIS asks if you want to monitor ML models. If you say yes:

- Queries your MLflow registry for all registered Production models
- Checks accuracy drop vs baseline and PSI (Population Stability Index) for data drift
- If a model is degraded: triggers the `[AEGIS ML] Model Retraining Pipeline` job in Databricks
- Polls the retraining run until it completes
- Compares new model accuracy against the old Production version in MLflow
- If accuracy improved by ≥ 0.5%: promotes the new version to Production stage
- If accuracy did not improve: keeps the existing model and notifies you
- Falls back to simulation if MLflow is not configured (useful for demos)

### Email Notifications (8 stages, non-blocking)

AEGIS sends an email at every stage so you always know what's happening:

| Stage | Trigger | What's in it |
|-------|---------|--------------|
| 1. Initial Health Check | Startup | Full job status table with icons + ML model health (if opted in) |
| 2. Failure Alert | Job failure detected | Incident ID, job name, error summary, RCA with confidence score |
| 3. Fix In Progress | GPT-5.5 repair started | Which notebook is being fixed, incident ID |
| 4. Fix Complete | Job passed post-fix run | Fixed files, MTTR (time-to-repair) |
| 5. PR Raised | GitHub PR created | PR URL, what was changed, what to review |
| 6. Final Confirmation | Post-deploy health passed | Full end-to-end summary |
| 7. Deployment Failed | Post-deploy job still failing | Escalation to human with details |
| 8. Escalation | RCA confidence < 70% or max retries exceeded | Root cause, confidence %, what to investigate |
| ML Healing Complete | Model retrained + promoted | Old vs new accuracy, improvement |
| ML Healing Failed | Retraining did not improve model | Why model was not promoted |

### Guardrails (safety mechanisms)

| Guardrail | What it does |
|-----------|-------------|
| Confidence Gate | If RCA confidence < 70%, AEGIS escalates to human instead of auto-fixing |
| Syntax Check | Fixed code must pass `ast.parse()` before uploading |
| Lint Check | Pyflakes lint run on every fix |
| PEP8 Auto-Format | Code auto-formatted before upload |
| Diff Review | If LLM returns identical code (no changes), it's flagged |
| Rollback | If post-fix run fails, original notebook is restored immediately |
| Rate Limiter | Prevents AEGIS from re-triggering the same job too many times |
| PR#0 Guard | Never polls GitHub if PR creation failed |

---

## Full workflow (step by step)

```
You run AEGIS
    │
    ├── Lists all Databricks jobs (real SDK call)
    ├── You select: single job / multiple jobs / all
    ├── You choose: monitor ML models? (y/n)
    │
    ▼
STATUS CHECK (real Databricks API)
    ├── Checks latest run for each selected job
    ├── Checks MLflow models (if opted in)
    ▼
EMAIL #1 — Initial Health Check
    (job status table + model health)
    │
    ├── All healthy → END
    ├── ML drift detected → ML HEALER → END
    └── Job failure detected ↓
    │
    ▼
RCA — Root Cause Analysis (GPT-5.5)
    ├── Assembles context: real error logs + past incidents + pipeline activity
    ├── GPT-5.5 reasons across all signals → root cause + confidence score
    ├── Confidence < 70% → EMAIL (escalation) → END
    └── Confidence ≥ 70% ↓
    │
    ▼
EMAIL #2 — Failure Alert (RCA details)
    ▼
EMAIL #3 — Fix In Progress
    ▼
JOB FIXER — GPT-5.5 Notebook Repair
    ├── Discovers Databricks environment (catalogs, tables)
    ├── Fetches past similar incidents from ChromaDB
    ├── Fetches real notebook source code from Databricks
    ├── Sends: actual error + actual code + context → GPT-5.5
    ├── GPT-5.5 identifies ALL bugs, returns fixed code
    ├── Syntax check + lint + PEP8 format
    ├── Uploads fixed notebook to Databricks
    ├── Triggers re-run, polls until terminal state
    ├── Re-run PASSED → continue
    └── Re-run FAILED → extract new error → retry (max 3x) → rollback if exhausted
    │
    ▼
EMAIL #4 — Fix Complete
    ▼
GITHUB PR — Created with fixed code
    ▼
EMAIL #5 — PR Raised (awaiting review)
    ▼
PR WAIT — Polls GitHub until merged or closed
    │
    ├── Closed without merge → END
    └── Merged ↓
    │
    ▼
CD — GitHub Actions deploys Databricks bundle
    ▼
POST-DEPLOY CHECK — Re-runs health check on job
    │
    ├── Healthy → EMAIL #6 (Final Confirmation) → INCIDENT REPORT → END
    └── Still failing → EMAIL #7 (Deployment Failed) → INCIDENT REPORT → END
```

---

## ML Healing workflow (when drift detected)

```
ML monitoring opted in → MLflow queried for Production models
    │
    └── Degraded model found (accuracy drop > 5% or PSI > 0.20)
         ▼
    MLHealerAgent finds "[AEGIS ML] Model Retraining Pipeline" job in Databricks
         ▼
    Triggers Databricks job run (passes model_name as parameter)
         ▼
    Polls run until SUCCESS / FAILED
         │
         ├── Run FAILED → EMAIL (ml_healing_failed) → done
         └── Run SUCCESS ↓
              ▼
         Fetches new model metrics from MLflow
              ▼
         Compares new accuracy vs old Production accuracy
              │
              ├── Improved ≥ 0.5% → Promotes new version to Production → EMAIL (ml_healing_complete)
              └── Not improved → Keeps old model → EMAIL (ml_healing_failed with reason)
```

---

## Project structure

```
aegis/
├── src/
│   ├── workflow.py               # LangGraph 16-node state machine (main orchestrator)
│   ├── agents/
│   │   ├── status_checker.py     # Real Databricks SDK job health check
│   │   ├── job_fixer.py          # GPT-5.5 notebook repair (fetch → fix → upload → verify)
│   │   ├── ml_healer.py          # Autonomous ML retraining + model promotion
│   │   ├── model_monitor.py      # MLflow model drift detection
│   │   ├── mail_sender.py        # 8-stage email notifications (Gmail SMTP)
│   │   ├── pr_manager.py         # GitHub PR creation and polling
│   │   └── deployment.py         # CD trigger via GitHub Actions
│   ├── diagnosis/
│   │   ├── rca_agent.py          # GPT-5.5 root cause analysis
│   │   └── context_assembler.py  # Assembles real error logs + pipeline activity
│   ├── knowledge/
│   │   └── incident_store.py     # ChromaDB vector store of past incidents
│   ├── guardrails/
│   │   ├── audit_log.py          # Full audit trail of every action
│   │   ├── rate_limiter.py       # Prevents runaway fix loops
│   │   └── validators.py         # Syntax check, lint, PEP8 format
│   ├── reporting/
│   │   └── incident_report.py    # Structured JSON incident report generator
│   └── models.py                 # Shared data models (AEGISState, RCAResult, etc.)
├── de_project/
│   ├── databricks.yml            # Databricks Asset Bundle config
│   ├── notebooks/
│   │   ├── failing_notebook.py   # Intentionally broken notebook (AEGIS test target)
│   │   └── ml_model_train.py     # ML retraining notebook (GradientBoosting + MLflow)
│   └── resources/jobs/
│       ├── failing_job.yml       # Databricks job for failing_notebook
│       └── ml_job.yml            # Databricks job for ml_model_train
├── demo/
│   └── production_multi_agent.py # Main entry point
├── config/
│   └── config.yaml               # Thresholds, job-to-git path mapping, MLflow URI
├── .github/workflows/
│   ├── ci.yml                    # Lint + bundle validate on PRs (skips failing_notebook)
│   └── cd.yml                    # Deploy to Databricks on merge (destroy requires DESTROY input)
└── .env                          # Credentials (never committed)
```

---

## Setup

### Prerequisites

- Python 3.11
- Databricks workspace with SDK access
- EPAM DIAL API key (for GPT-5.5)
- Gmail account with App Password enabled
- GitHub repo with Actions enabled

### Environment variables (.env)

```bash
# Databricks
DATABRICKS_HOST=https://your-workspace.cloud.databricks.com
DATABRICKS_TOKEN=your-token

# EPAM DIAL / GPT-5.5
DIAL_API_KEY=your-dial-api-key
DIAL_API_ENDPOINT=https://ai-proxy.lab.epam.com
DIAL_DEPLOYMENT=gpt-5.5-2026-04-24
DIAL_API_VERSION=2025-04-01-preview

# Gmail
GMAIL_SENDER=your@gmail.com
GMAIL_APP_PASSWORD=your-app-password
GMAIL_RECIPIENTS=oncall@company.com,team@company.com

# GitHub
GITHUB_TOKEN=your-github-pat
GITHUB_REPO_OWNER=your-org
GITHUB_REPO_NAME=your-repo

# MLflow (optional — AEGIS simulates if not set)
MLFLOW_TRACKING_URI=https://your-mlflow-server
```

### Install and run

```bash
pip install -r requirements.txt
python demo/production_multi_agent.py
```

### Deploy the Databricks test jobs

```bash
cd de_project
databricks bundle deploy --target dev
```

This creates two jobs in your workspace:
- `[AEGIS Test] Data Quality Validation - Failing` — used to demo autonomous job fixing
- `[AEGIS ML] Model Retraining Pipeline` — used for autonomous ML retraining

---

## AI tools used

| Tool | Role |
|------|------|
| GPT-5.5 (via EPAM DIAL) | Root cause analysis + notebook repair |
| LangGraph | 16-node multi-agent state machine orchestration |
| LangChain AzureChatOpenAI | LLM integration |
| MLflow | Model registry + drift metrics |
| ChromaDB | Vector store for past incident memory |
| Databricks SDK | Real job monitoring, notebook fetch/upload, run triggering |
| PyGithub | PR creation and polling |

---

## What makes this different

- **No simulation mode** — every action hits real Databricks APIs
- **Error-driven fixing** — GPT-5.5 reads the actual error from the actual failed run, not predefined patterns
- **End-to-end autonomous** — detect → diagnose → fix → verify → PR → deploy → report, without human intervention (except PR review)
- **ML + Jobs** — monitors both Databricks jobs and MLflow models in one unified loop
- **Safe by design** — rollback, rate limiting, confidence gate, syntax validation all built in
- **Memory** — ChromaDB stores every resolved incident; future fixes are informed by past fixes
