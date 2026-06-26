# AEGIS Multi-Agent Architecture

## Current Agents (6)

### 1. **StatusCheckerAgent** (`src/agents/status_checker.py`)
- **Purpose**: Monitor Databricks job health
- **Methods**: 
  - `check_health()` - Entry point, returns JobHealthReport[]
  - `_check_single_job()` - Monitors one job
  - `_extract_error()` - Fetches error traces from Databricks API
- **Status**: ✅ Working (fixed error extraction bug)

### 2. **MailSenderAgent** (`src/agents/mail_sender.py`)
- **Purpose**: Send 6-stage email notifications
- **Stages**:
  1. `initial_health_check` - Status summary
  2. `failure_alert` - Incident detected
  3. `fix_in_progress` - GPT-5.5 fixing
  4. `fix_complete` - Fix successful
  5. `pr_raised` - PR created, awaiting approval
  6. `deployment_complete` - Deployed and verified
- **Issues**: 
  - ❌ Shows "GPT-4o" instead of "GPT-5.5"
  - ❌ Missing job ID and clear failure details
- **Status**: ⚠️ Needs updates

### 3. **RCAAgent** (`src/diagnosis/rca_agent.py`)
- **Purpose**: Root cause analysis using GPT-5.5
- **Methods**: 
  - `diagnose()` - Analyze incident
  - `_llm_diagnose()` - GPT-5.5 analysis
  - `_rule_based_diagnose()` - Fallback heuristics
- **Status**: ✅ Working (99% confidence)

### 4. **JobFixerAgent** (`src/agents/job_fixer.py`)
- **Purpose**: Fix notebooks using GPT-5.5
- **Methods**:
  - `fix_job()` - Fix all notebooks in a job
  - `_fix_notebook_with_llm()` - GPT-5.5 repair
  - Post-fix verification run
- **Status**: ✅ Working

### 5. **PRManagerAgent** (`src/agents/pr_manager.py`)
- **Purpose**: Create PR and wait for approval
- **Methods**:
  - `create_pr()` - Create branch + commit + PR
  - `wait_for_pr_approval()` - Poll until merged
- **Issues**:
  - ❌ Has 60-minute timeout (should be indefinite)
- **Status**: ⚠️ Needs fix

### 6. **DeploymentAgent** (`src/agents/deployment.py`)
- **Purpose**: Monitor GitHub Actions CD workflow
- **Methods**:
  - `trigger_cd()` - Wait for workflow run
- **Issues**:
  - ❌ Fails with "list index out of range"
  - ❌ No post-deployment health verification
- **Status**: ❌ Broken

---

## Current Workflow (11 Nodes)

```
START
  ↓
1. status_check (StatusCheckerAgent)
  ↓
2. initial_email (MailSenderAgent - stage 1)
  ↓
  [IF FAILURES]
  ↓
3. failure_alert (RCAAgent + MailSenderAgent - stage 2)
  ↓
4. fix_in_progress_email (MailSenderAgent - stage 3)
  ↓
5. job_fixer (JobFixerAgent + post-fix run verification)
  ↓
6. fix_complete_email (MailSenderAgent - stage 4)
  ↓
7. pr_create (PRManagerAgent)
  ↓
8. pr_raised_email (MailSenderAgent - stage 5)
  ↓
9. pr_wait_approval (PRManagerAgent - polls every 60s, 60min timeout)
  ↓
10. deployment (DeploymentAgent - waits for GitHub Actions)
  ↓
11. deployment_complete_email (MailSenderAgent - stage 6)
  ↓
END
```

---

## Missing Features

### ❌ 1. Dynamic Job Selection at Startup
- **Current**: Hardcoded job_id or all jobs
- **Needed**: Interactive job listing from Databricks
- **Implementation**: New `job_selector_node` at start

### ❌ 2. Indefinite PR Approval Wait
- **Current**: 60-minute timeout
- **Needed**: Wait indefinitely until merged/closed
- **Fix**: Remove timeout in `wait_for_pr_approval()`

### ❌ 3. Post-Deployment Health Verification
- **Current**: Assumes deployment succeeds
- **Needed**: Run StatusCheckerAgent again after CD completes
- **Implementation**: New `post_deployment_verification_node`

### ❌ 4. Final Confirmation Email
- **Current**: "deployment_complete" sent even if deployment fails
- **Needed**: Only send if post-deployment health check passes
- **Implementation**: Update stage 6 email logic

### ❌ 5. Deployment Monitoring Fix
- **Current**: `list index out of range` error
- **Root Cause**: No workflow runs found for merge SHA
- **Fix**: Better error handling + wait longer for GitHub Actions to start

---

## Proposed Enhanced Workflow (14 Nodes)

```
START
  ↓
1. [NEW] job_selector (List jobs, let user choose)
  ↓
2. status_check (StatusCheckerAgent)
  ↓
3. initial_email (MailSenderAgent - stage 1)
  ↓
  [IF FAILURES]
  ↓
4. failure_alert (RCAAgent + MailSenderAgent - stage 2)
  ↓
5. fix_in_progress_email (MailSenderAgent - stage 3)
  ↓
6. job_fixer (JobFixerAgent + post-fix run verification)
  ↓
7. fix_complete_email (MailSenderAgent - stage 4)
  ↓
8. pr_create (PRManagerAgent)
  ↓
9. pr_raised_email (MailSenderAgent - stage 5)
  ↓
10. pr_wait_approval (PRManagerAgent - [FIXED] NO TIMEOUT, wait indefinitely)
  ↓
11. deployment (DeploymentAgent - [FIXED] better error handling)
  ↓
12. [NEW] post_deployment_verification (StatusCheckerAgent again)
  ↓
  [IF GREEN]
  ↓
13. deployment_complete_email (MailSenderAgent - stage 6 - [ENHANCED])
  ↓
14. [NEW] final_health_email (Confirmation that everything is green)
  ↓
END
```

---

## Fixes Required

### Fix 1: Update Email Model References
**Files**: `src/agents/mail_sender.py`
- Line 8: "GPT-4o" → "GPT-5.5"
- Line 123: "GPT-4o analysis" → "GPT-5.5 analysis"
- Line 149: "fixed by GPT-4o" → "fixed by GPT-5.5"

### Fix 2: Enhance Email Content
**Files**: `src/agents/mail_sender.py`
- Add job_id to all emails
- Make error messages more prominent
- Add job description/link to Databricks

### Fix 3: Remove PR Approval Timeout
**Files**: `src/agents/pr_manager.py`
- Line 177: Remove `timeout_minutes` parameter
- Line 179-199: Remove timeout check logic
- Wait indefinitely until merged or closed

### Fix 4: Fix Deployment Monitoring
**Files**: `src/agents/deployment.py`
- Better error handling for missing workflow runs
- Wait longer (30s instead of 10s) for GitHub Actions to start
- Poll more frequently

### Fix 5: Add Post-Deployment Verification
**Files**: `src/workflow.py`
- New node: `post_deployment_verification_node`
- Re-run StatusCheckerAgent after CD completes
- Only send final email if health check passes

### Fix 6: Add Dynamic Job Selection
**Files**: `demo/production_multi_agent.py`, `src/workflow.py`
- New node: `job_selector_node`
- List all jobs from Databricks
- Interactive prompt for user selection

---

## Agent Synchronization

### Current State Management
- **Technology**: LangGraph `StateGraph` with `AEGISState` TypedDict
- **State Persistence**: In-memory for single run
- **Agent Communication**: Shared state dictionary passed between nodes

### State Flow
```python
AEGISState = {
    # Input
    "workspace_host": str,
    "workspace_token": str,
    "specific_job_id": str | None,
    
    # StatusChecker Output
    "job_health_reports": List[Dict],
    "has_failures": bool,
    
    # RCAAgent Output
    "root_cause": str,
    "confidence": float,
    
    # JobFixer Output
    "fix_status": str,
    "fixed_notebooks": List[Dict],
    "post_fix_run_id": int,
    
    # PRManager Output
    "pr_number": int,
    "pr_url": str,
    "merge_sha": str,
    
    # DeploymentAgent Output
    "deployment_status": str,
    "workflow_run_url": str,
    
    # Metrics
    "mttr_seconds": float,
}
```

### Inter-Agent Dependencies
1. **StatusChecker** → **RCAAgent**: Provides error traces
2. **RCAAgent** → **JobFixer**: Provides root cause for targeted fix
3. **JobFixer** → **PRManager**: Provides fixed notebooks to commit
4. **PRManager** → **DeploymentAgent**: Provides merge SHA to track
5. **DeploymentAgent** → **StatusChecker** (post-deploy): Verify fix worked

---

## Summary

**Working Agents**: 4/6 (StatusChecker, RCAAgent, JobFixer, MailSender)  
**Broken Agents**: 2/6 (PRManager timeout, DeploymentAgent error)  
**Missing Nodes**: 3 (job_selector, post_deployment_verification, final_health_email)  
**Current Nodes**: 11  
**Proposed Nodes**: 14
