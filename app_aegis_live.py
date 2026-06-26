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
if "selected_job_id" not in st.session_state:
    st.session_state.selected_job_id = None
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
    """Fetch all available Databricks jobs"""
    try:
        client = WorkspaceClient(
            host=config["databricks"]["host"],
            token=config["databricks"]["token"]
        )
        jobs = []
        for job in client.jobs.list():
            # Get latest run status
            runs = list(client.jobs.list_runs(job_id=job.job_id, limit=1))
            latest_status = runs[0].state.life_cycle_state.value if runs else "UNKNOWN"
            
            jobs.append({
                "job_id": job.job_id,
                "name": job.settings.name,
                "tasks": len(job.settings.tasks) if job.settings.tasks else 0,
                "status": latest_status
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

def run_aegis_workflow_thread(selected_job_id: str):
    """Run AEGIS workflow in background thread"""
    try:
        add_log("🚀 Initializing AEGIS workflow...", "info")
        st.session_state.start_time = time.time()
        st.session_state.current_node = "job_selector"
        st.session_state.completed_nodes = []
        
        # Build workflow
        workflow = build_aegis_workflow()
        workflow_app = workflow.compile()
        
        # Initial state
        initial_state: AEGISState = {
            "workspace_host": config["databricks"]["host"],
            "workspace_token": config["databricks"]["token"],
            "monitor_all_jobs": selected_job_id == "all",
            "specific_job_id": selected_job_id if selected_job_id != "all" else None,
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
            "user_selected_job_id": selected_job_id,
        }
        
        add_log(f"✅ Workflow initialized. Monitoring: {selected_job_id}", "success")
        
        # Execute workflow with node tracking
        for state_update in workflow_app.stream(initial_state):
            # Track current node
            if state_update:
                node_name = list(state_update.keys())[0]
                st.session_state.current_node = node_name
                
                if node_name not in st.session_state.completed_nodes:
                    st.session_state.completed_nodes.append(node_name)
                    add_log(f"📍 Node: {node_name}", "info")
                
                # Extract state data
                node_state = state_update[node_name]
                
                # Update session state with latest data
                if "pr_url" in node_state and node_state["pr_url"]:
                    st.session_state.pr_url = node_state["pr_url"]
                    add_log(f"🔗 PR Created: {node_state['pr_url']}", "success")
                
                if "workflow_run_url" in node_state and node_state["workflow_run_url"]:
                    st.session_state.workflow_run_url = node_state["workflow_run_url"]
                    add_log(f"🚀 Deployment: {node_state['workflow_run_url']}", "success")
                
                if "mttr_seconds" in node_state:
                    st.session_state.mttr_seconds = node_state["mttr_seconds"]
                
                if "emails_sent" in node_state:
                    st.session_state.email_count = len(node_state["emails_sent"])
                
                # Store final state
                st.session_state.workflow_state = node_state
        
        # Workflow complete
        elapsed = time.time() - st.session_state.start_time
        add_log(f"✅ Workflow completed in {elapsed:.0f}s", "success")
        
        # Add to history
        st.session_state.incidents_history.append({
            "timestamp": datetime.now().isoformat(),
            "job_id": selected_job_id,
            "status": "healed" if st.session_state.workflow_state.get("post_deployment_healthy") else "failed",
            "mttr": elapsed,
            "pr_url": st.session_state.pr_url
        })
        
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
    if st.button("🔄 Refresh Jobs", use_container_width=True):
        st.session_state.available_jobs = fetch_databricks_jobs()
        add_log("Jobs refreshed", "info")
    
    if not st.session_state.available_jobs:
        st.session_state.available_jobs = fetch_databricks_jobs()
    
    if st.session_state.available_jobs:
        job_options = ["all"] + [f"{j['job_id']} - {j['name'][:40]}" for j in st.session_state.available_jobs]
        selected = st.selectbox(
            "Select Job to Monitor",
            job_options,
            disabled=st.session_state.workflow_running
        )
        
        if selected == "all":
            st.session_state.selected_job_id = "all"
        else:
            st.session_state.selected_job_id = selected.split(" - ")[0]
    else:
        st.warning("No jobs found. Click 'Refresh Jobs'.")
    
    st.markdown("---")
    
    # Start/Stop Controls
    st.markdown("#### ⚡ Workflow Control")
    
    if not st.session_state.workflow_running:
        if st.button("🚀 Start AEGIS", type="primary", use_container_width=True, disabled=not st.session_state.selected_job_id):
            st.session_state.workflow_running = True
            st.session_state.workflow_logs = []
            st.session_state.completed_nodes = []
            
            # Run workflow in background thread
            thread = threading.Thread(
                target=run_aegis_workflow_thread,
                args=(st.session_state.selected_job_id,),
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
    🔗 {config['databricks']['host']}
    
    **Model**  
    🤖 GPT-5.5 (EPAM DIAL)
    
    **GitHub**  
    📦 {config['github']['repo']}
    """)
    
    st.markdown("---")
    st.caption("AEGIS v2.0 | 15-Node Workflow")

# ═══════════════════════════════════════════════════════════════════════════
# MAIN CONTENT - TABS
# ═══════════════════════════════════════════════════════════════════════════

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Live Dashboard",
    "🔄 Workflow Progress",
    "📝 Live Logs",
    "📈 Analytics",
    "🔗 Resources"
])

# ─────────────────────────────────────────────────────────────────────────────
# TAB 1: LIVE DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────

with tab1:
    # Top metrics
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        status_emoji = "🟡" if st.session_state.workflow_running else "🟢"
        status_text = "Running" if st.session_state.workflow_running else "Idle"
        st.metric("System Status", f"{status_emoji} {status_text}")
    
    with col2:
        st.metric("Elapsed Time", get_elapsed_time())
    
    with col3:
        st.metric("Current Node", st.session_state.current_node or "—")
    
    with col4:
        progress_pct = (len(st.session_state.completed_nodes) / 15 * 100) if st.session_state.completed_nodes else 0
        st.metric("Progress", f"{progress_pct:.0f}%")
    
    with col5:
        st.metric("Emails Sent", st.session_state.email_count)
    
    st.markdown("---")
    
    # Current Job Info
    if st.session_state.selected_job_id:
        st.markdown("### 🎯 Current Monitoring Target")
        
        if st.session_state.selected_job_id == "all":
            st.info(f"**Monitoring:** All Jobs ({len(st.session_state.available_jobs)} total)")
        else:
            job_info = next((j for j in st.session_state.available_jobs if str(j['job_id']) == st.session_state.selected_job_id), None)
            if job_info:
                col_a, col_b, col_c = st.columns(3)
                with col_a:
                    st.info(f"**Job ID:** {job_info['job_id']}")
                with col_b:
                    st.info(f"**Name:** {job_info['name']}")
                with col_c:
                    status_emoji = "✅" if job_info['status'] == "SUCCESS" else "❌"
                    st.info(f"**Status:** {status_emoji} {job_info['status']}")
    
    st.markdown("---")
    
    # Real-time Progress Bar
    if st.session_state.workflow_running:
        st.markdown("### ⏳ Real-Time Progress")
        progress = len(st.session_state.completed_nodes) / 15
        st.progress(progress, text=f"Processing: {st.session_state.current_node}")
        
        # Show waiting indicator
        with st.spinner(f"Processing node: {st.session_state.current_node}..."):
            time.sleep(0.5)  # Small delay for UI responsiveness
    
    # Latest Logs Preview
    st.markdown("### 📋 Latest Activity")
    recent_logs = st.session_state.workflow_logs[-5:]
    
    if recent_logs:
        for log in reversed(recent_logs):
            level_class = f"log-{log['level']}"
            st.markdown(f'<div class="log-entry {level_class}">[{log["timestamp"]}] {log["message"]}</div>', unsafe_allow_html=True)
    else:
        st.info("No activity yet. Start AEGIS to begin monitoring.")

# ─────────────────────────────────────────────────────────────────────────────
# TAB 2: WORKFLOW PROGRESS
# ─────────────────────────────────────────────────────────────────────────────

with tab2:
    st.markdown("### 🔄 15-Node Workflow Progress")
    
    # Define all 15 nodes
    all_nodes = [
        "job_selector",
        "status_check",
        "initial_email",
        "failure_alert",
        "fix_in_progress_email",
        "job_fixer",
        "fix_complete_email",
        "pr_create",
        "pr_raised_email",
        "pr_wait_approval",
        "deployment",
        "post_deployment_verification",
        "final_confirmation_email",
        "deployment_failed_email",
    ]
    
    # Display each node
    for i, node in enumerate(all_nodes, 1):
        if node in st.session_state.completed_nodes:
            st.markdown(f'<div class="stage-complete">✅ {i}. {node}</div>', unsafe_allow_html=True)
        elif node == st.session_state.current_node:
            st.markdown(f'<div class="stage-active">⏳ {i}. {node} (In Progress...)</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="stage-pending">⏸️ {i}. {node}</div>', unsafe_allow_html=True)
    
    # Workflow visualization
    st.markdown("---")
    st.markdown("### 📊 Workflow Flow Diagram")
    
    # Create flow chart
    fig = go.Figure()
    
    # Add nodes
    completed_count = len(st.session_state.completed_nodes)
    total_count = 15
    
    fig.add_trace(go.Indicator(
        mode="gauge+number+delta",
        value=completed_count,
        domain={'x': [0, 1], 'y': [0, 1]},
        title={'text': "Nodes Completed", 'font': {'size': 24}},
        delta={'reference': total_count, 'increasing': {'color': "green"}},
        gauge={
            'axis': {'range': [None, total_count], 'tickwidth': 1},
            'bar': {'color': "darkblue"},
            'bgcolor': "white",
            'borderwidth': 2,
            'bordercolor': "gray",
            'steps': [
                {'range': [0, total_count/3], 'color': '#f0f4f8'},
                {'range': [total_count/3, 2*total_count/3], 'color': '#d9e2ec'},
                {'range': [2*total_count/3, total_count], 'color': '#bcccdc'}
            ],
            'threshold': {
                'line': {'color': "red", 'width': 4},
                'thickness': 0.75,
                'value': total_count
            }
        }
    ))
    
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={'color': "#334e68", 'family': "Arial"},
        height=300
    )
    
    st.plotly_chart(fig, use_container_width=True)

# ─────────────────────────────────────────────────────────────────────────────
# TAB 3: LIVE LOGS
# ─────────────────────────────────────────────────────────────────────────────

with tab3:
    st.markdown("### 📝 Real-Time Logs")
    
    # Log filter
    log_filter = st.multiselect(
        "Filter by Level",
        ["info", "success", "warning", "error"],
        default=["info", "success", "warning", "error"]
    )
    
    st.markdown("---")
    
    # Display logs
    log_container = st.container(height=600)
    
    with log_container:
        filtered_logs = [log for log in st.session_state.workflow_logs if log["level"] in log_filter]
        
        if filtered_logs:
            for log in reversed(filtered_logs):
                level_class = f"log-{log['level']}"
                st.markdown(f'<div class="log-entry {level_class}">[{log["timestamp"]}] {log["message"]}</div>', unsafe_allow_html=True)
        else:
            st.info("No logs match the selected filters.")
    
    # Clear logs button
    if st.button("🗑️ Clear Logs"):
        st.session_state.workflow_logs = []
        st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# TAB 4: ANALYTICS
# ─────────────────────────────────────────────────────────────────────────────

with tab4:
    st.markdown("### 📈 Historical Analytics")
    
    if st.session_state.incidents_history:
        # Metrics
        col1, col2, col3, col4 = st.columns(4)
        
        total_incidents = len(st.session_state.incidents_history)
        healed = len([i for i in st.session_state.incidents_history if i["status"] == "healed"])
        avg_mttr = sum(i["mttr"] for i in st.session_state.incidents_history) / total_incidents
        heal_rate = (healed / total_incidents * 100)
        
        with col1:
            st.metric("Total Incidents", total_incidents)
        with col2:
            st.metric("Auto-Healed", f"{healed} ({heal_rate:.0f}%)")
        with col3:
            st.metric("Avg MTTR", f"{avg_mttr:.0f}s")
        with col4:
            st.metric("Success Rate", f"{heal_rate:.0f}%")
        
        st.markdown("---")
        
        # MTTR over time
        st.markdown("#### ⏱️ MTTR Over Time")
        
        mttr_data = [
            {"Incident": f"#{i+1}", "MTTR (seconds)": inc["mttr"]}
            for i, inc in enumerate(st.session_state.incidents_history)
        ]
        
        fig_mttr = px.line(
            mttr_data,
            x="Incident",
            y="MTTR (seconds)",
            markers=True,
            title="Mean Time To Recovery Trend"
        )
        fig_mttr.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="white",
            font={'color': "#334e68"}
        )
        st.plotly_chart(fig_mttr, use_container_width=True)
        
        st.markdown("---")
        
        # Success rate pie chart
        st.markdown("#### ✅ Healing Success Rate")
        
        col_a, col_b = st.columns([2, 1])
        
        with col_a:
            success_data = {
                "Status": ["Healed", "Failed"],
                "Count": [
                    healed,
                    total_incidents - healed
                ]
            }
            
            fig_success = px.pie(
                success_data,
                values="Count",
                names="Status",
                color="Status",
                color_discrete_map={"Healed": "#38ef7d", "Failed": "#f45c43"}
            )
            fig_success.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                font={'color': "#334e68"}
            )
            st.plotly_chart(fig_success, use_container_width=True)
        
        with col_b:
            st.markdown("##### 📊 Statistics")
            st.info(f"""
            **Total Incidents:** {total_incidents}  
            **Healed:** {healed}  
            **Failed:** {total_incidents - healed}  
            **Success Rate:** {heal_rate:.1f}%  
            **Avg MTTR:** {avg_mttr:.0f}s
            """)
        
        st.markdown("---")
        
        # Incident history table
        st.markdown("#### 📋 Incident History")
        
        history_display = []
        for i, inc in enumerate(st.session_state.incidents_history, 1):
            history_display.append({
                "#": i,
                "Timestamp": datetime.fromisoformat(inc["timestamp"]).strftime("%Y-%m-%d %H:%M:%S"),
                "Job ID": inc["job_id"],
                "Status": "✅ Healed" if inc["status"] == "healed" else "❌ Failed",
                "MTTR": f"{inc['mttr']:.0f}s",
                "PR": inc.get("pr_url", "N/A")
            })
        
        st.dataframe(history_display, use_container_width=True)
        
    else:
        st.info("No incident history yet. Complete a workflow run to see analytics.")

# ─────────────────────────────────────────────────────────────────────────────
# TAB 5: RESOURCES & LINKS
# ─────────────────────────────────────────────────────────────────────────────

with tab5:
    st.markdown("### 🔗 External Resources & Quick Links")
    
    # Databricks
    st.markdown("#### 🟠 Databricks")
    col1, col2 = st.columns(2)
    
    with col1:
        db_host = config['databricks']['host']
        st.markdown(f'<a href="{db_host}" target="_blank" class="url-link">🔗 Open Databricks Workspace</a>', unsafe_allow_html=True)
    
    with col2:
        if st.session_state.selected_job_id and st.session_state.selected_job_id != "all":
            job_url = f"{db_host}/#job/{st.session_state.selected_job_id}"
            st.markdown(f'<a href="{job_url}" target="_blank" class="url-link">📊 View Current Job</a>', unsafe_allow_html=True)
        else:
            st.markdown('<span class="url-link" style="background: #cbd5e0; color: #718096;">Select a job first</span>', unsafe_allow_html=True)
    
    st.markdown("---")
    
    # GitHub
    st.markdown("#### 🐙 GitHub")
    col3, col4 = st.columns(2)
    
    with col3:
        github_repo = f"https://github.com/{config['github']['owner']}/{config['github']['repo']}"
        st.markdown(f'<a href="{github_repo}" target="_blank" class="url-link">🔗 Open Repository</a>', unsafe_allow_html=True)
    
    with col4:
        if st.session_state.pr_url:
            st.markdown(f'<a href="{st.session_state.pr_url}" target="_blank" class="url-link">🔀 View Active PR</a>', unsafe_allow_html=True)
        else:
            st.markdown('<span class="url-link" style="background: #cbd5e0; color: #718096;">No PR created yet</span>', unsafe_allow_html=True)
    
    st.markdown("---")
    
    # GitHub Actions
    st.markdown("#### ⚙️ GitHub Actions (CD)")
    if st.session_state.workflow_run_url:
        st.markdown(f'<a href="{st.session_state.workflow_run_url}" target="_blank" class="url-link">🚀 View Deployment Workflow</a>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="url-link" style="background: #cbd5e0; color: #718096;">No deployment triggered yet</span>', unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Current Workflow State
    if st.session_state.workflow_state:
        st.markdown("#### 📦 Current Workflow State")
        
        with st.expander("🔍 View Full State Object"):
            st.json(st.session_state.workflow_state)
    
    st.markdown("---")
    
    # Quick Stats
    st.markdown("#### 📊 Quick Stats")
    
    stats_col1, stats_col2, stats_col3 = st.columns(3)
    
    with stats_col1:
        st.info(f"""
        **Available Jobs**  
        {len(st.session_state.available_jobs)} total
        """)
    
    with stats_col2:
        st.info(f"""
        **Logs Captured**  
        {len(st.session_state.workflow_logs)} entries
        """)
    
    with stats_col3:
        st.info(f"""
        **Incident History**  
        {len(st.session_state.incidents_history)} incidents
        """)

# ═══════════════════════════════════════════════════════════════════════════
# AUTO-REFRESH FOR REAL-TIME UPDATES
# ═══════════════════════════════════════════════════════════════════════════

if st.session_state.workflow_running:
    time.sleep(2)  # Refresh every 2 seconds
    st.rerun()
