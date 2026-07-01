# AEGIS — System Architecture

> **AI-Engine for Guardian Intelligence & Self-healing**  
> Hackathon Track: Self-Healing Data & ML Systems | AI-Autonomous Reliability Engineer

---

## Overview

AEGIS is a fully autonomous reliability system for Databricks-based Data & ML pipelines. It implements a closed-loop **DETECT → DIAGNOSE → DECIDE → HEAL → REPORT** cycle using a 15-node LangGraph multi-agent workflow.

---

## 15-Node LangGraph Workflow

```mermaid
flowchart TD
    START([▶ START]) --> N0

    N0["🎛️  Node 0\nJob Selector\n— interactive job/ML selection —"]
    N1["📡  Node 1\nStatus Checker\n— real Databricks SDK health poll —"]
    N2{"🔀  Router\nall healthy?"}
    N3["📧  Node 2\nEmail: Initial Health Check\n— job status table + model health —"]
    N4["🤖  Node 3\nML Model Monitor\n— MLflow PSI + accuracy drift —"]
    N5{"🔀  Router\nML drift?"}
    N6["🔧  Node 4\nML Healer\n— trigger Databricks retraining job —"]
    N7["📧  Node 5\nEmail: ML Healing Result\n— promoted / not improved —"]
    N8["🔍  Node 6\nRCA Agent (GPT-4o)\n— error logs + context → root cause + confidence —"]
    N9{"🔀  Router\nconfidence ≥ 70%?"}
    N10["⚠️  Node 7\nEscalation Email\n— RCA confidence too low —"]
    N11["📧  Node 8\nEmail: Failure Alert\n— RCA details, confidence score —"]
    N12["📧  Node 9\nEmail: Fix In Progress\n— notebook repair started —"]
    N13["🛠️  Node 10\nJob Fixer (GPT-5.5)\n— fetch → scan → fix → upload → verify —\n↺ up to 3 retries with rollback"]
    N14{"🔀  Router\nfix succeeded?"}
    N15["📧  Node 11\nEmail: Fix Complete\n— MTTR, fixed files —"]
    N16["🐙  Node 12\nPR Manager\n— create GitHub PR, wait for merge —"]
    N17["📧  Node 13\nEmail: PR Raised\n— PR URL, what to review —"]
    N18["🚀  Node 14\nDeployment Agent\n— trigger GitHub Actions CD, poll status —"]
    N19{"🔀  Router\npost-deploy healthy?"}
    N20["📧  Node 15\nEmail: Final Confirmation\n— end-to-end summary —"]
    N21["📧  Email: Deployment Failed\n— escalate to human —"]
    DONE([⏹ END])

    START --> N0
    N0 --> N1
    N1 --> N2
    N2 -- "✅ all healthy" --> N3
    N3 --> DONE
    N2 -- "⚠️ failures present" --> N4
    N4 --> N5
    N5 -- "🔴 drift detected" --> N6
    N6 --> N7
    N7 --> DONE
    N5 -- "✅ models healthy" --> N8
    N8 --> N9
    N9 -- "❌ confidence < 70%" --> N10
    N10 --> DONE
    N9 -- "✅ confidence ≥ 70%" --> N11
    N11 --> N12
    N12 --> N13
    N13 --> N14
    N14 -- "✅ fix succeeded" --> N15
    N15 --> N16
    N16 --> N17
    N17 --> N18
    N18 --> N19
    N19 -- "✅ healthy" --> N20
    N20 --> DONE
    N19 -- "❌ still failing" --> N21
    N21 --> DONE
    N14 -- "❌ fix failed\n(max retries exceeded)" --> N10
```

---

## Component Map

```mermaid
graph LR
    subgraph Guardrails["🛡️ Guardrails (7 Safety Layers)"]
        G1["#1 Confidence Gate\n70% threshold"]
        G2["#2 Diff Review\nno-change detection"]
        G3["#3 Rollback\noriginal notebook restored"]
        G4["#4 Syntax Check\nast.parse + pyflakes"]
        G5["#5 Rate Limiter\nsliding window per job"]
        G6["#6 Audit Log\nappend-only JSONL"]
        G7["#7 Prompt Guard\ninjection detection + truncation"]
    end

    subgraph Agents["🤖 Agent Layer"]
        A1[StatusCheckerAgent]
        A2[RCAAgent / GPT-4o]
        A3[JobFixerAgent / GPT-5.5]
        A4[PRManagerAgent]
        A5[DeploymentAgent]
        A6[ModelMonitorAgent]
        A7[MLHealerAgent]
        A8[MailSenderAgent]
    end

    subgraph Storage["💾 Storage"]
        S1[ChromaDB\nVector Knowledge Store]
        S2[JSONL Audit Log]
        S3[Databricks Workspace\nNotebooks + Jobs]
        S4[MLflow Registry]
        S5[GitHub Repo + Actions]
    end

    subgraph Detection["🔭 Detection"]
        D1[FailureDetector\nDatabricks SDK poll]
        D2[ModelMonitor\nPSI + accuracy drop]
    end

    D1 --> A1
    D2 --> A6
    A2 --> S1
    A3 --> S3
    A3 --> Guardrails
    A4 --> S5
    A5 --> S5
    A6 --> S4
    A7 --> S4
    A8 --> |"8 email stages"| Agents
    A2 --> S1
```

---

## Data Flow: Full Autonomous Healing Cycle

```mermaid
sequenceDiagram
    participant User
    participant AEGIS as AEGIS Orchestrator
    participant DB as Databricks SDK
    participant GPT as GPT-4o / 5.5
    participant GH as GitHub
    participant Email as Gmail SMTP

    User->>AEGIS: python -m src.workflow
    AEGIS->>User: Show job list (tabulate)
    User->>AEGIS: Select job(s) + ML opt-in

    AEGIS->>DB: jobs.list_runs() — health check
    DB-->>AEGIS: run states + error logs
    AEGIS->>Email: Email #1 — Initial Health Check

    alt Job failure detected
        AEGIS->>DB: workspace.export(notebook)
        DB-->>AEGIS: notebook source code
        AEGIS->>GPT: error + code → RCA JSON
        GPT-->>AEGIS: root_cause + confidence + risk
        AEGIS->>Email: Email #2 — Failure Alert

        alt confidence ≥ 70%
            AEGIS->>Email: Email #3 — Fix In Progress
            AEGIS->>GPT: deep scan + comprehensive fix
            GPT-->>AEGIS: fixed notebook code
            Note over AEGIS: Guardrails: syntax✓ lint✓ diff✓ pep8✓
            AEGIS->>DB: workspace.import_ (upload fix)
            AEGIS->>DB: jobs.run_now()
            DB-->>AEGIS: run result

            alt run SUCCESS
                AEGIS->>Email: Email #4 — Fix Complete
                AEGIS->>GH: create PR (hotfix branch)
                AEGIS->>Email: Email #5 — PR Raised
                GH-->>AEGIS: PR merged
                AEGIS->>GH: trigger CD workflow
                AEGIS->>Email: Email #6 — Final Confirmation
            else run FAILED (retry ≤ 3)
                AEGIS->>DB: rollback notebook
                AEGIS->>GPT: retry with new error
            else max retries exceeded
                AEGIS->>Email: Email — Escalation
            end
        else confidence < 70%
            AEGIS->>Email: Email — Escalation (low confidence)
        end
    end
```

---

## Guardrail Decision Tree

```mermaid
flowchart TD
    A[LLM returns fixed code] --> B{Code non-empty?\n≥ 50 chars}
    B -- No --> FAIL1[❌ Reject — empty output]
    B -- Yes --> C{ast.parse\nsyntax check}
    C -- Fail --> FAIL2[❌ Reject — SyntaxError]
    C -- Pass --> D{pyflakes\nlint check}
    D -- Issues --> WARN[⚠️ Log warning\nnon-blocking]
    D -- Clean --> E[autopep8\nformat]
    WARN --> E
    E --> F{compute_diff\nany changes?}
    F -- No diff --> WARN2[⚠️ Log — LLM returned\nidentical code]
    F -- Changed --> G{Rate Limiter\ncheck}
    WARN2 --> G
    G -- Blocked --> FAIL3[❌ Rate limit exceeded]
    G -- Allowed --> H[Upload to Databricks\nrecord in AuditLog]
    H --> I{Post-fix run\nresult}
    I -- SUCCESS --> DONE[✅ Auto-healed]
    I -- FAILED --> J{retry_attempt\n< max_retries?}
    J -- Yes --> K[Extract new error\nRollback notebook\nRetry fix]
    K --> A
    J -- No --> ESC[⚠️ Escalate to human\nRollback notebook]
```

---

## Technology Stack

| Layer | Technology |
|---|---|
| **Orchestration** | LangGraph (15-node async state machine) |
| **LLM (RCA)** | GPT-4o via EPAM DIAL (Azure OpenAI proxy) |
| **LLM (Code Fix)** | GPT-5.5 via EPAM DIAL |
| **Pipeline Platform** | Databricks SDK + DAB (Databricks Asset Bundles) |
| **ML Registry** | MLflow |
| **Vector Store** | ChromaDB (persistent, lightweight embeddings) |
| **CI/CD** | GitHub Actions (ci.yml + cd.yml) |
| **Notifications** | Gmail SMTP (8 lifecycle stages) |
| **Teams** | Microsoft Teams Webhook |
| **Config** | YAML + python-dotenv (env-var expansion) |
| **Validation** | pyflakes + autopep8 + ast.parse |
| **Audit** | Append-only JSONL |
| **Testing** | pytest + pytest-asyncio |

---

## Security Architecture

| Guardrail | Mechanism | Where |
|---|---|---|
| Confidence Gate | Blocks auto-heal if RCA confidence < 70% | `workflow.py`, `policy_engine.py` |
| Prompt Injection Guard | Truncation + pattern detection + injection-resistant system message | `guardrails/prompt_guard.py` |
| Code Syntax Validation | `ast.parse` + `compile()` before upload | `guardrails/validators.py` |
| Lint Gate | pyflakes static analysis | `guardrails/validators.py` |
| Diff Check | Rejects identical code (no-op LLM output) | `guardrails/validators.py` |
| Rate Limiter | Max 5 triggers / 10 min per job (sliding window) | `guardrails/rate_limiter.py` |
| Rollback | Original notebook restored on post-fix failure | `agents/job_fixer.py` |
| Audit Log | Every action recorded to immutable JSONL | `guardrails/audit_log.py` |
| Env-var secrets | No credentials in source — `.env` only | `.env.example`, `config.yaml` |

---

## Directory Structure

```
aegis/
├── src/
│   ├── main.py                  # AEGISOrchestrator (legacy event loop)
│   ├── workflow.py              # LangGraph 15-node multi-agent workflow
│   ├── models.py                # Shared data models (dataclasses + enums)
│   ├── agents/
│   │   ├── status_checker.py    # Databricks job health polling
│   │   ├── job_fixer.py         # GPT-5.5 notebook repair (5-phase)
│   │   ├── pr_manager.py        # GitHub PR creation + merge polling
│   │   ├── deployment.py        # GitHub Actions CD trigger + monitoring
│   │   ├── mail_sender.py       # 8-stage Gmail notifications
│   │   ├── model_monitor.py     # MLflow PSI + accuracy drift detection
│   │   └── ml_healer.py         # Autonomous retraining + promotion
│   ├── diagnosis/
│   │   ├── rca_agent.py         # GPT-4o root cause analysis
│   │   └── context_assembler.py # Multi-signal context gathering
│   ├── detection/
│   │   └── failure_detector.py  # Simulation + production detector
│   ├── healing/
│   │   ├── heal_orchestrator.py # Failure-type → action routing
│   │   └── policy_engine.py     # Confidence + risk gate
│   ├── guardrails/
│   │   ├── prompt_guard.py      # Prompt injection defence (Guardrail #7)
│   │   ├── validators.py        # Syntax / lint / diff / format (Guardrails #2, #4)
│   │   ├── rate_limiter.py      # Sliding-window trigger throttle (Guardrail #5)
│   │   └── audit_log.py         # Append-only action log (Guardrail #6)
│   ├── knowledge/
│   │   └── incident_store.py    # ChromaDB vector store for past incidents
│   └── reporting/
│       ├── incident_report.py   # Structured report generation
│       ├── incident_reporter.py # IncidentReporter facade
│       ├── gmail_notifier.py    # HTML email builder
│       ├── pr_creator.py        # GitHub PR body builder
│       └── teams_notifier.py    # Teams webhook
├── de_project/                  # Databricks Asset Bundle
│   ├── databricks.yml
│   ├── notebooks/               # Sample + intentionally broken notebooks
│   └── resources/jobs/          # Job definitions (YAML)
├── tests/                       # Full test suite
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
├── config/config.yaml           # Runtime config (env-var expanded)
├── .env.example                 # Environment variable template
├── .github/workflows/
│   ├── ci.yml                   # Lint notebooks + validate DAB bundle
│   └── cd.yml                   # Deploy to Databricks on PR merge
└── docker-compose.yml           # Container config
```
