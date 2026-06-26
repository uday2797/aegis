# AEGIS — Complete Code Explanation

> This document explains every file, class, and design decision in AEGIS
> so any team member can understand, extend, or present the code confidently.

**⭐ NEW: Multi-Agent Architecture** — AEGIS now uses **LangGraph** to orchestrate 5 specialized agents in a state machine workflow. See the [Multi-Agent Architecture](MULTI_AGENT_ARCHITECTURE.md) doc for full details.

---

## Quick Navigation

**Multi-Agent System (New)**:
- [`src/agents/status_checker.py`](#multi-agent-1-statuschecker) — Health monitoring
- [`src/agents/mail_sender.py`](#multi-agent-2-mailsender) — 6-stage email notifications
- [`src/agents/job_fixer.py`](#multi-agent-3-jobfixer) — LLM notebook repair
- [`src/agents/pr_manager.py`](#multi-agent-4-prmanager) — PR creation & approval polling
- [`src/agents/deployment.py`](#multi-agent-5-deployment) — CD automation
- [`src/workflow.py`](#langgraph-orchestration) — LangGraph state machine

**Original Components (Legacy)**:
- [`src/models.py`](#1-srcmodelspy) — Shared data contracts
- [`src/detection/failure_detector.py`](#2-srcdetectionfailure_detectorpy) — Eyes of AEGIS
- [`src/diagnosis/rca_agent.py`](#3-srcdiagnosisrca_agentpy) — LLM brain
- [`src/healing/heal_orchestrator.py`](#4-srchealingheal_orchestratorpy) — Self-healing actions
- [`src/reporting/incident_reporter.py`](#5-srcreportingincident_reporterpy) — Notifications & reports

---

## Multi-Agent System

### Multi-Agent #1: StatusChecker

**File:** `src/agents/status_checker.py`

**Purpose:** Monitors Databricks jobs and reports health status.

**Key Features:**
- Discover all jobs in workspace or filter by DAB bundle tag
- Monitor specific job by ID
- Extract error traces from failed task runs
- Return structured `JobHealthReport[]`

**Usage:**
```python
agent = StatusCheckerAgent(host, token)
reports = await agent.check_health(
    monitor_all_jobs=True,
    dab_bundle_name="aegis-de-project"
)
```

**Output:**
```python
[{
    "job_id": "470575380114552",
    "job_name": "[AEGIS] Data Processing Pipeline",
    "status": "failed",
    "error_summary": "ModuleNotFoundError: pandsa",
    "failed_tasks": ["validate"]
}]
```

---

### Multi-Agent #2: MailSender

**File:** `src/agents/mail_sender.py`

**Purpose:** 6-stage email notifications (non-blocking).

**Key Features:**
- Non-blocking SMTP sends via `asyncio.to_thread()`
- HTML email templates with color-coded status
- Retry logic (2 attempts, 30s timeout)

**6 Notification Stages:**
1. `initial_health_check` — All good or failures detected
2. `failure_alert` — Error trace + GPT-4o RCA
3. `fix_in_progress` — Notebook repair started
4. `fix_complete` — Job fixed, MTTR
5. `pr_raised` — PR created, awaiting approval
6. `deployment_complete` — CD finished, all healthy

**Usage:**
```python
agent = MailSenderAgent()
await agent.send_stage("fix_complete", {
    "incident_id": "INC-ABC123",
    "post_fix_run_id": 123456,
    "mttr_seconds": 90
})
```

---

### Multi-Agent #3: JobFixer

**File:** `src/agents/job_fixer.py`

**Purpose:** LLM-powered autonomous notebook repair.

**Key Features:**
- Fetch notebook source from Databricks
- Call GPT-4o with error + code → fixed code
- Upload fixed notebook to Databricks
- Trigger job run and verify success

**Flow:**
```python
agent = JobFixerAgent(host, token, config)
result = await agent.fix_job(
    job_id=470575380114552,
    error_summary="ModuleNotFoundError: pandsa",
    incident_id="INC-ABC123"
)
# Returns: {"status": "success", "fixed_notebooks": [...], "post_fix_run_id": 123}
```

**GPT-4o Integration:**
- Uses EPAM DIAL API (Azure OpenAI proxy)
- Temperature=0 for deterministic fixes
- Strips markdown code fences from response

---

### Multi-Agent #4: PRManager

**File:** `src/agents/pr_manager.py`

**Purpose:** GitHub PR creation and approval polling.

**Key Features:**
- Create branch: `aegis-hotfix/{incident_id}`
- Commit fixed notebooks to git repo
- Create PR with AI-generated description
- **Poll PR status** every 60s until merged or rejected (max 60 min)

**Usage:**
```python
agent = PRManagerAgent()
result = await agent.create_pr(
    incident_id="INC-ABC123",
    fixed_notebooks=[...],
    root_cause="Typo in import statement"
)
# Returns: {"pr_url": "...", "pr_number": 1}

# Wait for approval
approval = await agent.wait_for_pr_approval(pr_number=1, timeout_minutes=60)
# Returns: {"merged": True, "sha": "abc123"}
```

---

### Multi-Agent #5: Deployment

**File:** `src/agents/deployment.py`

**Purpose:** GitHub Actions CD automation.

**Key Features:**
- Wait for CD workflow run triggered by merge commit
- Poll workflow status until completion (max 10 min)
- Return workflow run URL and conclusion

**Usage:**
```python
agent = DeploymentAgent()
result = await agent.trigger_cd(merge_sha="abc123")
# Returns: {"workflow_run_url": "...", "status": "success"}
```

---

### LangGraph Orchestration

**File:** `src/workflow.py`

**Purpose:** State machine workflow that orchestrates all 5 agents.

**Key Components:**
- `AEGISState` TypedDict — global state shared across agents
- 11 workflow nodes (status_check, initial_email, failure_alert, ...)
- 3 conditional routing functions
- `build_aegis_workflow()` — builds the LangGraph compiled graph

**Conditional Edges:**
- After `initial_email`: If failures → `failure_alert`, else → END
- After `job_fixer`: If success → `fix_complete_email`, else → escalate
- After `pr_wait_approval`: If merged → `deployment`, else → escalate

**Entry Point:**
```bash
python demo/production_multi_agent.py
```

---

## Original Components (Legacy)

### 1. `src/models.py` — Shared Data Contracts

**Purpose:** All data structures that flow between components. Think of these as the "language" that AEGIS components speak to each other.

### Key Classes

| Class | What It Represents |
|---|---|
| `FailureType` | Enum of all incident categories AEGIS can handle |
| `RiskLevel` | LOW / MEDIUM / HIGH — drives policy decisions |
| `DetectedIncident` | Raw incident data: job name, logs, metrics, timestamp |
| `RCAResult` | LLM analysis output: root cause, confidence, recommended action |
| `HealResult` | What healing was done and what happened |
| `IncidentReport` | Final report: timeline, MTTR, cause, fix, prevention |

**Why this matters for the demo:** Judges can see the data flowing cleanly from detection → diagnosis → healing → report. No magic, no black boxes.

---

## 2. `src/detection/failure_detector.py` — Eyes of AEGIS

**Purpose:** Continuously polls for failures across jobs, data, and models.

### Design Decisions

- **Simulation mode** (`SIMULATION_MODE=true`) — injects realistic failures without needing a real Databricks cluster. Critical for hackathon demo reliability.
- **Production mode** (`SIMULATION_MODE=false`) — polls real Databricks Jobs API using the official SDK.
- **`inject_failure()`** — the demo's "failure injection" API. Demo scripts call this to trigger a specific failure type for the live presentation.

### What It Detects (per `config.yaml`)

```
null_threshold_pct: 5.0     → alert if nulls > 5% in any critical column
volume_drop_threshold_pct: 20.0  → alert if row count drops > 20%
psi_threshold: 0.2          → alert if model prediction drift PSI > 0.20
sla_breach multiplier: 3.0  → alert if job takes 3x longer than P95 runtime
```

### Log Simulation

The `_generate_realistic_logs()` method produces real-looking Spark/Databricks error messages for each failure type. This makes the demo believable without real production errors.

---

## 3. `src/diagnosis/context_assembler.py` — Information Gatherer

**Purpose:** Before the LLM reasons about a failure, it needs all relevant context assembled in one place.

### What It Gathers

1. Raw error logs and summary from the incident
2. Upstream job statuses (which jobs feed this one)
3. Affected downstream tables
4. Current metrics (null %, row count, PSI score)
5. Recent schema/config changes (from Delta table history in production)
6. Similar past incidents retrieved from the knowledge store

**Why this is important:** LLM accuracy is directly proportional to context quality. A senior engineer investigating an incident would gather all of this before forming a hypothesis — AEGIS does the same.

---

## 4. `src/diagnosis/rca_agent.py` — The AI Brain

**Purpose:** LLM-powered root cause analysis. This is the most impressive component for judges.

### How the LLM Prompt Works

The prompt gives GPT-4o:
- A role: "You are a senior data reliability engineer"
- All context: logs, metrics, lineage, recent changes, similar incidents
- A structured output requirement: JSON with root_cause, confidence, risk_level, etc.

This is **not** pattern matching. The LLM reasons across multiple signals simultaneously — exactly like a human SRE would.

### Confidence Score (0-100%)

- High confidence (85%+): AEGIS is sure about root cause → auto-heal approved
- Medium confidence (60-85%): Some uncertainty → only low-risk auto-heal allowed
- Low confidence (<60%): Too uncertain → always escalate to human

### Fallback RCA

If Azure OpenAI is unavailable (no credentials, no internet), `_rule_based_diagnose()` provides deterministic answers for known failure types. This ensures the demo never breaks.

---

## 5. `src/healing/policy_engine.py` — The Safety Gate

**Purpose:** Decides whether AEGIS can act autonomously or must ask a human first.

### Decision Logic

```
confidence < 60%     → ALWAYS escalate (not sure enough)
risk = HIGH          → ALWAYS escalate (too dangerous)
risk = MEDIUM + confidence >= 85%  → auto-heal approved
risk = LOW   + confidence >= 60%   → auto-heal approved
```

**Why this is the most important component for judge trust:** Without this, AEGIS is just an AI that acts on everything, which is dangerous. With it, AEGIS demonstrates **governed autonomy** — the gold standard for production AI systems.

---

## 6. `src/healing/heal_orchestrator.py` — The Hands of AEGIS

**Purpose:** Executes the actual healing action for each failure type.

### Healing Actions

| Failure Type | Action | What It Does |
|---|---|---|
| `transient_failure` | `RetryWithBackoff` | Retries job up to 3 times with 30s intervals |
| `upstream_delay` | `WaitAndRetrigger` | Monitors upstream, retriggers when ready |
| `data_corruption` | `DeltaRollback` | Rolls Delta table back to last good version |
| `schema_drift` | `SchemaAdaptation` | Generates SQL column mapping patch |
| `model_drift` | `ModelRollback + Retrain` | Switches to stable model, queues retraining |
| `data_quality` | `QuarantineAndBackfill` | Isolates bad partition, triggers data backfill |

All actions are **idempotent** (safe to run multiple times) and produce detailed outcome strings for the incident report.

---

## 7. `src/reporting/teams_notifier.py` — Voice of AEGIS

**Purpose:** Sends Microsoft Teams Adaptive Card with the full incident context.

### What the Card Shows

- Incident ID, job name, detection time, MTTR
- Root cause, confidence %, risk level
- Action taken and outcome
- Prevention recommendation
- Link to hotfix PR (if code fix was generated)

**Fallback:** If no webhook is configured, prints a beautiful Rich-formatted table to the terminal (perfect for demo).

---

## 8. `src/reporting/pr_creator.py` — Code Fix Publisher

**Purpose:** Creates GitHub pull requests for AI-generated code/config fixes.

### PR Contents

- Branch: `aegis-hotfix/{failure_type}/{incident_id}`
- Title: `[AEGIS Auto-Fix] {root cause}`
- Body: root cause, explanation, risk assessment, files changed, prevention recommendation
- Labels: `aegis-auto-fix`, `reliability`

In simulation mode, logs a fake PR URL but all content is generated. In production mode, creates a real PR using PyGithub.

---

## 9. `src/knowledge/incident_store.py` — Memory of AEGIS

**Purpose:** Stores every resolved incident as a vector embedding. Retrieved during RCA to show the LLM similar past failures and their fixes.

### How It Works

1. When an incident is resolved, AEGIS stores a document: `job + failure type + root cause + action taken + outcome`
2. When a new incident comes in, AEGIS queries the store for top-5 semantically similar past incidents
3. These are included in the LLM RCA prompt → LLM can say "this is like incident INC-001A, which was fixed by..."

**Storage:** ChromaDB (persistent vector DB). Falls back to in-memory list if ChromaDB isn't available.

---

## 10. `src/main.py` — The Orchestrator

**Purpose:** Ties all components together and runs the main event loop.

### `run_once()` — one full loop

```
1. Poll for incident (detector)
2. Assemble context (assembler)
3. Run RCA (rca_agent)
4. Apply policy gate (policy_engine)
5. Execute healing OR escalate (heal_orchestrator)
6. Generate report + send Teams + create PR (reporter)
```

### `run_continuous()` — production polling loop

Calls `run_once()` every `poll_interval_seconds` (default: 30s). Runs until interrupted.

---

## 11. `demo/run_demo.py` — The Presentation Script

**Purpose:** Interactive demo for the hackathon presentation.

### Flow

1. Shows AEGIS banner
2. Presents 3 scenarios with descriptions
3. User presses Enter to inject each failure
4. AEGIS heals it live on screen
5. Final summary: incidents handled, auto-heal rate, MTTR comparison

### 3 Demo Scenarios

| # | Failure | Risk | Healing |
|---|---|---|---|
| 1 | Schema Drift | MEDIUM | Schema patch + GitHub PR |
| 2 | Data Corruption | LOW | Delta rollback + retrigger |
| 3 | Transient Failure | LOW | Retry with backoff |

---

## Design Principles

1. **Modular** — each component is independent and testable
2. **Fallback-safe** — every component works without external dependencies (simulation/fallback mode)
3. **Governed** — no action without policy approval, all actions logged with audit trail
4. **Explainable** — every decision produces human-readable reasoning (confidence, risk, explanation)
5. **Extensible** — add a new failure type by: adding a `FailureType` enum value + a healing action method + a rule in the fallback RCA map

---

## Extending AEGIS

### Add a New Failure Type

1. Add to `FailureType` enum in `models.py`
2. Add log simulation in `failure_detector.py` → `_generate_realistic_logs()`
3. Add rule-based RCA in `rca_agent.py` → `_rule_based_diagnose()` rules dict
4. Add healing action in `heal_orchestrator.py` → `action_map` + new method
5. Add to `policy.yaml` risk category

### Add Slack Notifications

1. Add `SLACK_WEBHOOK_URL` to `.env`
2. Create `src/reporting/slack_notifier.py` (same interface as `TeamsNotifier`)
3. Wire into `IncidentReporter.report()`
