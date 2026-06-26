"""
AEGIS Advanced Streamlit Dashboard with Real-Time Progress
Shows live workflow execution with stage-by-stage updates.
"""
import streamlit as st
import asyncio
import os
from datetime import datetime
from dotenv import load_dotenv
import yaml
import time
from typing import Dict, List
import plotly.graph_objects as go
import plotly.express as px

# Import AEGIS components
from src.agents.status_checker import StatusCheckerAgent

load_dotenv()

# Page config
st.set_page_config(
    page_title="AEGIS Dashboard",
    page_icon="🛡️",
    layout="wide",
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
if "workflow_progress" not in st.session_state:
    st.session_state.workflow_progress = []
if "incidents_history" not in st.session_state:
    st.session_state.incidents_history = [
        {"id": "INC-001", "mttr": 95, "status": "healed", "timestamp": "2024-06-25 10:15"},
        {"id": "INC-002", "mttr": 87, "status": "healed", "timestamp": "2024-06-25 14:30"},
        {"id": "INC-003", "mttr": 92, "status": "healed", "timestamp": "2024-06-26 08:20"},
    ]

# Custom CSS
st.markdown("""
<style>
    .stApp {
        background: linear-gradient(135deg, #0f0f1e 0%, #1a1a2e 100%);
    }
    .main-title {
        font-size: 3rem;
        font-weight: bold;
        background: linear-gradient(90deg, #00d2ff 0%, #3a7bd5 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        padding: 1rem 0;
    }
    .subtitle {
        text-align: center;
        color: #888;
        font-size: 1.1rem;
        margin-bottom: 2rem;
    }
    .stage-active {
        background: #3a7bd5;
        color: white;
        padding: 0.5rem 1rem;
        border-radius: 0.5rem;
        font-weight: bold;
    }
    .stage-complete {
        background: #2ecc71;
        color: white;
        padding: 0.5rem 1rem;
        border-radius: 0.5rem;
    }
    .stage-pending {
        background: #34495e;
        color: #95a5a6;
        padding: 0.5rem 1rem;
        border-radius: 0.5rem;
    }
</style>
""", unsafe_allow_html=True)

# Header
st.markdown('<h1 class="main-title">🛡️ AEGIS</h1>', unsafe_allow_html=True)
st.markdown('<p class="subtitle">AI-Engine for Guardian Intelligence & Self-healing<br>LangGraph Multi-Agent Autonomous Reliability System</p>', unsafe_allow_html=True)

# Top metrics row
met1, met2, met3, met4, met5 = st.columns(5)

with met1:
    st.metric("System Status", "🟢 Online", delta=None)
with met2:
    healthy = sum(1 for j in st.session_state.jobs if j.get("status") == "healthy")
    st.metric("Healthy Jobs", healthy)
with met3:
    failed = sum(1 for j in st.session_state.jobs if j.get("status") == "failed")
    st.metric("Failed Jobs", failed, delta="-1 auto-healed" if failed > 0 else None)
with met4:
    avg_mttr = sum(i["mttr"] for i in st.session_state.incidents_history) / len(st.session_state.incidents_history) if st.session_state.incidents_history else 0
    st.metric("Avg MTTR", f"{avg_mttr:.0f}s", delta="-95% vs manual")
with met5:
    heal_rate = (len([i for i in st.session_state.incidents_history if i["status"] == "healed"]) / len(st.session_state.incidents_history) * 100) if st.session_state.incidents_history else 0
    st.metric("Auto-Heal Rate", f"{heal_rate:.0f}%")

st.divider()

# Main layout - 2 columns
col_left, col_right = st.columns([2, 1])

with col_left:
    st.subheader("📊 Job Health Monitor")
    
    # Refresh button
    if st.button("🔄 Refresh Health", key="refresh_health"):
        with st.spinner("Checking job health..."):
            async def fetch_health():
                agent = StatusCheckerAgent(
                    os.environ.get("DATABRICKS_HOST", ""),
                    os.environ.get("DATABRICKS_TOKEN", "")
                )
                return await agent.check_health(
                    monitor_all_jobs=True,
                    dab_bundle_name=os.environ.get("DAB_BUNDLE_NAME", "aegis-de-project")
                )
            
            try:
                st.session_state.jobs = asyncio.run(fetch_health())
                st.success("✅ Health check complete")
            except Exception as e:
                st.error(f"Health check failed: {e}")
    
    # Job status grid
    if st.session_state.jobs:
        for job in st.session_state.jobs:
            status_emoji = "✅" if job["status"] == "healthy" else "❌" if job["status"] == "failed" else "❓"
            status_color = "#2ecc71" if job["status"] == "healthy" else "#e74c3c" if job["status"] == "failed" else "#95a5a6"
            
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
                        st.code(job['error_summary'][:400], language="python")
    else:
        st.info("Click 'Refresh Health' to check job status")

with col_right:
    st.subheader("🛡️ AEGIS Control")
    
    # Big run button
    run_btn = st.button(
        "▶️ Run AEGIS Workflow",
        type="primary",
        use_container_width=True,
        disabled=st.session_state.get("running", False),
        key="run_aegis"
    )
    
    if run_btn:
        st.session_state.running = True
        st.session_state.workflow_progress = []
        st.rerun()
    
    st.divider()
    
    # Configuration
    st.markdown("### ⚙️ Configuration")
    
    with st.expander("Databricks", expanded=False):
        db_host = os.environ.get("DATABRICKS_HOST", "Not configured")
        st.text(f"Host: {db_host[:40]}...")
        st.text(f"Job ID: {os.environ.get('DATABRICKS_JOB_ID', 'All jobs')}")
    
    with st.expander("LLM (GPT-4o)", expanded=False):
        llm_configured = bool(os.environ.get("DIAL_API_KEY"))
        st.text(f"Status: {'✅ Configured' if llm_configured else '❌ Not configured'}")
        st.text(f"Endpoint: {os.environ.get('DIAL_API_ENDPOINT', 'N/A')[:40]}...")
    
    with st.expander("GitHub", expanded=False):
        gh_configured = bool(os.environ.get("GITHUB_TOKEN"))
        st.text(f"Status: {'✅ Configured' if gh_configured else '❌ Not configured'}")
        owner = os.environ.get("GITHUB_REPO_OWNER", "N/A")
        repo = os.environ.get("GITHUB_REPO_NAME", "N/A")
        st.text(f"Repo: {owner}/{repo}")

st.divider()

# Workflow execution section
if st.session_state.get("running"):
    st.header("🚀 AEGIS Workflow Execution")
    
    # Progress stages
    stages = [
        ("status_check", "Status Check", "🔍"),
        ("initial_email", "Initial Email", "📧"),
        ("failure_alert", "Failure Alert", "⚠️"),
        ("fix_in_progress", "Fix in Progress", "🔧"),
        ("job_fixer", "Job Fixer", "🛠️"),
        ("fix_complete", "Fix Complete", "✅"),
        ("pr_create", "PR Creation", "📝"),
        ("pr_wait", "PR Approval", "⏳"),
        ("deployment", "Deployment", "🚀"),
        ("complete", "Complete", "🎉"),
    ]
    
    # Stage progress bar
    progress_cols = st.columns(len(stages))
    for idx, (stage_id, stage_name, emoji) in enumerate(stages):
        with progress_cols[idx]:
            if idx < len(st.session_state.workflow_progress):
                st.markdown(f'<div class="stage-complete">{emoji}<br>{stage_name}</div>', unsafe_allow_html=True)
            elif idx == len(st.session_state.workflow_progress):
                st.markdown(f'<div class="stage-active">{emoji}<br>{stage_name}</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="stage-pending">{emoji}<br>{stage_name}</div>', unsafe_allow_html=True)
    
    # Progress bar
    progress_pct = len(st.session_state.workflow_progress) / len(stages)
    st.progress(progress_pct)
    
    # Live logs
    st.subheader("📜 Live Execution Log")
    log_container = st.container()
    
    with log_container:
        # Simulate workflow execution (in real implementation, this would be the actual workflow)
        if len(st.session_state.workflow_progress) < len(stages):
            current_stage_idx = len(st.session_state.workflow_progress)
            current_stage = stages[current_stage_idx]
            
            st.info(f"⚙️ Executing: **{current_stage[1]}**")
            
            # Simulate progress
            time.sleep(2)
            st.session_state.workflow_progress.append(current_stage[0])
            
            # Log entry
            st.success(f"✅ {current_stage[1]} complete")
            
            # Auto-refresh
            time.sleep(1)
            st.rerun()
        else:
            # Workflow complete
            st.success("🎉 Workflow completed successfully!")
            
            # Results
            st.subheader("📊 Execution Results")
            
            res1, res2, res3 = st.columns(3)
            res1.metric("Incident ID", "INC-ABC123")
            res2.metric("MTTR", "90s")
            res3.metric("Status", "✅ Auto-Healed")
            
            if st.button("View PR", key="view_pr"):
                st.markdown("[🔗 GitHub Pull Request #42](https://github.com/uday2797/aegis/pull/42)")
            
            if st.button("🔄 Run Again", key="run_again"):
                st.session_state.running = False
                st.session_state.workflow_progress = []
                st.rerun()

# Analytics section
st.divider()
st.header("📈 Analytics & Insights")

chart_col1, chart_col2 = st.columns(2)

with chart_col1:
    st.subheader("MTTR Trend")
    
    # Create MTTR trend chart
    if st.session_state.incidents_history:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=[i["timestamp"] for i in st.session_state.incidents_history],
            y=[i["mttr"] for i in st.session_state.incidents_history],
            mode='lines+markers',
            name='MTTR',
            line=dict(color='#3a7bd5', width=3),
            marker=dict(size=10)
        ))
        fig.update_layout(
            title="Mean Time to Recovery",
            xaxis_title="Timestamp",
            yaxis_title="MTTR (seconds)",
            template="plotly_dark",
            height=300
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No incident history available")

with chart_col2:
    st.subheader("Incident Status Distribution")
    
    # Pie chart
    statuses = [i["status"] for i in st.session_state.incidents_history]
    status_counts = {status: statuses.count(status) for status in set(statuses)}
    
    fig = go.Figure(data=[go.Pie(
        labels=list(status_counts.keys()),
        values=list(status_counts.values()),
        hole=0.4,
        marker=dict(colors=['#2ecc71', '#e74c3c', '#f39c12'])
    )])
    fig.update_layout(
        title="Incident Outcomes",
        template="plotly_dark",
        height=300
    )
    st.plotly_chart(fig, use_container_width=True)

# Recent incidents table
st.subheader("🕒 Recent Incidents")
if st.session_state.incidents_history:
    for incident in st.session_state.incidents_history[-5:]:
        col_i1, col_i2, col_i3, col_i4 = st.columns([2, 2, 2, 1])
        col_i1.write(f"**{incident['id']}**")
        col_i2.write(incident['timestamp'])
        col_i3.write(f"{incident['mttr']}s MTTR")
        status_emoji = "✅" if incident['status'] == "healed" else "❌"
        col_i4.write(f"{status_emoji} {incident['status']}")
else:
    st.info("No incidents recorded yet")

# Footer
st.divider()
st.markdown("""
<div style='text-align: center; color: #888; padding: 2rem 0;'>
    <p><strong>AEGIS v2.0</strong> — Powered by LangGraph Multi-Agent Architecture</p>
    <p>AI-Engine for Guardian Intelligence & Self-healing</p>
</div>
""", unsafe_allow_html=True)
