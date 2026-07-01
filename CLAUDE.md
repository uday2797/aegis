# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run full test suite
python -m pytest tests/ -q

# Run a single test file
python -m pytest tests/test_validators.py -v

# Run a single test by name
python -m pytest tests/test_policy_engine.py -k "test_auto_heal_low_risk" -v

# Run all tests except the integration smoke test (what CI does)
python -m pytest tests/ -v --tb=short --ignore=tests/test_integration_smoke.py

# Lint notebooks (skip failing_notebook.py — intentionally broken)
python -m pyflakes de_project/notebooks/01_ingest.py
python -m pyflakes de_project/notebooks/02_transform.py

# Run the production multi-agent demo (requires .env)
python demo/production_multi_agent.py

# Validate the Databricks Asset Bundle before deploying
cd de_project && databricks bundle validate
```

**Do not run `databricks bundle deploy` directly from the CLI.** All deployments must go through the GitHub Actions CD pipeline (`cd.yml`). This is enforced by policy — see the comment at the top of `.github/workflows/cd.yml`.

## Architecture

### Two entry points, one canonical repair path

**Production path** (`demo/production_multi_agent.py` → `src/workflow.py`): A 15-node LangGraph `StateGraph` that drives the full autonomous lifecycle interactively. This is the primary entry point for demos and production use.

**Simulation/legacy path** (`src/main.py` → `AEGISOrchestrator`): A continuous polling loop used for simulation demos with injected failures. Uses the same underlying agents but orchestrates them imperatively rather than through LangGraph.

Both paths delegate notebook repair to `JobFixerAgent`. All healing logic lives there; the `HealOrchestrator._fix_notebook_and_retry` in the legacy path just calls `JobFixerAgent.fix_job`.

### LangGraph state machine (`src/workflow.py`)

`AEGISState` is a `TypedDict` shared across all 15 nodes. The graph flow:

```
job_selector → status_check → initial_email
  → [failures?] → failure_alert (RCA runs here, confidence gate at 70%)
    → fix_in_progress_email → job_fixer → fix_complete_email
    → pr_create → pr_raised_email → pr_wait_approval (indefinite poll)
    → deployment → post_deployment_verification
    → final_confirmation_email / deployment_failed_email → incident_report → END
  → [ML drift?] → ml_healer → incident_report → END
  → [healthy] → END
```

**Routing is exclusive:** `route_after_initial_email` sends a run down the DE fix path OR the ML heal path, never both. The healthy path skips `incident_report` entirely — this is intentional (no incident = no report).

`failure_alert_node` is where RCA runs and the confidence gate lives. If `rca.confidence < 70`, `fix_status` is set to `"escalated"` and `route_after_rca` routes straight to `incident_report`, skipping the fixer.

### ML monitoring path (`src/agents/model_monitor.py` + `src/agents/ml_healer.py`)

`ModelMonitorAgent.check_models()` queries MLflow for Production model versions and injects synthetic drift metrics. By default, `sales_forecast_v3` has a 35% random chance of appearing degraded. Set `AEGIS_FORCE_ML_DRIFT=true` to make it always trigger (demo use).

`MLHealerAgent.heal()` flow:
1. Looks up `healing.ml_retraining_job_name` in config (`[AEGIS ML] Model Retraining Pipeline`) by name in Databricks
2. Triggers the job, passes `model_name` as a parameter
3. Polls `_wait_for_run()` until terminal state — capped at `MAX_POLLS = 240` (2 hours)
4. Fetches new model version metrics from MLflow; handles `None` if MLflow unavailable
5. If `new_accuracy - old_accuracy >= 0.005`: archives all current Production versions (loop variable captured by value to avoid closure bug), registers new version as Production
6. Sends `ml_healing_complete` or `ml_healing_failed` email

The retraining notebook (`de_project/notebooks/ml_model_train.py`) falls back to 10k synthetic rows if the configured Delta feature table is not found — so the demo works without a real feature table.

**Databricks ML one-time setup:** Before `MLHealerAgent` can compare and promote, a baseline Production model must exist. Run `[AEGIS ML] Model Retraining Pipeline` once manually in the Databricks UI, then promote the registered version to Production in the MLflow registry.

### JobFixerAgent — surgical repair philosophy (`src/agents/job_fixer.py`)

The GPT-5.5 prompt is deliberately **surgical**: fix only the lines the error points to, never refactor, never rename, never add type hints or style changes. The system message frames the model as "a surgical code repair tool", not a developer. This constraint is critical — changing it back to "fix all bugs + PEP8 clean" causes the model to rewrite entire notebooks.

Fix pipeline per notebook:
1. `_comprehensive_scan_and_fix` → GPT-5.5 targeted fix
2. `validate_python_code` → `compile()` hard block (invalid Python never uploaded)
3. `lint_python_code` → pyflakes warning only (non-blocking)
4. `compute_diff` → logged to audit trail
5. Upload via Databricks SDK `workspace.import_`
6. Re-run job and poll; on failure → `_extract_run_error` (uses `get_run_output` for full traceback) → rollback → recursive retry (max 3)

### Rate limiter (`src/guardrails/rate_limiter.py`)

`RateLimiter.check_and_record()` is the atomic method to use — it checks and records in a single call to prevent TOCTOU races. `check()` + `record_trigger()` called separately is a bug pattern; use `check_and_record()` instead.

### Guardrails (`src/guardrails/`)

Seven independent layers that run in sequence during every fix:

| # | File | Purpose |
|---|---|---|
| 1 | `workflow.py` | Confidence gate — escalate if RCA < 70% |
| 2 | `validators.py:compute_diff` | Flag if LLM returns identical code |
| 3 | `job_fixer.py` | Rollback to original on post-fix run failure |
| 4 | `validators.py:validate_python_code` | Hard-block invalid Python before upload |
| 4b | `validators.py:lint_python_code` | pyflakes static analysis (warning) |
| 5 | `rate_limiter.py` | Sliding-window cap: 5 triggers per job per 10 min |
| 6 | `audit_log.py` | Append-only JSONL record of every autonomous action |
| 7 | `prompt_guard.py` | Truncate + scan inputs for injection before LLM calls |

### Config and path mapping (`config/config.yaml`)

`config.yaml` uses `${DATABRICKS_USER_EMAIL}` placeholders. `load_config()` in both `main.py` and `production_multi_agent.py` expands these via `os.path.expandvars` at load time — set `DATABRICKS_USER_EMAIL` in `.env` so notebook paths resolve correctly.

The `databricks_to_git_path` block maps Databricks workspace paths → git repo paths for PR commits. `JobFixerAgent._map_to_git_path` tries exact match, then without `.py` suffix, then basename match, then falls back to the task key slug.

### Knowledge store (`src/knowledge/incident_store.py`)

ChromaDB with a custom lightweight keyword-hash embedding (no model download). Falls back to in-memory keyword search if ChromaDB is unavailable. Resolved incidents are stored here and retrieved as context for the RCA agent and job fixer on future similar failures. Data persists to `./data/knowledge_store/`.

### Databricks Asset Bundle (`de_project/`)

`de_project/notebooks/failing_notebook.py` is **intentionally broken** — it is the AEGIS demo target that AEGIS autonomously detects and repairs. CI lint skips it explicitly. Do not fix it.

## Tests

All tests run with `SIMULATION_MODE=true` and fake Databricks credentials (set in `conftest.py`) — no real API calls are made. The `conftest.py` `config` fixture loads the real `config/config.yaml` with env-var expansion so tests match production config.

`test_integration_smoke.py` is excluded from CI (`--ignore`) but can be run locally. It exercises all 5 failure types end-to-end through the full pipeline.

## Environment variables

Required for production run: `DIAL_API_KEY`, `DATABRICKS_HOST`, `DATABRICKS_TOKEN`, `DATABRICKS_USER_EMAIL`. See `.env.example` for the full list.

| Variable | Default | Purpose |
|---|---|---|
| `DIAL_DEPLOYMENT` | `gpt-5.5-2026-04-24` | Model for `JobFixerAgent` (surgical notebook repair) |
| `DIAL_RCA_DEPLOYMENT` | `gpt-4o` | Model for `RCAAgent` (structured JSON root cause analysis) |
| `DATABRICKS_USER_EMAIL` | — | Expands `${DATABRICKS_USER_EMAIL}` placeholders in `config.yaml` notebook paths |
| `MLFLOW_TRACKING_URI` | `databricks` | Set to `databricks` to use Databricks-managed MLflow (no separate server); uses `DATABRICKS_HOST` + `DATABRICKS_TOKEN` |
| `AEGIS_FORCE_ML_DRIFT` | `false` | Set `true` to guarantee `ModelMonitorAgent` reports `sales_forecast_v3` as degraded — for demo runs; overrides the 35% random roll |
| `SIMULATION_MODE` | `false` | Set `true` in tests to skip real API calls; `conftest.py` sets this automatically |

**`DIAL_DEPLOYMENT` vs `DIAL_RCA_DEPLOYMENT` are intentionally different.** GPT-5.5 for repair, GPT-4o for RCA. Do not unify them — different tasks need different model characteristics.

**`RCAAgent` config keys** (`rca.model`, `rca.temperature`) are overridden by `DIAL_RCA_DEPLOYMENT` env var at runtime. Config values are fallback defaults only.

## Intentional design decisions (not bugs)

- **Healthy path skips `incident_report`**: `route_after_initial_email` has a `"healthy"` edge that goes directly to END. No incident, no report. This is intentional.
- **Different models for fixer vs RCA**: `DIAL_DEPLOYMENT` and `DIAL_RCA_DEPLOYMENT` are separate env vars by design. Do not merge them.
- **`failing_notebook.py` is broken intentionally**: Do not fix it — it is the demo target AEGIS repairs. CI lint explicitly skips it.
