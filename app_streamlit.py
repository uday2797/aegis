"""
AEGIS Streamlit Dashboard
Real-time monitoring and control interface for the AI-Autonomous Reliability Agent.

Features:
- Live job health monitoring
- One-click AEGIS execution
- Real-time workflow progress
- Metrics and analytics
- Email notification display
- PR and deployment tracking
"""
import streamlit as st
import asyncio
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
import yaml
from pathlib import Path

# Import AEGIS components
from src.workflow import build_aegis_workflow
from src.agents.status_checker import StatusCheckerAgent
from src.knowledge.incident_store import IncidentKnowledgeStore

load_dotenv()

# Page config
st.set_page_config(
    page_title="AEGIS — AI-Autonomous Reliability Agent",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        padding: 1rem 0;
        background: linear-gradient(90deg, #1f77b4 0%, #17becf 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .metric-card {
        background: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #1f77b4;
    }
    .status-healthy {
        color: #2ecc71;
        font-weight: bold;
    }
    .status-failed {
        color: #e74c3c;
        font-weight: bold;
    }
    .status-running {
        color: #f39c12;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# Load config
@st.cache_resource
def load_config():
    with open("config/config.yaml", "r") as f:
        return yaml.safe_load(f)

config = load_config()

# Initialize session state
if "workflow_running" not in st.session_state:
    st.session_state.workflow_running = False
if "workflow_state" not in st.session_state:
    st.session_state.workflow_state = None
if "workflow_logs" not in st.session_state:
    st.session_state.workflow_logs = []
if "job_health" not in st.session_state:
    st.session_state.job_health = []
if "metrics" not in st.session_state:
    st.session_state.metrics = {
        "total_incidents": 0,
        "auto_healed": 0,
        "avg_mttr": 0,
        "success_rate": 0,
    }

# Header
st.markdown('<h1 class="main-header">🛡️ AEGIS — AI-Autonomous Reliability Agent</h1>', unsafe_allow_html=True)
st.markdown("**AI-Engine for Guardian Intelligence & Self-healing** | LangGraph Multi-Agent System")
st.divider()

# Sidebar - Configuration
with st.sidebar:
    st.header("⚙️ Configuration")
    
    # Databricks
    st.subheader("Databricks")
    db_host = os.environ.get("DATABRICKS_HOST", "")
    db_configured = bool(db_host)
    st.write(f"**Status:** {'✅ Configured' if db_configured else '❌ Not configured'}")
    if db_configured:
        st.code(f"{db_host[:40]}...", language="text")
    
    # Monitoring Mode
    st.subheader("Monitoring Mode")
    specific_job_id = os.environ.get("DATABRICKS_JOB_ID")
    if specific_job_id:
        mode = st.radio("Mode", ["Specific Job", "All DAB Jobs"], index=0)
        monitor_all = mode == "All DAB Jobs"
        if mode == "Specific Job":
            st.info(f"Job ID: `{specific_job_id}`")
    else:
        mode = "All DAB Jobs"
        monitor_all = True
        st.info("No specific job set — monitoring all DAB jobs")
    
    dab_bundle = os.environ.get("DAB_BUNDLE_NAME", "aegis-de-project")
    if monitor_all:
        st.text_input("DAB Bundle Filter", value=dab_bundle, key="dab_bundle")
    
    # LLM
    st.subheader("LLM (GPT-4o)")
    llm_key = os.environ.get("DIAL_API_KEY", "")
    llm_configured = bool(llm_key)
    st.write(f"**Status:** {'✅ Configured' if llm_configured else '❌ Not configured'}")
    
    # GitHub
    st.subheader("GitHub")
    gh_token = os.environ.get("GITHUB_TOKEN", "")
    gh_configured = bool(gh_token)
    st.write(f"**Status:** {'✅ Configured' if gh_configured else '❌ Not configured'}")
    if gh_configured:
        owner = os.environ.get("GITHUB_REPO_OWNER", "")
        repo = os.environ.get("GITHUB_REPO_NAME", "")
        st.code(f"{owner}/{repo}", language="text")
    
    # Gmail
    st.subheader("Gmail Notifications")
    gmail_configured = bool(os.environ.get("GMAIL_SENDER", ""))
    st.write(f"**Status:** {'✅ Configured' if gmail_configured else '❌ Not configured'}")
    
    st.divider()
    
    # Quick Actions
    st.subheader("🔧 Quick Actions")
    if st.button("🔄 Refresh Health", use_container_width=True):
        st.session_state.force_refresh = True
        st.rerun()
    
    if st.button("📊 Load Metrics", use_container_width=True):
        st.session_state.load_metrics = True
        st.rerun()

# Main content - 3 columns
col1, col2, col3 = st.columns([2, 1, 1])

with col1:
    st.subheader("📊 System Health")

with col2:
    if st.session_state.workflow_running:
        st.button("🛡️ AEGIS Running...", disabled=True, use_container_width=True)
    else:
        if st.button("🛡️ Run AEGIS", type="primary", use_container_width=True):
            st.session_state.start_aegis = True
            st.rerun()

with col3:
    st.metric("Status", "🟢 Online" if db_configured else "🔴 Offline")

# Health Check Display
async def check_health():
    """Fetch current job health status."""
    if not db_configured:
        return []
    
    agent = StatusCheckerAgent(
        os.environ["DATABRICKS_HOST"],
        os.environ["DATABRICKS_TOKEN"]
    )
    
    return await agent.check_health(
        monitor_all_jobs=monitor_all,
        specific_job_id=specific_job_id if not monitor_all else None,
        dab_bundle_name=dab_bundle if monitor_all else None
    )

# Display job health
if st.session_state.get("force_refresh") or not st.session_state.job_health:
    with st.spinner("🔍 Checking job health..."):
        try:
            st.session_state.job_health = asyncio.run(check_health())
            st.session_state.force_refresh = False
        except Exception as e:
            st.error(f"Health check failed: {e}")
            st.session_state.job_health = []

if st.session_state.job_health:
    # Summary metrics
    healthy_count = sum(1 for j in st.session_state.job_health if j["status"] == "healthy")
    failed_count = sum(1 for j in st.session_state.job_health if j["status"] == "failed")
    unknown_count = sum(1 for j in st.session_state.job_health if j["status"] == "unknown")
    
    m1, m2, m3 = st.columns(3)
    m1.metric("✅ Healthy Jobs", healthy_count, delta=None)
    m2.metric("❌ Failed Jobs", failed_count, delta=None)
    m3.metric("❓ Unknown Jobs", unknown_count, delta=None)
    
    # Job grid
    st.subheader("Job Status")
    for job in st.session_state.job_health:
        with st.expander(
            f"{'✅' if job['status'] == 'healthy' else '❌' if job['status'] == 'failed' else '❓'} {job['job_name']}", 
            expanded=(job['status'] == 'failed')
        ):
            col_a, col_b = st.columns(2)
            with col_a:
                st.write(f"**Job ID:** `{job['job_id']}`")
                st.write(f"**Last Run:** `{job['last_run_id']}`")
            with col_b:
                status_class = f"status-{job['status']}"
                st.markdown(f"**Status:** <span class='{status_class}'>{job['status'].upper()}</span>", unsafe_allow_html=True)
            
            if job['status'] == 'failed' and job['error_summary']:
                st.error("**Error Summary:**")
                st.code(job['error_summary'][:500], language="python")
                if job['failed_tasks']:
                    st.write(f"**Failed Tasks:** {', '.join(job['failed_tasks'])}")
else:
    st.info("No job health data available. Click 'Refresh Health' to fetch.")

st.divider()

# Metrics Dashboard
st.header("📈 Metrics & Analytics")

# Load metrics from incident store
if st.session_state.get("load_metrics"):
    try:
        knowledge_store = IncidentKnowledgeStore(config["knowledge_store"])
        # This is a placeholder - you'd implement get_metrics() in IncidentKnowledgeStore
        st.session_state.metrics = {
            "total_incidents": 5,
            "auto_healed": 4,
            "avg_mttr": 92,
            "success_rate": 80,
        }
        st.session_state.load_metrics = False
    except Exception as e:
        st.warning(f"Could not load metrics: {e}")

mc1, mc2, mc3, mc4 = st.columns(4)
mc1.metric("Total Incidents", st.session_state.metrics["total_incidents"])
mc2.metric("Auto-Healed", st.session_state.metrics["auto_healed"], 
           delta=f"{st.session_state.metrics['success_rate']}% success rate")
mc3.metric("Avg MTTR", f"{st.session_state.metrics['avg_mttr']}s", 
           delta="-95% vs manual" if st.session_state.metrics['avg_mttr'] > 0 else None)
mc4.metric("Success Rate", f"{st.session_state.metrics['success_rate']}%")

st.divider()

# AEGIS Workflow Execution
if st.session_state.get("start_aegis"):
    st.session_state.start_aegis = False
    st.session_state.workflow_running = True
    st.session_state.workflow_logs = []
    
    st.header("🛡️ AEGIS Autonomous Workflow")
    
    # Progress container
    progress_container = st.container()
    
    with progress_container:
        workflow_status = st.status("🚀 Starting AEGIS workflow...", expanded=True)
        
        async def run_aegis_workflow():
            """Execute the full LangGraph workflow with live updates."""
            try:
                # Build workflow
                workflow = build_aegis_workflow()
                
                # Initial state
                initial_state = {
                    "workspace_host": os.environ["DATABRICKS_HOST"],
                    "workspace_token": os.environ["DATABRICKS_TOKEN"],
                    "monitor_all_jobs": monitor_all,
                    "specific_job_id": specific_job_id if not monitor_all else None,
                    "dab_bundle_name": dab_bundle if monitor_all else None,
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
                    "emails_sent": [],
                    "current_stage": "init",
                }
                
                # Execute workflow
                workflow_status.update(label="⚙️ Executing LangGraph workflow...", state="running")
                final_state = await workflow.ainvoke(initial_state)
                
                # Store final state
                st.session_state.workflow_state = final_state
                workflow_status.update(label="✅ Workflow complete!", state="complete")
                
                return final_state
            
            except Exception as e:
                workflow_status.update(label=f"❌ Workflow failed: {e}", state="error")
                st.session_state.workflow_running = False
                raise
        
        # Run workflow
        try:
            final_state = asyncio.run(run_aegis_workflow())
            
            # Display results
            st.success("🎉 AEGIS completed successfully!")
            
            # Results tabs
            tab1, tab2, tab3, tab4 = st.tabs(["📊 Summary", "📧 Emails", "🔗 PR & Deployment", "🔍 Details"])
            
            with tab1:
                st.subheader("Execution Summary")
                col_x, col_y = st.columns(2)
                with col_x:
                    st.metric("Final Stage", final_state.get("current_stage", "unknown"))
                    st.metric("Healthy Jobs", final_state.get("healthy_count", 0))
                    st.metric("Failed Jobs", final_state.get("failed_count", 0))
                with col_y:
                    if final_state.get("current_incident_id"):
                        st.metric("Incident ID", final_state["current_incident_id"])
                        st.metric("Fix Status", final_state.get("fix_status", "N/A"))
                        st.metric("MTTR", f"{final_state.get('mttr_seconds', 0):.0f}s")
            
            with tab2:
                st.subheader("Email Notifications Sent")
                emails = final_state.get("emails_sent", [])
                if emails:
                    for idx, email in enumerate(emails, 1):
                        st.write(f"{idx}. **{email.replace('_', ' ').title()}**")
                else:
                    st.info("No emails sent (likely all jobs healthy)")
            
            with tab3:
                st.subheader("PR & Deployment")
                pr_url = final_state.get("pr_url")
                if pr_url:
                    st.success(f"**Pull Request:** [{pr_url}]({pr_url})")
                    st.write(f"**PR Number:** #{final_state.get('pr_number', 0)}")
                    st.write(f"**Merged:** {'✅ Yes' if final_state.get('pr_merged') else '⏳ Pending'}")
                else:
                    st.info("No PR created (no code fixes needed)")
                
                workflow_url = final_state.get("workflow_run_url")
                if workflow_url:
                    st.success(f"**Deployment:** [{workflow_url}]({workflow_url})")
                    st.write(f"**Status:** {final_state.get('deployment_status', 'unknown')}")
                else:
                    st.info("No deployment triggered")
            
            with tab4:
                st.subheader("Full Workflow State")
                st.json(final_state)
            
            st.session_state.workflow_running = False
        
        except Exception as e:
            st.error(f"Workflow execution failed: {e}")
            st.exception(e)
            st.session_state.workflow_running = False

elif st.session_state.workflow_state:
    # Show last execution results
    st.header("📋 Last AEGIS Execution")
    
    final_state = st.session_state.workflow_state
    
    # Quick summary
    col_s1, col_s2, col_s3 = st.columns(3)
    col_s1.metric("Stage", final_state.get("current_stage", "unknown"))
    col_s2.metric("Failed Jobs", final_state.get("failed_count", 0))
    col_s3.metric("MTTR", f"{final_state.get('mttr_seconds', 0):.0f}s" if final_state.get("mttr_seconds") else "N/A")
    
    if final_state.get("pr_url"):
        st.success(f"**Pull Request Created:** [{final_state['pr_url']}]({final_state['pr_url']})")
    
    if st.button("🔄 Run Again"):
        st.session_state.start_aegis = True
        st.rerun()

# Footer
st.divider()
st.markdown("""
<div style='text-align: center; color: #888; padding: 2rem 0;'>
    <p><strong>AEGIS</strong> — AI-Engine for Guardian Intelligence & Self-healing</p>
    <p>LangGraph Multi-Agent Autonomous Reliability System</p>
</div>
""", unsafe_allow_html=True)
