# AEGIS — Autonomous Excellence Guardian & Intelligent System

> **"When your data pipeline breaks at 3am, AEGIS fixes it before you even wake up."**

**Hackathon:** AI-Autonomous Reliability Engineer | Data DevOps & MLOps Track  
**Theme:** Self-Healing Data & ML Systems

[![Tests](https://img.shields.io/badge/tests-94%20passed-brightgreen)](#testing)
[![Guardrails](https://img.shields.io/badge/guardrails-7%20layers-blue)](#guardrails--safety-layers)
[![LLM](https://img.shields.io/badge/LLM-GPT--5.5%20%7C%20GPT--4o-orange)](#ai-tools-used)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](#setup)

---

## The Problem

Every data engineering team has woken up at 3am because a Databricks job failed. The manual process is painful:

| Step | Time cost |
|---|---|
| 1. Spot the alert | 5–15 min |
| 2. Find the failed job & read the log | 10–20 min |
| 3. Understand the root cause | 20–60 min |
| 4. Write, test, and deploy a fix | 30–90 min |
| 5. Verify the job passes | 10–20 min |
| 6. Write the incident report | 15–30 min |
| **Total MTTR** | **1.5–4 hours** |

**AEGIS compresses that entire loop to under 5 minutes — autonomously, for jobs and ML models.**

---

## What AEGIS Does

### Job Self-Healing

- Connects to your real Databricks workspace via the SDK
- Lists all available jobs; you select which ones to monitor (single / multiple / all)
- Reads the **actual error** from the failed Databricks run — not predefined patterns
- Fetches the **actual notebook source** from Databricks
- Sends the full Python traceback + real notebook source to **GPT-5.5**, which makes the **minimum surgical change** required to fix the specific error — logic, variable names, and structure are never touched
- Validates the fix (syntax check + lint) before uploading — invalid Python is hard-blocked and never uploaded
- Uploads the fixed notebook, re-runs the job, and monitors to completion
- If re-run fails: extracts the **full error trace** from that run, rolls back to original, retries up to **3 times**, each time feeding GPT-5.5 the latest real error
- If all 3 retries fail: **rolls back** the notebook to the original version and escalates to a human
- If re-run passes: creates a **GitHub PR**, waits for approval, then triggers CD to deploy

### ML Model Monitoring & Auto-Retraining (opt-in)

At startup, AEGIS asks if you want to monitor ML models. If yes:

- Queries your MLflow registry for all registered Production models
- Checks **accuracy drop vs baseline** and **PSI** (Population Stability Index) for data drift
- If a model is degraded: triggers the `[AEGIS ML] Model Retraining Pipeline` job in Databricks
- Polls until retraining completes, then compares new model accuracy against the old version in MLflow
- Accuracy improved ≥ 0.5% → promotes new version to Production stage
- No improvement → keeps existing model and notifies you
- Falls back to simulation if MLflow is not configured

### Email Notifications — 10 stages, non-blocking

AEGIS sends an email at every stage of the lifecycle:

| Stage | Trigger | Content |
|---|---|---|
| 1. Initial Health Check | Startup | Job status table + ML model health |
| 2. Failure Alert | Job failure detected | Incident ID, RCA, confidence score |
| 3. Fix In Progress | GPT-5.5 repair started | Notebook being fixed, incident ID |
| 4. Fix Complete | Job passed post-fix run | Fixed files, MTTR |
| 5. PR Raised | GitHub PR created | PR URL, what changed, what to review |
| 6. Final Confirmation | Post-deploy health passed | End-to-end summary |
| 7. Deployment Failed | Post-deploy job still failing | Escalation details |
| 8. Escalation | Confidence < 70% or max retries hit | Root cause, confidence %, next steps |
| 9. ML Healing Complete | Model retrained + promoted | Old vs new accuracy |
| 10. ML Healing Failed | Retraining did not improve model | Why model was not promoted |

---

## Guardrails — 7 Safety Layers

AEGIS is built to be **autonomous but safe**. Seven independent guardrails protect every action:

| # | Guardrail | What it does | Where |
|---|---|---|---|
| 1 | **Confidence Gate** | If RCA confidence < 70%, AEGIS escalates instead of auto-fixing | `workflow.py`, `policy_engine.py` |
| 2 | **Diff Review** | If LLM returns identical code (zero changes), it is flagged and logged | `guardrails/validators.py` |
| 3 | **Rollback** | If post-fix run fails, original notebook is restored immediately | `agents/job_fixer.py` |
| 4 | **Syntax + Lint Check** | Fixed code must pass `compile()` syntax check (hard block) + pyflakes lint (warning) before uploading | `guardrails/validators.py` |
| 5 | **Rate Limiter** | Sliding-window cap: max 5 trigger runs per job per 10 minutes | `guardrails/rate_limiter.py` |
| 6 | **Audit Log** | Every autonomous action written to an append-only JSONL file | `guardrails/audit_log.py` |
| 7 | **Prompt Injection Guard** | Untrusted error logs and notebook code are truncated and scanned for injection patterns before LLM calls; every system message includes an injection-resistance instruction | `guardrails/prompt_guard.py` |

---

## Full Autonomous Workflow (15 nodes)

```
You run AEGIS
    │
    ├── [Node 0]  Job Selector — lists all Databricks jobs, you pick which to monitor
    ├── [Node 1]  Status Check — real Databricks SDK health poll
    ├── [Node 2]  Email #1 — Initial Health Check (job status + model health)
    │
    ├── All healthy → END
    ├── ML drift detected → [Node 3] ML Monitor → [Node 4] ML Healer → Email → END
    └── Job failure detected ↓
    │
    ▼
[Node 5] RCA (GPT-4o)
    ├── Assembles: real error logs + past incidents (ChromaDB) + pipeline activity
    ├── GPT-4o reasons across all signals → root cause + confidence score
    ├── Confidence < 70% → Email (escalation) → END
    └── Confidence ≥ 70% ↓
    │
[Node 6] Email #2 — Failure Alert
[Node 7] Email #3 — Fix In Progress
    │
    ▼
[Node 8] Job Fixer (GPT-5.5)
    ├── Discovers Databricks environment (catalogs, schemas)
    ├── Fetches similar past incidents from ChromaDB as reference
    ├── Fetches real notebook source from Databricks
    ├── Surgical targeted fix — GPT-5.5 changes ONLY the lines the error points to
    │     (no refactoring, no renames, no style changes, no logic rewrites)
    ├── Guardrails: Syntax hard-block ✓ → Lint check ✓ → Diff logged ✓
    ├── Uploads fixed notebook → triggers re-run → polls to terminal state
    ├── Re-run PASSED → continue
    └── Re-run FAILED → extract full error trace → rollback → retry (max 3x) → escalate if exhausted
    │
[Node 9]  Email #4 — Fix Complete
[Node 10] PR Manager — creates GitHub hotfix PR
[Node 11] Email #5 — PR Raised (awaiting review)
[Node 12] PR Wait — polls GitHub until merged
    │
    ▼
[Node 13] Deployment Agent — triggers GitHub Actions CD, polls status
    │
[Node 14] Post-Deploy Health Check
    ├── Healthy → Email #6 (Final Confirmation) → Incident Report → END
    └── Still failing → Email #7 (Deployment Failed) → Incident Report → END
```

> **Architecture reference:** See [docs/architecture.md](docs/architecture.md) for full Mermaid diagrams covering the 15-node workflow, component map, sequence diagram, and guardrail decision tree.

---

## ML Healing Workflow

```
ML monitoring opted in → MLflow queried for Production models
    │
    └── Degraded model found (accuracy drop > 5% OR PSI > 0.20)
         ▼
    MLHealerAgent finds "[AEGIS ML] Model Retraining Pipeline" in Databricks
         ▼
    Triggers Databricks job (passes model_name as parameter)
         ▼
    Polls run until SUCCESS / FAILED
         │
         ├── FAILED → Email (ml_healing_failed) → END
         └── SUCCESS ↓
              ▼
         Fetches new model metrics from MLflow
              ▼
         Compares new accuracy vs old Production accuracy
              │
              ├── Improved ≥ 0.5% → Promotes to Production → Email (ml_healing_complete)
              └── Not improved → Keeps old model → Email (ml_healing_failed with reason)
```

---

## Testing

AEGIS ships with a complete test suite — **103 tests, 0 failures**:

```bash
python -m pytest tests/ -q
```

| Test file | What it covers |
|---|---|
| `test_policy_engine.py` | All 4 confidence/risk decision branches |
| `test_validators.py` | Syntax check, lint, diff, autoformat, Databricks magic stripping |
| `test_rate_limiter.py` | Sliding window, check/record, job isolation, window expiry |
| `test_audit_log.py` | Append-only JSONL, UTC timestamps, `read_recent()` |
| `test_prompt_guard.py` | 8 injection payload patterns, truncation, system message hardening |
| `test_rca_agent.py` | Rule-based fallback, mocked LLM path, JSON parsing, injection resilience |
| `test_heal_orchestrator.py` | All 7 failure types routed correctly in simulation mode |
| `test_incident_store.py` | Store/retrieve cycle, ChromaDB fallback to in-memory |
| `test_integration_smoke.py` | End-to-end simulation: all 5 failure types (DE + ML) through full pipeline with field-level assertions |

Tests are also run automatically on every pull request via **GitHub Actions** (`ci.yml`).

---

## Project Structure

```
aegis/
├── src/
│   ├── workflow.py               # LangGraph 15-node multi-agent state machine
│   ├── main.py                   # AEGISOrchestrator (simulation/demo loop)
│   ├── models.py                 # Shared data models (dataclasses + enums)
│   ├── agents/
│   │   ├── status_checker.py     # Databricks SDK job health polling
│   │   ├── job_fixer.py          # GPT-5.5 notebook repair (5-phase autonomous)
│   │   ├── ml_healer.py          # Autonomous ML retraining + model promotion
│   │   ├── model_monitor.py      # MLflow accuracy + PSI drift detection
│   │   ├── mail_sender.py        # 10-stage Gmail SMTP notifications
│   │   ├── pr_manager.py         # GitHub PR creation and merge polling
│   │   └── deployment.py         # GitHub Actions CD trigger + monitoring
│   ├── diagnosis/
│   │   ├── rca_agent.py          # GPT-4o root cause analysis (JSON output)
│   │   └── context_assembler.py  # Multi-signal context builder
│   ├── detection/
│   │   └── failure_detector.py   # Simulation + production failure detector
│   ├── healing/
│   │   ├── heal_orchestrator.py  # Failure-type → action routing
│   │   └── policy_engine.py      # Confidence + risk governance gate
│   ├── guardrails/
│   │   ├── prompt_guard.py       # Prompt injection defence (Guardrail #7)
│   │   ├── validators.py         # Syntax / lint / diff / PEP8 (Guardrails #2, #4)
│   │   ├── rate_limiter.py       # Sliding-window trigger throttle (Guardrail #5)
│   │   └── audit_log.py          # Append-only action log (Guardrail #6)
│   ├── knowledge/
│   │   └── incident_store.py     # ChromaDB vector store for past incidents
│   └── reporting/
│       ├── incident_report.py    # Structured incident report generator
│       ├── gmail_notifier.py     # HTML email builder
│       ├── pr_creator.py         # GitHub PR body builder
│       └── teams_notifier.py     # Teams webhook sender
├── de_project/                   # Databricks Asset Bundle (DAB)
│   ├── databricks.yml
│   ├── notebooks/
│   │   ├── failing_notebook.py   # Intentionally broken notebook (AEGIS test target)
│   │   ├── 01_ingest.py          # Sample ingest notebook
│   │   ├── 02_transform.py       # Sample transform notebook
│   │   └── ml_model_train.py     # ML retraining notebook (GradientBoosting + MLflow)
│   └── resources/jobs/
│       ├── data_pipeline.yml     # Databricks job for full pipeline
│       ├── failing_job.yml       # Databricks job for failing_notebook
│       └── ml_job.yml            # Databricks job for ML retraining
├── tests/                        # Complete test suite (103 tests)
│   ├── conftest.py
│   ├── test_policy_engine.py
│   ├── test_validators.py
│   ├── test_rate_limiter.py
│   ├── test_audit_log.py
│   ├── test_prompt_guard.py
│   ├── test_rca_agent.py
│   ├── test_heal_orchestrator.py
│   ├── test_incident_store.py
│   └── test_integration_smoke.py
├── docs/
│   └── architecture.md           # Mermaid diagrams: workflow, components, sequence, guardrails
├── demo/
│   ├── production_multi_agent.py # Full production entry point
│   ├── production_run.py         # Single-run demo
│   └── quick_test.py             # 5-failure-type smoke test
├── config/
│   └── config.yaml               # Thresholds, drift config, notebook-to-git path mapping
├── .github/workflows/
│   ├── ci.yml                    # Tests + lint + DAB validate on PRs
│   └── cd.yml                    # Deploy to Databricks on merge to master
├── .env.example                  # Environment variable template
├── docker-compose.yml
└── requirements.txt
```

---

## Setup

### Prerequisites

- Python 3.11+
- Databricks workspace with SDK access
- EPAM DIAL API key (for GPT-4o / GPT-5.5)
- Gmail account with App Password enabled
- GitHub repo with Actions enabled

### 1. Clone and install

```bash
git clone https://github.com/your-org/aegis.git
cd aegis
pip install -r requirements.txt
```

### 2. Configure environment variables

Copy `.env.example` to `.env` and fill in your values:

```bash
# EPAM DIAL API (Azure OpenAI-compatible proxy)
DIAL_API_KEY=your-dial-api-key
DIAL_API_ENDPOINT=https://ai-proxy.lab.epam.com
DIAL_DEPLOYMENT=gpt-4o
DIAL_API_VERSION=2025-04-01-preview

# Databricks
DATABRICKS_HOST=https://your-workspace.azuredatabricks.net
DATABRICKS_TOKEN=your-databricks-token

# Your Databricks user email — resolves notebook paths in config.yaml
DATABRICKS_USER_EMAIL=you@company.com

# Gmail notifications
GMAIL_SENDER=your@gmail.com
GMAIL_APP_PASSWORD=your-16-char-app-password
GMAIL_RECIPIENTS=oncall@company.com,team@company.com

# GitHub PR creation
GITHUB_TOKEN=your-github-pat
GITHUB_REPO_OWNER=your-org
GITHUB_REPO_NAME=your-repo

# MLflow (optional — AEGIS simulates if not set)
MLFLOW_TRACKING_URI=https://your-mlflow-server

# AEGIS mode
SIMULATION_MODE=false   # true = use simulated data (demo), false = real Databricks
```

> **Note on `DATABRICKS_USER_EMAIL`:** `config.yaml` uses `${DATABRICKS_USER_EMAIL}` placeholders for notebook path mapping. Setting this env var is all that is needed — no personal email in committed files.

### 3. Deploy the Databricks test jobs

```bash
cd de_project
databricks bundle deploy --target dev
```

This creates two jobs in your Databricks workspace:
- **`[AEGIS Test] Failing Data Pipeline`** — intentionally broken notebook AEGIS will fix autonomously
- **`[AEGIS ML] Model Retraining Pipeline`** — triggered automatically if ML drift is detected

### 4. Run AEGIS

```bash
python demo/production_multi_agent.py
```

AEGIS will:
1. List all jobs in your workspace
2. Let you choose which job(s) to monitor
3. Ask if you want ML model monitoring
4. Run the full autonomous healing loop

### 5. Run tests

```bash
python -m pytest tests/ -q
```

---

## AI Tools Used

| Tool | Where used | Purpose |
|---|---|---|
| **GPT-4o** (via EPAM DIAL) | `src/diagnosis/rca_agent.py` | Root cause analysis — structured JSON output with confidence score |
| **GPT-5.5** (via EPAM DIAL) | `src/agents/job_fixer.py` | Surgical targeted fix — repairs only the lines that caused the failure; logic and structure never changed |
| **LangChain** (`AzureChatOpenAI`) | `rca_agent.py`, `job_fixer.py` | LLM integration layer |
| **LangGraph** | `src/workflow.py` | 15-node async multi-agent state machine orchestrating the healing lifecycle |
| **MLflow** | `model_monitor.py`, `ml_healer.py`, `ml_model_train.py` | Model registry, drift metrics, version promotion |
| **ChromaDB** | `src/knowledge/incident_store.py` | Vector store — persists resolved incidents; similar past cases fed to GPT-5.5 as context |
| **Databricks SDK** | `status_checker.py`, `job_fixer.py`, `ml_healer.py` | Job monitoring, notebook fetch/upload, run triggering |
| **PyGithub** | `src/agents/pr_manager.py`, `deployment.py` | PR creation, merge polling, CD workflow triggering |
| **scikit-learn** | `de_project/notebooks/ml_model_train.py` | GradientBoosting model training in the retraining pipeline |

---

## What Makes This Different

| Capability | AEGIS | Typical on-call alert tool |
|---|---|---|
| Root cause analysis | GPT-4o reads the real error log | Pattern matching on known errors |
| Code repair | GPT-5.5 makes the minimum surgical change to fix the error — business logic is never altered | Manual fix required |
| Verification | Uploads fix and re-runs the job | No automated verification |
| Retry loop | Up to 3 retries with the new error each time | Single attempt |
| Rollback | Automatic if post-fix run fails | Manual rollback |
| ML monitoring | PSI + accuracy drift detection | Job alerts only |
| Deployment | Auto-creates PR → CD on merge | Manual deployment |
| Memory | ChromaDB stores every resolved incident; future fixes are informed by past fixes | No institutional memory |
| Safety | 7 independent guardrails including prompt injection defence | None |
| Audit trail | Every action in append-only JSONL | Alert logs only |
