"""
AEGIS Real-Time Dashboard - Production Integration
Connects to real Databricks and executes actual multi-agent workflow.
"""
import streamlit as st
import asyncio
import os
from datetime import datetime
from dotenv import load_dotenv
import yaml
from typing import Dict, List
import plotly.graph_objects as go
import json
from pathlib import Path

# Import AEGIS real components
from src.agents.status_checker import StatusCheckerAgent
from src.workflow import build_aegis_workflow, AEGISState

load_dotenv()

# Page config
st.set_page_config(
    page_title="AEGIS Dashboard - Live",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Load config
@st.cache_resource
def load_config():
    with open("config/config.yaml", "r") as f:
        return yaml.safe_load(f)

config = load_config()

# Initialize session state
if "jobs" not in st.session_state:
    st.session_state.jobs = []
if "workflow_running" not in st.session_state:
    st.session_state.workflow_running = False
if "workflow_logs" not in st.session_state:
    st.session_state.workflow_logs = []
if "workflow_state" not in st.session_state:
    st.session_state.workflow_state = None
if "incidents_history" not in st.session_state:
    st.session_state.incidents_history = []
if "current_stage" not in st.session_state:
    st.session_state.current_stage = None

# Custom CSS - Light Theme
st.markdown("""
<style>
    .stApp {
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
    }
    .main-title {
        font-size: 3rem;
        font-weight: bold;
        color: #2c3e50;
        text-align: center;
        padding: 1rem 0;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.1);
    }
    .subtitle {
        text-align: center;
        color: #34495e;
        font-size: 1.1rem;
        margin-bottom: 2rem;
    }
    .stage-active {
        background: #3498db;
        color: white;
        padding: 0.8rem 1rem;
        border-radius: 0.5rem;
        font-weight: bold;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .stage-complete {
        background: #27ae60;
        color: white;
        padding: 0.8rem 1rem;
        border-radius: 0.5rem;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .stage-pending {
        background: #ecf0f1;
        color: #7f8c8d;
        padding: 0.8rem 1rem;
        border-radius: 0.5rem;
    }
    .metric-card {
        background: white;
        padding: 1rem;
        border-radius: 0.5rem;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .log-entry {
        background: white;
        padding: 0.5rem;
        margin: 0.25rem 0;
        border-radius: 0.3rem;
        border-left: 4px solid #3498db;
    }
</style>
""", unsafe_allow_html=True)

# Helper function to run workflow
def execute_aegis_workflow_sync(monitor_all_jobs: bool, specific_job_id: str = None, dab_bundle_name: str = None):
    """Execute the real AEGIS LangGraph workflow synchronously"""
    
    import asyncio
    from datetime import datetime
    
    async def _run_workflow():
        # Build the workflow
        workflow = build_aegis_workflow()
        
        # Initial state
        initial_state: AEGISState = {
            "monitor_all_jobs": monitor_all_jobs,
            "specific_job_id": specific_job_id,
            "dab_bundle_name": dab_bundle_name,
            "job_health_reports": [],
            "has_failures": False,
            "current_incident_id": None,
            "root_cause": None,
            "confidence": 0.0,
            "fix_status": None,
            "fixed_notebooks": [],
            "post_fix_run_id": None,
            "pr_url": None,
            "pr_number": None,
            "pr_merged": False,
            "pr_rejected": False,
            "workflow_run_url": None,
            "deployment_status": None,
            "final_health_check": [],
            "escalation_reason": None,
            "emails_sent": [],
            "start_time": datetime.now().isoformat(),
            "end_time": None,
        }
        
        # Execute workflow and collect events
        events = []
        async for event in workflow.astream(initial_state):
            events.append(event)
        
        return events
    
    # Run async workflow in sync context
    return asyncio.run(_run_workflow())

# Header
st.markdown('<h1 class="main-title">🛡️ AEGIS Production Dashboard</h1>', unsafe_allow_html=True)
st.markdown('<p class="subtitle">AI-Engine for Guardian Intelligence & Self-healing<br>Real-Time Multi-Agent Autonomous System</p>', unsafe_allow_html=True)

# Top metrics row
met1, met2, met3, met4, met5 = st.columns(5)

with met1:
    status_color = "🟢" if not st.session_state.workflow_running else "🟡"
    status_text = "Online" if not st.session_state.workflow_running else "Running"
    st.metric("System Status", f"{status_color} {status_text}")
with met2:
    healthy = sum(1 for j in st.session_state.jobs if j.get("status") == "healthy")
    st.metric("Healthy Jobs", healthy)
with met3:
    failed = sum(1 for j in st.session_state.jobs if j.get("status") == "failed")
    st.metric("Failed Jobs", failed)
with met4:
    avg_mttr = sum(i["mttr"] for i in st.session_state.incidents_history) / len(st.session_state.incidents_history) if st.session_state.incidents_history else 0
    st.metric("Avg MTTR", f"{avg_mttr:.0f}s" if avg_mttr > 0 else "N/A")
with met5:
    heal_rate = (len([i for i in st.session_state.incidents_history if i["status"] == "healed"]) / len(st.session_state.incidents_history) * 100) if st.session_state.incidents_history else 0
    st.metric("Auto-Heal Rate", f"{heal_rate:.0f}%" if heal_rate > 0 else "N/A")

st.divider()

# Main layout - 2 columns
col_left, col_right = st.columns([2, 1])

with col_left:
    st.subheader("📊 Databricks Job Health Monitor")
    
    # Refresh button
    refresh_btn = st.button("🔄 Refresh Health Status", key="refresh_health", disabled=st.session_state.workflow_running)
    
    if refresh_btn:
        with st.spinner("Connecting to Databricks..."):
            async def fetch_health():
                agent = StatusCheckerAgent(
                    os.environ.get("DATABRICKS_HOST", ""),
                    os.environ.get("DATABRICKS_TOKEN", "")
                )
                
                # Check if monitoring all jobs or specific job
                specific_job = os.environ.get("DATABRICKS_JOB_ID")
                dab_bundle = os.environ.get("DAB_BUNDLE_NAME", "aegis-de-project")
                
                if specific_job:
                    return await agent.check_health(
                        monitor_all_jobs=False,
                        specific_job_id=specific_job
                    )
                else:
                    return await agent.check_health(
                        monitor_all_jobs=True,
                        dab_bundle_name=dab_bundle
                    )
            
            try:
                st.session_state.jobs = asyncio.run(fetch_health())
                st.success(f"✅ Health check complete - Found {len(st.session_state.jobs)} job(s)")
            except Exception as e:
                st.error(f"❌ Health check failed: {e}")
    
    # Job status grid
    if st.session_state.jobs:
        for job in st.session_state.jobs:
            status_emoji = "✅" if job["status"] == "healthy" else "❌" if job["status"] == "failed" else "❓"
            status_color = "#27ae60" if job["status"] == "healthy" else "#e74c3c" if job["status"] == "failed" else "#95a5a6"
            
            with st.container():
                col_a, col_b, col_c = st.columns([3, 2, 1])
                with col_a:
                    st.markdown(f"### {status_emoji} {job['job_name']}")
                with col_b:
                    st.markdown(f"**Job ID:** `{job['job_id']}`")
                with col_c:
                    st.markdown(f"<span style='color:{status_color};font-weight:bold;'>{job['status'].upper()}</span>", unsafe_allow_html=True)
                
                if job["status"] == "failed":
                    with st.expander("🔍 Error Details", expanded=True):
                        st.error(f"**Failed Tasks:** {', '.join(job['failed_tasks'])}")
                        st.code(job['error_summary'][:500], language="python")
    else:
        st.info("👆 Click 'Refresh Health Status' to check Databricks jobs")

with col_right:
    st.subheader("🛡️ AEGIS Control Panel")
    
    # Configuration display
    st.markdown("### ⚙️ Configuration")
    
    db_host = os.environ.get("DATABRICKS_HOST", "Not configured")
    db_connected = bool(os.environ.get("DATABRICKS_HOST") and os.environ.get("DATABRICKS_TOKEN"))
    st.text(f"Databricks: {'✅ Connected' if db_connected else '❌ Not configured'}")
    
    llm_connected = bool(os.environ.get("DIAL_API_KEY"))
    st.text(f"LLM (GPT-4o): {'✅ Ready' if llm_connected else '❌ Not configured'}")
    
    gh_connected = bool(os.environ.get("GITHUB_TOKEN"))
    st.text(f"GitHub: {'✅ Ready' if gh_connected else '❌ Not configured'}")
    
    gmail_connected = bool(os.environ.get("GMAIL_SENDER") and os.environ.get("GMAIL_APP_PASSWORD"))
    st.text(f"Gmail: {'✅ Ready' if gmail_connected else '❌ Not configured'}")
    
    st.divider()
    
    # Monitoring mode
    st.markdown("### 🎯 Monitoring Mode")
    specific_job = os.environ.get("DATABRICKS_JOB_ID")
    if specific_job:
        st.info(f"📍 Monitoring specific job: `{specific_job}`")
    else:
        dab_bundle = os.environ.get("DAB_BUNDLE_NAME", "aegis-de-project")
        st.info(f"📍 Monitoring all jobs in bundle: `{dab_bundle}`")
    
    st.divider()
    
    # Big run button
    run_btn = st.button(
        "▶️ Run AEGIS Workflow",
        type="primary",
        use_container_width=True,
        disabled=st.session_state.workflow_running or not db_connected,
        key="run_aegis"
    )
    
    if not db_connected:
        st.warning("⚠️ Configure Databricks credentials in .env to run AEGIS")
    
    if run_btn:
        st.session_state.workflow_running = True
        st.session_state.workflow_logs = []
        st.session_state.workflow_state = None
        st.rerun()

st.divider()

# Workflow execution section
if st.session_state.workflow_running:
    st.header("🚀 AEGIS Workflow Execution (LIVE)")
    
    # Progress stages mapping
    stage_display = {
        "status_check_node": ("🔍", "Status Check", "Monitoring Databricks jobs"),
        "initial_email_node": ("📧", "Initial Email", "Sending health report"),
        "failure_alert_node": ("⚠️", "Failure Alert", "Analyzing failures with GPT-4o"),
        "fix_in_progress_email_node": ("🔧", "Fix in Progress", "Notifying stakeholders"),
        "job_fixer_node": ("🛠️", "Job Fixer", "LLM repairing notebooks"),
        "fix_complete_email_node": ("✅", "Fix Complete", "Verification passed"),
        "pr_create_node": ("📝", "PR Creation", "Creating GitHub pull request"),
        "pr_raised_email_node": ("📬", "PR Raised", "Awaiting approval"),
        "pr_wait_approval_node": ("⏳", "PR Approval", "Polling for merge"),
        "deployment_node": ("🚀", "Deployment", "Triggering CD pipeline"),
        "deployment_complete_email_node": ("🎉", "Complete", "Workflow finished"),
    }
    
    # Create progress container
    progress_container = st.container()
    
    # Live logs container
    st.subheader("📜 Live Execution Log")
    log_container = st.container()
    
    # Execute workflow asynchronously
    async def run_workflow_async():
        specific_job = os.environ.get("DATABRICKS_JOB_ID")
        dab_bundle = os.environ.get("DAB_BUNDLE_NAME", "aegis-de-project")
        
        monitor_all = not bool(specific_job)
        
        try:
            async for node_name, node_state in execute_aegis_workflow(
                monitor_all_jobs=monitor_all,
                specific_job_id=specific_job,
                dab_bundle_name=dab_bundle
            ):
                # Update UI with current stage
                with progress_container:
                    if node_name in stage_display:
                        emoji, title, desc = stage_display[node_name]
                        st.info(f"{emoji} **{title}** - {desc}")
                
                # Add log entry
                with log_container:
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    st.markdown(f'<div class="log-entry">[{timestamp}] {node_name}</div>', unsafe_allow_html=True)
                
                # Show state updates
                if node_state.get("has_failures"):
                    st.warning(f"⚠️ Detected failures: {len(node_state.get('job_health_reports', []))} job(s)")
                
                if node_state.get("fix_status") == "success":
                    st.success(f"✅ Fix successful! Post-fix run ID: {node_state.get('post_fix_run_id')}")
                
                if node_state.get("pr_url"):
                    st.success(f"📝 PR created: {node_state['pr_url']}")
                
                # Small delay for UI update
                await asyncio.sleep(0.5)
            
            # Workflow complete
            st.session_state.workflow_running = False
            final_state = st.session_state.workflow_state
            
            # Save incident to history
            if final_state and final_state.get("current_incident_id"):
                start_time = datetime.fromisoformat(final_state["start_time"])
                end_time = datetime.fromisoformat(final_state.get("end_time", datetime.now().isoformat()))
                mttr = int((end_time - start_time).total_seconds())
                
                st.session_state.incidents_history.append({
                    "id": final_state["current_incident_id"],
                    "mttr": mttr,
                    "status": "healed" if final_state.get("deployment_status") == "success" else "escalated",
                    "timestamp": start_time.strftime("%Y-%m-%d %H:%M"),
                })
            
            st.success("🎉 AEGIS Workflow completed successfully!")
            
            # Show final results
            if final_state:
                st.subheader("📊 Execution Results")
                
                res1, res2, res3, res4 = st.columns(4)
                res1.metric("Incident ID", final_state.get("current_incident_id", "N/A"))
                
                if final_state.get("start_time") and final_state.get("end_time"):
                    start = datetime.fromisoformat(final_state["start_time"])
                    end = datetime.fromisoformat(final_state["end_time"])
                    mttr = int((end - start).total_seconds())
                    res2.metric("MTTR", f"{mttr}s")
                else:
                    res2.metric("MTTR", "N/A")
                
                status = final_state.get("deployment_status", "unknown")
                res3.metric("Status", "✅ Healed" if status == "success" else "⚠️ Escalated")
                
                emails_sent = len(final_state.get("emails_sent", []))
                res4.metric("Emails Sent", emails_sent)
                
                if final_state.get("pr_url"):
                    st.markdown(f"### 📝 Pull Request")
                    st.markdown(f"[View PR on GitHub]({final_state['pr_url']})")
                
                if final_state.get("workflow_run_url"):
                    st.markdown(f"### 🚀 GitHub Actions")
                    st.markdown(f"[View Deployment]({final_state['workflow_run_url']})")
                
                # Show full state in expander
                with st.expander("🔍 View Full State (JSON)"):
                    st.json(final_state)
            
        except Exception as e:
            st.session_state.workflow_running = False
            st.error(f"❌ Workflow failed: {e}")
            import traceback
            st.code(traceback.format_exc())
    
    # Run the workflow
    asyncio.run(run_workflow_async())
    
    # Rerun button
    if not st.session_state.workflow_running:
        if st.button("🔄 Run Again", key="run_again"):
            st.session_state.workflow_logs = []
            st.session_state.workflow_state = None
            st.rerun()

# Analytics section - only show if we have incident history
if st.session_state.incidents_history:
    st.divider()
    st.header("📈 Analytics & Insights")

    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        st.subheader("MTTR Trend")
        
        # Create MTTR trend chart
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=[i["timestamp"] for i in st.session_state.incidents_history],
            y=[i["mttr"] for i in st.session_state.incidents_history],
            mode='lines+markers',
            name='MTTR',
            line=dict(color='#3498db', width=3),
            marker=dict(size=10, color='#2980b9')
        ))
        fig.update_layout(
            title="Mean Time to Recovery",
            xaxis_title="Timestamp",
            yaxis_title="MTTR (seconds)",
            template="plotly_white",
            height=300,
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
        )
        st.plotly_chart(fig, use_container_width=True)

    with chart_col2:
        st.subheader("Incident Status Distribution")
        
        # Pie chart
        statuses = [i["status"] for i in st.session_state.incidents_history]
        status_counts = {status: statuses.count(status) for status in set(statuses)}
        
        fig = go.Figure(data=[go.Pie(
            labels=list(status_counts.keys()),
            values=list(status_counts.values()),
            hole=0.4,
            marker=dict(colors=['#27ae60', '#e74c3c', '#f39c12'])
        )])
        fig.update_layout(
            title="Incident Outcomes",
            template="plotly_white",
            height=300,
            paper_bgcolor='rgba(0,0,0,0)',
        )
        st.plotly_chart(fig, use_container_width=True)

    # Recent incidents table
    st.subheader("🕒 Recent Incidents")
    for incident in st.session_state.incidents_history[-10:]:
        col_i1, col_i2, col_i3, col_i4 = st.columns([2, 2, 2, 1])
        col_i1.write(f"**{incident['id']}**")
        col_i2.write(incident['timestamp'])
        col_i3.write(f"{incident['mttr']}s MTTR")
        status_emoji = "✅" if incident['status'] == "healed" else "❌"
        col_i4.write(f"{status_emoji} {incident['status']}")

# Footer
st.divider()
st.markdown("""
<div style='text-align: center; color: #34495e; padding: 2rem 0;'>
    <p><strong>AEGIS v2.0</strong> — Production Multi-Agent System</p>
    <p>Powered by LangGraph | GPT-4o | Real Databricks Integration</p>
</div>
""", unsafe_allow_html=True)

