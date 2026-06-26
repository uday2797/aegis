"""
AEGIS Production Dashboard - Real Databricks Integration
Light theme, real workflow execution, live progress
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

# Import AEGIS real components
from src.agents.status_checker import StatusCheckerAgent
from src.workflow import build_aegis_workflow, AEGISState

load_dotenv()

# Page config
st.set_page_config(
    page_title="AEGIS Production Dashboard",
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
if "workflow_result" not in st.session_state:
    st.session_state.workflow_result = None
if "incidents_history" not in st.session_state:
    st.session_state.incidents_history = []

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
    .log-entry {
        background: white;
        padding: 0.5rem;
        margin: 0.25rem 0;
        border-radius: 0.3rem;
        border-left: 4px solid #3498db;
        font-family: monospace;
    }
</style>
""", unsafe_allow_html=True)

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
        st.info(f"📍 Specific job: `{specific_job}`")
    else:
        dab_bundle = os.environ.get("DAB_BUNDLE_NAME", "aegis-de-project")
        st.info(f"📍 Bundle: `{dab_bundle}`")
    
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
        st.warning("⚠️ Configure Databricks in .env")
    
    if run_btn:
        st.session_state.workflow_running = True
        st.session_state.workflow_result = None
        st.rerun()

st.divider()

# Workflow execution section
if st.session_state.workflow_running:
    st.header("🚀 AEGIS Workflow Execution (LIVE)")
    
    progress_placeholder = st.empty()
    log_placeholder = st.empty()
    
    # Execute workflow
    try:
        with st.spinner("🚀 Executing AEGIS Multi-Agent Workflow..."):
            
            # Run workflow synchronously
            async def run_workflow():
                workflow = build_aegis_workflow()
                
                specific_job = os.environ.get("DATABRICKS_JOB_ID")
                dab_bundle = os.environ.get("DAB_BUNDLE_NAME", "aegis-de-project")
                monitor_all = not bool(specific_job)
                
                initial_state: AEGISState = {
                    "monitor_all_jobs": monitor_all,
                    "specific_job_id": specific_job,
                    "dab_bundle_name": dab_bundle,
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
                
                events = []
                async for event in workflow.astream(initial_state):
                    events.append(event)
                
                return events
            
            events = asyncio.run(run_workflow())
        
        # Process events
        logs = []
        final_state = None
        
        for event in events:
            for node_name, node_state in event.items():
                logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ {node_name}")
                final_state = node_state
                
                # Show progress
                progress_placeholder.info(f"⚙️ Executing: **{node_name}**")
        
        # Display logs
        with log_placeholder.container():
            st.subheader("📜 Execution Log")
            for log in logs:
                st.markdown(f'<div class="log-entry">{log}</div>', unsafe_allow_html=True)
        
        # Complete
        st.session_state.workflow_running = False
        st.session_state.workflow_result = final_state
        
        # Save to history
        if final_state and final_state.get("current_incident_id"):
            start = datetime.fromisoformat(final_state["start_time"])
            end = datetime.fromisoformat(final_state.get("end_time", datetime.now().isoformat()))
            mttr = int((end - start).total_seconds())
            
            st.session_state.incidents_history.append({
                "id": final_state["current_incident_id"],
                "mttr": mttr,
                "status": "healed" if final_state.get("deployment_status") == "success" else "escalated",
                "timestamp": start.strftime("%Y-%m-%d %H:%M"),
            })
        
        st.success("🎉 AEGIS Workflow completed!")
        
        # Show results
        if final_state:
            st.subheader("📊 Results")
            
            r1, r2, r3, r4 = st.columns(4)
            r1.metric("Incident", final_state.get("current_incident_id", "N/A"))
            
            if final_state.get("start_time") and final_state.get("end_time"):
                start = datetime.fromisoformat(final_state["start_time"])
                end = datetime.fromisoformat(final_state["end_time"])
                mttr = int((end - start).total_seconds())
                r2.metric("MTTR", f"{mttr}s")
            else:
                r2.metric("MTTR", "N/A")
            
            status = final_state.get("deployment_status", "unknown")
            r3.metric("Status", "✅ Healed" if status == "success" else "⚠️ Escalated")
            
            emails = len(final_state.get("emails_sent", []))
            r4.metric("Emails", emails)
            
            if final_state.get("pr_url"):
                st.markdown(f"**PR:** [{final_state['pr_url']}]({final_state['pr_url']})")
            
            if final_state.get("root_cause"):
                with st.expander("🔍 Root Cause"):
                    st.info(final_state["root_cause"])
            
            with st.expander("📧 Emails"):
                for email in final_state.get("emails_sent", []):
                    st.write(f"• {email}")
            
            with st.expander("🔍 Full State"):
                st.json(final_state)
        
    except Exception as e:
        st.session_state.workflow_running = False
        st.error(f"❌ Workflow failed: {e}")
        import traceback
        st.code(traceback.format_exc())
    
    # Rerun button
    if not st.session_state.workflow_running:
        if st.button("🔄 Run Again"):
            st.rerun()

# Analytics - only if we have history
if st.session_state.incidents_history:
    st.divider()
    st.header("📈 Analytics")

    c1, c2 = st.columns(2)

    with c1:
        st.subheader("MTTR Trend")
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=[i["timestamp"] for i in st.session_state.incidents_history],
            y=[i["mttr"] for i in st.session_state.incidents_history],
            mode='lines+markers',
            line=dict(color='#3498db', width=3),
            marker=dict(size=10)
        ))
        fig.update_layout(
            xaxis_title="Time",
            yaxis_title="MTTR (s)",
            template="plotly_white",
            height=300
        )
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        st.subheader("Status Distribution")
        statuses = [i["status"] for i in st.session_state.incidents_history]
        counts = {s: statuses.count(s) for s in set(statuses)}
        
        fig = go.Figure(data=[go.Pie(
            labels=list(counts.keys()),
            values=list(counts.values()),
            hole=0.4
        )])
        fig.update_layout(template="plotly_white", height=300)
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("🕒 Recent Incidents")
    for inc in st.session_state.incidents_history[-10:]:
        c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
        c1.write(f"**{inc['id']}**")
        c2.write(inc['timestamp'])
        c3.write(f"{inc['mttr']}s")
        c4.write(f"{'✅' if inc['status'] == 'healed' else '❌'} {inc['status']}")

# Footer
st.divider()
st.markdown("""
<div style='text-align: center; color: #34495e; padding: 2rem 0;'>
    <p><strong>AEGIS v2.0</strong> — Production Multi-Agent System</p>
    <p>Powered by LangGraph | GPT-4o | Real Databricks Integration</p>
</div>
""", unsafe_allow_html=True)
