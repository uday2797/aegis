"""
AEGIS Live Production Dashboard
Real-time multi-agent workflow monitoring with comprehensive analytics
Version: 2.0 (15-Node Workflow with Dynamic Job Selection)
"""
import streamlit as st
import asyncio
import os
import time
import threading
from datetime import datetime, timedelta
from dotenv import load_dotenv
import yaml
from typing import Dict, List
import plotly.graph_objects as go
import plotly.express as px
from pathlib import Path
import sys
from io import StringIO
from contextlib import redirect_stdout
from databricks.sdk import WorkspaceClient

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Import AEGIS components
from src.workflow import build_aegis_workflow, AEGISState
from src.agents.status_checker import StatusCheckerAgent

load_dotenv()

# ═══════════════════════════════════════════════════════════════════════════
# PAGE CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="AEGIS Live Dashboard",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ═══════════════════════════════════════════════════════════════════════════
# CUSTOM CSS - LIGHT THEME, VISUALLY RICH
# ═══════════════════════════════════════════════════════════════════════════

st.markdown("""
<style>
    /* Main background gradient */
    .stApp {
        background: linear-gradient(135deg, #f0f4f8 0%, #d9e2ec 50%, #bcccdc 100%);
    }
    
    /* Main title styling */
    .main-title {
        font-size: 3.5rem;
        font-weight: 900;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        padding: 1rem 0;
        text-shadow: 2px 2px 8px rgba(0,0,0,0.1);
        animation: fadeIn 1s ease-in;
    }
    
    /* Subtitle */
    .subtitle {
        text-align: center;
        color: #334e68;
        font-size: 1.2rem;
        margin-bottom: 2rem;
        font-weight: 500;
    }
    
    /* Stage indicators */
    .stage-active {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 1rem 1.5rem;
        border-radius: 0.8rem;
        font-weight: bold;
        box-shadow: 0 6px 12px rgba(102, 126, 234, 0.4);
        animation: pulse 2s infinite;
        text-align: center;
        margin: 0.5rem 0;
    }
    
    .stage-complete {
        background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
        color: white;
        padding: 1rem 1.5rem;
        border-radius: 0.8rem;
        font-weight: bold;
        box-shadow: 0 4px 8px rgba(17, 153, 142, 0.3);
        text-align: center;
        margin: 0.5rem 0;
    }
    
    .stage-pending {
        background: #f7fafc;
        color: #718096;
        padding: 1rem 1.5rem;
        border-radius: 0.8rem;
        border: 2px dashed #cbd5e0;
        text-align: center;
        margin: 0.5rem 0;
    }
    
    .stage-failed {
        background: linear-gradient(135deg, #eb3349 0%, #f45c43 100%);
        color: white;
        padding: 1rem 1.5rem;
        border-radius: 0.8rem;
        font-weight: bold;
        box-shadow: 0 4px 8px rgba(235, 51, 73, 0.3);
        text-align: center;
        margin: 0.5rem 0;
    }
    
    /* Metric cards */
    .metric-card {
        background: white;
        padding: 1.5rem;
        border-radius: 1rem;
        box-shadow: 0 4px 12px rgba(0,0,0,0.08);
        border-left: 4px solid #667eea;
        transition: transform 0.2s ease;
    }
    
    .metric-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 16px rgba(0,0,0,0.12);
    }
    
    /* Log entries */
    .log-entry {
        background: white;
        padding: 0.8rem 1rem;
        margin: 0.3rem 0;
        border-radius: 0.5rem;
        border-left: 4px solid #4299e1;
        font-family: 'Courier New', monospace;
        font-size: 0.9rem;
        color: #2d3748;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    
    .log-info {
        border-left-color: #4299e1;
    }
    
    .log-success {
        border-left-color: #48bb78;
    }
    
    .log-warning {
        border-left-color: #ed8936;
    }
    
    .log-error {
        border-left-color: #f56565;
    }
    
    /* Progress bar custom */
    .stProgress > div > div > div > div {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
    }
    
    /* Buttons */
    .stButton > button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border-radius: 0.8rem;
        padding: 0.8rem 2rem;
        font-weight: 600;
        border: none;
        box-shadow: 0 4px 8px rgba(102, 126, 234, 0.3);
        transition: all 0.3s ease;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 12px rgba(102, 126, 234, 0.4);
    }
    
    /* Info boxes */
    .info-box {
        background: white;
        padding: 1.5rem;
        border-radius: 1rem;
        box-shadow: 0 4px 12px rgba(0,0,0,0.08);
        margin: 1rem 0;
    }
    
    /* URL links */
    .url-link {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 0.6rem 1.2rem;
        border-radius: 0.6rem;
        text-decoration: none;
        display: inline-block;
        font-weight: 600;
        box-shadow: 0 2px 6px rgba(102, 126, 234, 0.3);
        transition: all 0.3s ease;
    }
    
    .url-link:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 10px rgba(102, 126, 234, 0.4);
    }
    
    /* Animations */
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(-20px); }
        to { opacity: 1; transform: translateY(0); }
    }
    
    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.8; }
    }
    
    /* Tab styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 1rem;
    }
    
    .stTabs [data-baseweb="tab"] {
        background: white;
        border-radius: 0.8rem;
        padding: 0.8rem 1.5rem;
        font-weight: 600;
        color: #4a5568;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
    }
    
    /* Sidebar */
    .css-1d391kg {
        background: white;
    }
</style>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════
# LOAD CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════

@st.cache_resource
def load_config():
    with open("config/config.yaml", "r") as f:
        return yaml.safe_load(f)

config = load_config()

# ═══════════════════════════════════════════════════════════════════════════
# SESSION STATE INITIALIZATION
# ═══════════════════════════════════════════════════════════════════════════

if "workflow_running" not in st.session_state:
    st.session_state.workflow_running = False
if "workflow_logs" not in st.session_state:
    st.session_state.workflow_logs = []
if "workflow_state" not in st.session_state:
    st.session_state.workflow_state = None
if "current_node" not in st.session_state:
    st.session_state.current_node = None
if "completed_nodes" not in st.session_state:
    st.session_state.completed_nodes = []
if "start_time" not in st.session_state:
    st.session_state.start_time = None
if "incidents_history" not in st.session_state:
    st.session_state.incidents_history = []
if "available_jobs" not in st.session_state:
    st.session_state.available_jobs = []
if "selected_job_ids" not in st.session_state:
    st.session_state.selected_job_ids = []  # Multiple jobs
if "monitored_jobs_status" not in st.session_state:
    st.session_state.monitored_jobs_status = {}  # {job_id: latest_status_dict}
if "pr_url" not in st.session_state:
    st.session_state.pr_url = None
if "workflow_run_url" not in st.session_state:
    st.session_state.workflow_run_url = None
if "job_run_url" not in st.session_state:
    st.session_state.job_run_url = None
if "mttr_seconds" not in st.session_state:
    st.session_state.mttr_seconds = 0
if "email_count" not in st.session_state:
    st.session_state.email_count = 0
if "last_run_result" not in st.session_state:
    st.session_state.last_run_result = None  # dict with outcome summary
if "workflow_completed_at" not in st.session_state:
    st.session_state.workflow_completed_at = None  # time.time() when finished
if "job_health_reports" not in st.session_state:
    st.session_state.job_health_reports = []

# ═══════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

def add_log(message: str, level: str = "info"):
    """Add log entry with timestamp and level"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    st.session_state.workflow_logs.append({
        "timestamp": timestamp,
        "message": message,
        "level": level
    })
    # Keep only last 100 logs
    if len(st.session_state.workflow_logs) > 100:
        st.session_state.workflow_logs = st.session_state.workflow_logs[-100:]

def fetch_databricks_jobs():
    """Fetch all available Databricks jobs with latest status"""
    try:
        client = WorkspaceClient(
            host=os.getenv("DATABRICKS_HOST"),
            token=os.getenv("DATABRICKS_TOKEN")
        )
        jobs = []
        for job in client.jobs.list():
            # Get latest run status
            runs = list(client.jobs.list_runs(job_id=job.job_id, limit=1))
            latest_run = runs[0] if runs else None
            
            if latest_run:
                status = latest_run.state.life_cycle_state.value
                result_state = latest_run.state.result_state.value if latest_run.state.result_state else "UNKNOWN"
                run_id = latest_run.run_id
            else:
                status = "UNKNOWN"
                result_state = "UNKNOWN"
                run_id = None
            
            jobs.append({
                "job_id": job.job_id,
                "name": job.settings.name,
                "tasks": len(job.settings.tasks) if job.settings.tasks else 0,
                "status": status,
                "result_state": result_state,
                "run_id": run_id,
                "is_failed": result_state in ["FAILED", "TIMEDOUT", "CANCELED"],
            })
        return jobs
    except Exception as e:
        add_log(f"Error fetching jobs: {str(e)}", "error")
        return []

def get_elapsed_time():
    """Get elapsed time since workflow start"""
    if st.session_state.start_time:
        elapsed = time.time() - st.session_state.start_time
        return f"{int(elapsed)}s"
    return "0s"

def run_aegis_workflow_thread(selected_job_ids: list):
    """Run AEGIS workflow in background thread for selected jobs"""
    try:
        add_log(f"🚀 Initializing AEGIS workflow for {len(selected_job_ids)} job(s)...", "info")
        st.session_state.start_time = time.time()
        st.session_state.current_node = "job_selector"
        st.session_state.completed_nodes = []
        
        # Determine monitoring mode
        if len(selected_job_ids) == 1:
            specific_job_id = selected_job_ids[0]
            monitor_all = False
        else:
            specific_job_id = None
            monitor_all = True
        
        # Build workflow
        workflow = build_aegis_workflow()
        workflow_app = workflow.compile()
        
        # Initial state
        initial_state: AEGISState = {
            "workspace_host": os.getenv("DATABRICKS_HOST"),
            "workspace_token": os.getenv("DATABRICKS_TOKEN"),
            "monitor_all_jobs": monitor_all,
            "specific_job_id": specific_job_id,
            "dab_bundle_name": config.get("dab_bundle_name"),
            "config": config,
            "job_health_reports": [],
            "has_failures": False,
            "healthy_count": 0,
            "failed_count": 0,
            "current_incident_id": None,
            "current_job_id": None,
            "current_job_name": None,
            "current_error_summary": None,
            "root_cause": None,
            "confidence": 0.0,
            "risk_level": "unknown",
            "fix_status": None,
            "fixed_notebooks": [],
            "post_fix_run_id": None,
            "mttr_seconds": 0.0,
            "pr_url": None,
            "pr_number": 0,
            "pr_merged": False,
            "merge_sha": None,
            "workflow_run_url": None,
            "deployment_status": None,
            "post_deployment_healthy": False,
            "emails_sent": [],
            "available_jobs": st.session_state.available_jobs,
            "user_selected_job_id": ",".join(map(str, selected_job_ids)) if len(selected_job_ids) > 1 else str(selected_job_ids[0]),
        }
        
        add_log(f"✅ Workflow initialized. Monitoring: {', '.join(map(str, selected_job_ids))}", "success")
        
        final_state = {}
        
        # Execute workflow with node tracking
        for state_update in workflow_app.stream(initial_state):
            if state_update:
                node_name = list(state_update.keys())[0]
                st.session_state.current_node = node_name
                
                if node_name not in st.session_state.completed_nodes:
                    st.session_state.completed_nodes.append(node_name)
                
                # Extract state data
                node_state = state_update[node_name]
                final_state = node_state  # always keep the last
                
                # Rich per-node logging
                if node_name == "job_selector":
                    add_log(f"🔍 [job_selector] Fetching Databricks jobs...", "info")
                elif node_name == "status_check":
                    healthy = node_state.get("healthy_count", 0)
                    failed = node_state.get("failed_count", 0)
                    add_log(f"📊 [status_check] Healthy: {healthy} | Failed: {failed}", "info")
                    if node_state.get("job_health_reports"):
                        st.session_state.job_health_reports = node_state["job_health_reports"]
                        for r in node_state["job_health_reports"]:
                            emoji = "✅" if r["status"] == "healthy" else "❌"
                            add_log(f"  {emoji} Job {r.get('job_id','?')}: {r['status'].upper()} — {r.get('job_name','')}", "success" if r["status"] == "healthy" else "error")
                elif node_name == "initial_email":
                    has_fail = node_state.get("has_failures", False)
                    add_log(f"✉️  [initial_email] Sent — {'⚠️ Failures detected' if has_fail else '✅ All healthy, no action needed'}", "success")
                elif node_name == "failure_alert":
                    conf = node_state.get("confidence", 0)
                    rc = node_state.get("root_cause", "N/A")
                    add_log(f"🔬 [failure_alert] RCA confidence: {conf:.0%} — {rc[:80]}", "warning")
                elif node_name == "job_fixer":
                    status = node_state.get("fix_status", "unknown")
                    add_log(f"🔧 [job_fixer] Fix result: {status.upper()}", "success" if status == "success" else "error")
                elif node_name == "pr_create":
                    pr = node_state.get("pr_url")
                    if pr:
                        st.session_state.pr_url = pr
                        add_log(f"🔀 [pr_create] PR created: {pr}", "success")
                elif node_name == "pr_wait_approval":
                    merged = node_state.get("pr_merged", False)
                    add_log(f"👤 [pr_wait_approval] PR {'merged ✅' if merged else 'closed/cancelled'}", "success" if merged else "warning")
                elif node_name == "deployment":
                    url = node_state.get("workflow_run_url")
                    if url:
                        st.session_state.workflow_run_url = url
                        add_log(f"🚀 [deployment] CD triggered: {url}", "success")
                elif node_name == "post_deployment_verification":
                    healthy = node_state.get("post_deployment_healthy", False)
                    add_log(f"🔍 [post_deploy] Job health: {'✅ HEALTHY' if healthy else '❌ STILL FAILING'}", "success" if healthy else "error")
                elif node_name == "final_confirmation_email":
                    add_log("🎉 [final_email] Full cycle complete — confirmation email sent!", "success")
                elif node_name == "deployment_failed_email":
                    add_log("🚨 [escalation_email] Post-deploy still failing — escalation email sent!", "error")
                else:
                    add_log(f"📍 [{node_name}] Completed", "info")
                
                if "pr_url" in node_state and node_state["pr_url"]:
                    st.session_state.pr_url = node_state["pr_url"]
                if "workflow_run_url" in node_state and node_state["workflow_run_url"]:
                    st.session_state.workflow_run_url = node_state["workflow_run_url"]
                if "mttr_seconds" in node_state:
                    st.session_state.mttr_seconds = node_state["mttr_seconds"]
                if "emails_sent" in node_state:
                    st.session_state.email_count = len(node_state["emails_sent"])
                
                st.session_state.workflow_state = node_state
        
        # Workflow complete
        elapsed = time.time() - st.session_state.start_time
        has_failures = final_state.get("has_failures", False)
        post_healthy = final_state.get("post_deployment_healthy", False)
        
        if not has_failures:
            outcome = "healthy"
            outcome_label = "✅ Job was already healthy — no action needed"
            add_log(f"✅ Workflow complete in {elapsed:.0f}s — Job is HEALTHY, Stage 1 email sent.", "success")
        elif post_healthy:
            outcome = "healed"
            outcome_label = f"🎉 Incident auto-healed in {elapsed:.0f}s (MTTR)"
            add_log(f"🎉 Workflow complete in {elapsed:.0f}s — HEALED!", "success")
        else:
            outcome = "failed"
            outcome_label = "❌ Could not fully heal — escalation email sent"
            add_log(f"❌ Workflow complete in {elapsed:.0f}s — still failing after deployment.", "error")
        
        # Build last run summary
        reports = final_state.get("job_health_reports", [])
        st.session_state.last_run_result = {
            "outcome": outcome,
            "outcome_label": outcome_label,
            "elapsed": elapsed,
            "has_failures": has_failures,
            "healthy_count": final_state.get("healthy_count", 0),
            "failed_count": final_state.get("failed_count", 0),
            "job_health_reports": reports,
            "emails_sent": final_state.get("emails_sent", []),
            "nodes_completed": len(st.session_state.completed_nodes),
            "pr_url": st.session_state.pr_url,
            "root_cause": final_state.get("root_cause"),
            "confidence": final_state.get("confidence", 0),
        }
        st.session_state.workflow_completed_at = time.time()
        
        # Add to history
        st.session_state.incidents_history.append({
            "timestamp": datetime.now().isoformat(),
            "job_id": ",".join(map(str, selected_job_ids)),
            "status": outcome,
            "mttr": elapsed,
            "pr_url": st.session_state.pr_url
        })
        
        # Re-fetch job status to show updated state
        add_log("🔄 Refreshing job status...", "info")
        updated_jobs = fetch_databricks_jobs()
        for job in updated_jobs:
            if job["job_id"] in selected_job_ids:
                st.session_state.monitored_jobs_status[job["job_id"]] = job
        add_log(f"✅ Refreshed status for {len(selected_job_ids)} job(s)", "success")
        
    except Exception as e:
        add_log(f"❌ Workflow error: {str(e)}", "error")
    finally:
        st.session_state.workflow_running = False
        st.session_state.current_node = None

# ═══════════════════════════════════════════════════════════════════════════
# MAIN DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════

# Header
st.markdown('<h1 class="main-title">🛡️ AEGIS Live Dashboard</h1>', unsafe_allow_html=True)
st.markdown(
    '<p class="subtitle">Autonomous Excellence Guardian & Intelligent System<br>'
    'Real-Time Multi-Agent Workflow • 15 Nodes • GPT-5.5 Powered</p>',
    unsafe_allow_html=True
)

# ═══════════════════════════════════════════════════════════════════════════
# SIDEBAR - CONTROLS
# ═══════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("### 🎛️ Control Panel")
    st.markdown("---")
    
    # Job Selection
    st.markdown("#### 📋 Job Selection")
    if st.button("🔄 Refresh Jobs", use_container_width=True, disabled=st.session_state.workflow_running):
        st.session_state.available_jobs = fetch_databricks_jobs()
        add_log("Jobs refreshed", "info")
        st.rerun()
    
    if not st.session_state.available_jobs:
        st.session_state.available_jobs = fetch_databricks_jobs()
    
    if st.session_state.available_jobs:
        # Multi-select for jobs
        job_options = {f"{j['job_id']}": f"{j['name'][:50]}" for j in st.session_state.available_jobs}
        
        selected_labels = st.multiselect(
            "Select Job(s) to Monitor",
            options=list(job_options.keys()),
            format_func=lambda x: f"{x} - {job_options[x]}",
            disabled=st.session_state.workflow_running,
            default=st.session_state.selected_job_ids if st.session_state.selected_job_ids else []
        )
        
        st.session_state.selected_job_ids = [int(jid) for jid in selected_labels]
        
        if st.session_state.selected_job_ids:
            # Show count and failed status
            selected_job_data = [j for j in st.session_state.available_jobs if j["job_id"] in st.session_state.selected_job_ids]
            failed_count = sum(1 for j in selected_job_data if j.get("is_failed", False))
            
            if failed_count > 0:
                st.warning(f"⚠️ {failed_count} of {len(st.session_state.selected_job_ids)} job(s) in FAILED state")
            else:
                st.success(f"✅ All {len(st.session_state.selected_job_ids)} selected job(s) healthy")
    else:
        st.warning("No jobs found. Click 'Refresh Jobs'.")
    
    st.markdown("---")
    
    # Start/Stop Controls
    st.markdown("#### ⚡ Workflow Control")
    
    if not st.session_state.workflow_running:
        if st.button("🚀 Start Monitoring", type="primary", use_container_width=True, disabled=len(st.session_state.selected_job_ids) == 0):
            st.session_state.workflow_running = True
            st.session_state.workflow_logs = []
            st.session_state.completed_nodes = []
            st.session_state.last_run_result = None
            
            # Store initial status
            for job in st.session_state.available_jobs:
                if job["job_id"] in st.session_state.selected_job_ids:
                    st.session_state.monitored_jobs_status[job["job_id"]] = job
            
            # Run workflow in background thread
            thread = threading.Thread(
                target=run_aegis_workflow_thread,
                args=(st.session_state.selected_job_ids,),
                daemon=True
            )
            thread.start()
            st.rerun()
    else:
        st.success("🟢 AEGIS is running...")
        if st.button("⏹️ Stop", type="secondary", use_container_width=True):
            st.session_state.workflow_running = False
            add_log("Workflow stopped by user", "warning")
            st.rerun()
    
    st.markdown("---")
    
    # Configuration Info
    st.markdown("#### ⚙️ Configuration")
    st.info(f"""
    **Databricks**  
    🔗 {os.getenv('DATABRICKS_HOST', 'N/A')}
    
    **Model**  
    🤖 GPT-5.5 (EPAM DIAL)
    
    **GitHub**  
    📦 {os.getenv('GITHUB_REPO_NAME', 'aegis')}
    """)
    
    st.markdown("---")
    st.caption("AEGIS v2.0 | 15-Node Workflow")

# ═══════════════════════════════════════════════════════════════════════════
# MAIN CONTENT - SIMPLIFIED FOCUSED UI
# ═══════════════════════════════════════════════════════════════════════════

# Top metrics
col1, col2, col3, col4 = st.columns(4)

with col1:
    status_emoji = "🟡" if st.session_state.workflow_running else "🟢"
    status_text = "Running" if st.session_state.workflow_running else "Idle"
    st.metric("System Status", f"{status_emoji} {status_text}")

with col2:
    st.metric("Elapsed Time", get_elapsed_time())

with col3:
    progress_pct = (len(st.session_state.completed_nodes) / 15 * 100) if st.session_state.completed_nodes else 0
    st.metric("Progress", f"{progress_pct:.0f}%")

with col4:
    st.metric("Selected Jobs", len(st.session_state.selected_job_ids))

st.markdown("---")

# ══ Selected Jobs Status Table ═══════════════════════════════════════════════
if st.session_state.selected_job_ids:
    st.markdown("### 📊 Monitored Jobs")
    
    # Use monitored_jobs_status if available (refreshed after workflow), else use available_jobs
    if st.session_state.monitored_jobs_status:
        display_data = list(st.session_state.monitored_jobs_status.values())
    else:
        display_data = [j for j in st.session_state.available_jobs if j["job_id"] in st.session_state.selected_job_ids]
    
    if display_data:
        import pandas as pd
        df = pd.DataFrame([{
            "Job ID": str(j["job_id"]),
            "Name": j["name"][:55],
            "Status": f"{'✅' if j.get('result_state') == 'SUCCESS' else '❌'} {j.get('result_state', 'UNKNOWN')}",
            "Tasks": j.get("tasks", 0),
        } for j in display_data])
        
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True
        )
else:
    st.info("👈 Select job(s) from the sidebar to start monitoring")

st.markdown("---")

# ══ Real-time Progress (while running) ═══════════════════════════════════════
if st.session_state.workflow_running:
    st.markdown("### ⏳ Workflow In Progress")
    progress = len(st.session_state.completed_nodes) / 15
    st.progress(progress, text=f"⚙️ {st.session_state.current_node}")
    
    # Workflow nodes completed so far
    if st.session_state.completed_nodes:
        with st.expander(f"✅ Completed {len(st.session_state.completed_nodes)} nodes"):
            for node in st.session_state.completed_nodes:
                st.write(f"• {node}")

st.markdown("---")

# ══ Last Run Result Banner ═══════════════════════════════════════════════════
result = st.session_state.last_run_result
if result:
    outcome = result["outcome"]
    if outcome == "healthy":
        banner_color = "#d4edda"
        border_color = "#28a745"
        icon = "✅"
    elif outcome == "healed":
        banner_color = "#cce5ff"
        border_color = "#004085"
        icon = "🎉"
    else:
        banner_color = "#f8d7da"
        border_color = "#721c24"
        icon = "❌"
    
    st.markdown(
        f'<div style="background:{banner_color};border-left:6px solid {border_color};'
        f'border-radius:0.8rem;padding:1.2rem 1.5rem;margin:1rem 0;">'
        f'<h3 style="margin:0;color:{border_color}">{icon} Last Run Result</h3>'
        f'<p style="margin:0.5rem 0 0;font-size:1.1rem;"><b>{result["outcome_label"]}</b></p>'
        f'</div>',
        unsafe_allow_html=True
    )
    
    r1, r2, r3 = st.columns(3)
    r1.metric("Duration", f"{result['elapsed']:.0f}s")
    r2.metric("Nodes", result["nodes_completed"])
    r3.metric("Emails", len(result.get("emails_sent", [])))
    
    if outcome != "healthy" and result.get("root_cause"):
        st.markdown(f"**🔬 Root Cause ({result['confidence']:.0%} confidence):** {result['root_cause']}")
    
    if result.get("pr_url"):
        st.markdown(f'<a href="{result["pr_url"]}" target="_blank" class="url-link">🔀 View PR</a>', unsafe_allow_html=True)
    
    st.markdown("---")

# ══ Live Logs ═════════════════════════════════════════════════════════════════
with st.expander("📋 View Live Logs", expanded=st.session_state.workflow_running):
    recent_logs = st.session_state.workflow_logs[-15:]
    
    if recent_logs:
        for log in reversed(recent_logs):
            level_class = f"log-{log['level']}"
            st.markdown(f'<div class="log-entry {level_class}">[{log["timestamp"]}] {log["message"]}</div>', unsafe_allow_html=True)
    else:
        st.info("No logs yet")

# ═══════════════════════════════════════════════════════════════════════════
# AUTO-REFRESH FOR REAL-TIME UPDATES
# ═══════════════════════════════════════════════════════════════════════════

# Auto-refresh: while running OR for 10 seconds after completion so final state shows
if st.session_state.workflow_running:
    time.sleep(2)
    st.rerun()
elif st.session_state.workflow_completed_at and (time.time() - st.session_state.workflow_completed_at) < 10:
    time.sleep(1)
    st.rerun()
