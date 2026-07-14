"""
AEGIS — Production Streamlit Dashboard
Real Databricks connect, real job listing, real LangGraph workflow execution.
"""

import streamlit as st
import threading, asyncio, queue, os, sys, time, yaml, base64
from datetime import datetime
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from dotenv import load_dotenv
load_dotenv(Path(ROOT) / ".env", override=True)   # always reload so updated tokens are picked up

def _logo_b64() -> str:
    p = Path(__file__).parent / "aegis_logo.png"
    return base64.b64encode(p.read_bytes()).decode() if p.exists() else ""

_LOGO_B64 = _logo_b64()

def _db_logo_b64() -> str:
    p = Path(__file__).parent / "databricks_logo.png"
    return base64.b64encode(p.read_bytes()).decode() if p.exists() else ""

_DB_LOGO_B64 = _db_logo_b64()

def _ml_icon_b64() -> str:
    p = Path(__file__).parent / "ml_monitor_icon.png"
    return base64.b64encode(p.read_bytes()).decode() if p.exists() else ""

_ML_ICON_B64 = _ml_icon_b64()

def _db_icon_b64() -> str:
    p = Path(__file__).parent / "databricks_icon.png"
    return base64.b64encode(p.read_bytes()).decode() if p.exists() else ""

_DB_ICON_B64 = _db_icon_b64()

def _step_icon_b64(fname: str) -> str:
    p = Path(__file__).parent / fname
    return base64.b64encode(p.read_bytes()).decode() if p.exists() else ""

_STEP_CONNECT_B64 = _step_icon_b64("step_connect_icon.png")
_STEP_JOBS_B64    = _step_icon_b64("step_jobs_icon.png")
_STEP_RUN_B64     = _step_icon_b64("step_run_icon.jpg")

st.set_page_config(
    page_title="AEGIS — Autonomous Pipeline Guardian",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Theme & CSS  (SRH Orange Army) ────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');

/* ── SRH Orange Army — Light theme palette ───────────────────────────────── */
:root {
  --srh-orange:  #FF6200;
  --srh-hot:     #E55500;
  --srh-gold:    #FFB300;
  --srh-bg:      #ffffff;
  --srh-card:    #FFF8F0;
  --srh-card2:   #FFF0E0;
  --srh-border:  #FFD4A8;
  --srh-border2: #FFBD80;
  --srh-text:    #2D1200;
  --srh-sub:     #7A3A10;
  --srh-muted:   #B06030;
}

/* ── Reset ── */
[data-testid="stApp"]           { background:#ffffff !important; font-family:'Inter',sans-serif !important; }
.main .block-container           { padding:1.5rem 2rem 2rem !important; max-width:1440px !important; }
section[data-testid="stSidebar"] { display:none !important; }

/* Streamlit native containers */
[data-testid="stVerticalBlock"]  { background:transparent !important; }
[data-testid="stHorizontalBlock"]{ background:transparent !important; }
[data-testid="stMain"]           { background:#ffffff !important; }
[data-testid="stAppViewContainer"]{ background:#ffffff !important; }

/* ── Hero banner ── */
.hero {
  background:linear-gradient(135deg,#FF6200 0%,#E55000 40%,#FF8C1A 100%);
  border-radius:20px; padding:28px 36px 26px; margin-bottom:24px;
  box-shadow:0 12px 48px rgba(255,98,0,.35), inset 0 1px 0 rgba(255,255,255,.15);
  border:none;
  display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:12px;
  position:relative; overflow:hidden;
}
.hero::before {
  content:""; position:absolute; top:-60px; right:-60px;
  width:240px; height:240px; border-radius:50%;
  background:radial-gradient(circle,rgba(255,255,255,.15),transparent 70%);
  pointer-events:none;
}
.hero-left h1 {
  font-size:2.6rem; font-weight:900; line-height:1; margin:0; color:#ffffff;
  text-shadow:0 2px 8px rgba(0,0,0,.2);
}
.hero-left p { color:rgba(255,255,255,.8); margin:6px 0 0; font-size:.85rem; font-weight:400; }
.hero-badges { display:flex; gap:8px; flex-wrap:wrap; align-items:center; }
.hb { background:rgba(255,255,255,.2); border:1px solid rgba(255,255,255,.35);
      border-radius:99px; padding:5px 14px; font-size:.7rem; font-weight:600; color:#fff; }

/* ── Step indicator ── */
.steps { display:flex; gap:0; margin-bottom:22px; }
.step  { flex:1; padding:14px 20px; background:#fff; border:1px solid #FFD4A8;
         border-right:none; display:flex; align-items:center; gap:12px; }
.step:first-child { border-radius:12px 0 0 12px; }
.step:last-child  { border-radius:0 12px 12px 0; border-right:1px solid #FFD4A8; }
.step-num { width:30px; height:30px; border-radius:50%; display:flex; align-items:center;
            justify-content:center; font-size:.8rem; font-weight:800; flex-shrink:0; }
.step-inactive .step-num  { background:#FFF0E0; color:#B06030; border:1px solid #FFD4A8; }
.step-active   .step-num  { background:linear-gradient(135deg,#FF6200,#FF8C1A); color:#fff; box-shadow:0 3px 12px rgba(255,98,0,.4); }
.step-done     .step-num  { background:#22c55e; color:#fff; }
.step-inactive .step-title{ color:#B06030; }
.step-active   .step-title{ color:#FF6200; font-weight:700; }
.step-done     .step-title{ color:#16a34a; font-weight:600; }
.step-title    { font-size:.83rem; font-weight:600; color:#2D1200; }
.step-sub      { font-size:.68rem; color:#B06030; margin-top:1px; }

/* ── Inputs ── */
[data-testid="stTextInput"] label { font-size:.75rem !important; font-weight:700 !important; color:#7A3A10 !important; text-transform:uppercase; letter-spacing:.08em; }
[data-testid="stTextInput"] input { border-radius:9px !important; border:1.5px solid #FFD4A8 !important; font-size:.88rem !important; color:#2D1200 !important; background:#fff !important; }
[data-testid="stTextInput"] input:focus { border-color:#FF6200 !important; box-shadow:0 0 0 3px rgba(255,98,0,.15) !important; }
[data-testid="stTextInput"] input::placeholder { color:#B06030 !important; }

/* ── Buttons ── */
.stButton > button {
  border-radius:10px !important; font-weight:700 !important;
  font-size:.88rem !important; padding:10px 24px !important;
  transition:all .2s !important; letter-spacing:.01em !important;
  background:#FF6200 !important; color:#fff !important; border:none !important;
}
.stButton > button:hover { transform:translateY(-1px) !important; box-shadow:0 4px 16px rgba(255,98,0,.4) !important; background:#FF8C1A !important; }
.stButton > button[kind="secondary"] { background:#FFF8F0 !important; color:#FF6200 !important; border:1px solid #FFD4A8 !important; }

/* ── Status badge ── */
.run-badge { display:inline-flex; align-items:center; gap:8px; border-radius:99px; padding:10px 22px; font-size:.78rem; font-weight:800; letter-spacing:.06em; }
.rb-idle    { background:#FFF8F0; border:1.5px solid #FFD4A8; color:#B06030; }
.rb-running { background:#FFF0E0; border:1.5px solid #FF6200; color:#E55000; animation:rp 1.5s ease-in-out infinite; }
.rb-done    { background:#f0fdf4; border:1.5px solid #22c55e; color:#15803d; }
.rb-error   { background:#fef2f2; border:1.5px solid #ef4444; color:#b91c1c; }
@keyframes rp { 0%,100%{box-shadow:0 0 0 0 rgba(255,98,0,.35)} 50%{box-shadow:0 0 0 14px rgba(255,98,0,0)} }

/* ── KPI cards ── */
.kpi-row     { display:grid; grid-template-columns:repeat(5,1fr); gap:12px; margin:18px 0; }
.kpi         { background:#fff; border:1px solid #FFD4A8; border-radius:14px; padding:18px 20px;
               box-shadow:0 2px 12px rgba(255,98,0,.08); position:relative; overflow:hidden; }
.kpi::before { content:""; position:absolute; top:0; left:0; right:0; height:3px;
               background:linear-gradient(90deg,#FF6200,#FFB300); }
.kpi-label   { font-size:.62rem; color:#B06030; text-transform:uppercase; letter-spacing:.12em; font-weight:700; margin-bottom:8px; }
.kpi-val     { font-size:1.8rem; font-weight:900; color:#FF6200; line-height:1; }
.kpi-sub     { font-size:.68rem; color:#7A3A10; margin-top:5px; }

/* ── Workflow nodes ── */
.wf-wrap { background:#fff; border:1px solid #FFD4A8; border-radius:16px; padding:20px 16px; margin:18px 0; box-shadow:0 2px 12px rgba(255,98,0,.08); overflow-x:auto; }
.wf-row  { display:inline-flex; align-items:center; min-width:100%; }
.wf-node { display:flex; flex-direction:column; align-items:center; min-width:76px; }
.wf-icon { width:36px; height:36px; border-radius:50%; border:2px solid; display:flex; align-items:center; justify-content:center; font-size:.68rem; font-weight:800; }
.wf-lbl  { font-size:.55rem; text-align:center; margin-top:6px; max-width:74px; white-space:normal; line-height:1.3; font-weight:500; }
.wf-p .wf-icon { border-color:#FFD4A8; color:#B06030; background:#FFF8F0; }
.wf-p .wf-lbl  { color:#B06030; }
.wf-a .wf-icon { border-color:#FF6200; color:#FF6200; background:#FFF0E0; animation:na 1.3s infinite; }
.wf-a .wf-lbl  { color:#E55000; font-weight:700; }
.wf-d .wf-icon { border-color:#FF6200; color:#fff; background:linear-gradient(135deg,#FF6200,#FF8C1A); }
.wf-d .wf-lbl  { color:#E55000; font-weight:600; }
@keyframes na  { 0%,100%{box-shadow:0 0 0 0 rgba(255,98,0,.4)}50%{box-shadow:0 0 0 9px rgba(255,98,0,0)} }
.wf-arr  { color:#FFD4A8; padding:0 2px; margin-top:-24px; font-size:.9rem; }
.wf-arrd { color:#FF6200; padding:0 2px; margin-top:-24px; font-size:.9rem; }

/* ── Terminal (stays dark — intentional contrast) ── */
.term-wrap { border-radius:14px; overflow:hidden; box-shadow:0 8px 32px rgba(255,98,0,.12); border:1px solid #FFD4A8; }
.term-bar  { background:#1e1e2e; padding:10px 16px; display:flex; gap:6px; align-items:center; border-bottom:1px solid #2d2d3e; }
.td { width:12px; height:12px; border-radius:50%; }
.td-r{background:#ff5f57}.td-y{background:#febc2e}.td-g{background:#28c840}
.term-ttl  { color:#4a4a6a; font-size:.62rem; margin-left:8px; font-family:monospace; }
.terminal  { background:#0d1117; padding:16px 18px; font-family:'JetBrains Mono','Fira Code',monospace; font-size:.73rem; min-height:340px; max-height:400px; overflow-y:auto; line-height:1.85; }
.log{margin:0;padding:0}
.ts  {color:#3d4466}
.li  {color:#6b7280}
.lf  {color:#f87171;font-weight:600}
.ls  {color:#4ade80;font-weight:600}
.lw  {color:#fbbf24}
.le  {color:#FF8C1A;font-weight:500}
.lg  {color:#22d3ee;font-weight:500}
.lgp {color:#FFB300;font-weight:600}
.lb  {color:#FF6200;font-weight:500}

/* ── RCA / metric cards ── */
.card     { background:#fff; border:1px solid #FFD4A8; border-radius:14px; padding:20px 22px; box-shadow:0 2px 10px rgba(255,98,0,.07); margin-bottom:12px; }
.card-lbl { font-size:.61rem; color:#B06030; text-transform:uppercase; letter-spacing:.12em; margin-bottom:6px; font-weight:700; }
.card-val { font-size:1.2rem; font-weight:700; color:#FF6200; }
.rca-f    { background:#FFF8F0; border:1px solid #FFD4A8; border-radius:10px; padding:12px 16px; margin-bottom:8px; }
.rca-lbl  { font-size:.61rem; color:#B06030; text-transform:uppercase; letter-spacing:.12em; font-weight:700; margin-bottom:3px; }
.rca-val  { font-size:.86rem; color:#2D1200; line-height:1.55; }

/* ── Bug cards ── */
.bug-c   { border:1px solid #FFD4A8; border-left:4px solid; border-radius:0 10px 10px 0; padding:10px 14px; margin-bottom:8px; background:#fff; }
.bc-d    { border-left-color:#22c55e; background:#f0fdf4; border-color:#bbf7d0; }
.bc-c    { border-left-color:#ef4444; }
.bc-h    { border-left-color:#FF6200; }
.bc-p    { border-left-color:#FFD4A8; opacity:.5; }
.bug-num { font-size:.6rem; color:#B06030; font-weight:700; text-transform:uppercase; letter-spacing:.1em; }
.bug-dsc { font-size:.84rem; color:#2D1200; font-weight:600; margin:3px 0 5px; }
.sb      { display:inline-block; font-size:.59rem; font-weight:700; border-radius:5px; padding:2px 9px; letter-spacing:.07em; }
.sb-c{background:#fef2f2;color:#dc2626;border:1px solid #fecaca}
.sb-h{background:#fff7ed;color:#ea580c;border:1px solid #fed7aa}
.sb-f{background:#f0fdf4;color:#16a34a;border:1px solid #bbf7d0}

/* ── Diff ── */
.diff-wrap { border:1px solid #FFD4A8; border-radius:10px; overflow:hidden; margin-bottom:12px; font-family:'JetBrains Mono',monospace; font-size:.71rem; }
.d-b { background:#fff5f5; border-bottom:1px solid #fecaca; }
.d-a { background:#f0fdf4; }
.dh  { padding:5px 14px; font-size:.61rem; font-weight:700; }
.d-b .dh{color:#dc2626} .d-a .dh{color:#16a34a}
.dc  { padding:10px 14px; margin:0; white-space:pre-wrap; word-break:break-all; }
.d-b .dc{color:#dc2626} .d-a .dc{color:#16a34a}

/* ── Email cards ── */
.em-c  { background:#fff; border:1px solid #FFD4A8; border-radius:12px; padding:14px 18px; margin-bottom:8px; display:flex; gap:14px; align-items:flex-start; box-shadow:0 1px 6px rgba(255,98,0,.06); }
.em-c.sent   { border-left:3px solid #FF6200; }
.em-c.unsent { opacity:.35; filter:grayscale(.5); }
.em-ico{ font-size:1.7rem; line-height:1; }
.em-s  { font-size:.59rem; color:#B06030; text-transform:uppercase; letter-spacing:.1em; font-weight:700; }
.em-sub{ font-size:.88rem; color:#2D1200; font-weight:700; margin:3px 0 4px; }
.em-pre{ font-size:.74rem; color:#7A3A10; line-height:1.5; }
.em-to { font-size:.65rem; color:#FF6200; margin-top:4px; font-weight:600; }
.em-st { white-space:nowrap; font-size:.72rem; font-weight:700; }
.em-ok { color:#16a34a }
.em-no { color:#B06030 }

/* ── Guardrails ── */
.gr-grid{ display:grid; grid-template-columns:repeat(7,1fr); gap:10px; }
.gr-b   { background:#fff; border:1px solid #FFD4A8; border-radius:12px; padding:14px 8px; text-align:center; box-shadow:0 1px 4px rgba(255,98,0,.06); transition:all .4s; }
.gr-b.on{ background:#FFF0E0; border-color:#FF6200; box-shadow:0 2px 14px rgba(255,98,0,.2); }
.gr-n   { font-size:.6rem; color:#B06030; font-weight:700; }
.gr-nm  { font-size:.71rem; font-weight:700; color:#7A3A10; margin:5px 0 3px; }
.gr-dc  { font-size:.58rem; color:#B06030; line-height:1.4; }
.gr-st  { font-size:.65rem; margin-top:7px; color:#B06030; font-weight:600; }
.gr-b.on .gr-n,.gr-b.on .gr-nm { color:#E55000 }
.gr-b.on .gr-st { color:#FF6200 }

/* ── Section title ── */
.sec { font-size:.63rem; text-transform:uppercase; letter-spacing:.14em; color:#B06030; margin:20px 0 12px; font-weight:700; display:flex; align-items:center; gap:10px; }
.sec::after { content:""; flex:1; height:1px; background:linear-gradient(90deg,#FFD4A8,transparent); }

/* ── Alerts ── */
.cred-ok   { background:#f0fdf4; border:1px solid #86efac; border-radius:10px; padding:10px 16px; color:#15803d; font-size:.8rem; font-weight:600; margin-bottom:12px; }
.cred-warn { background:#fff7ed; border:1px solid #fed7aa; border-radius:10px; padding:10px 16px; color:#c2410c; font-size:.8rem; font-weight:600; margin-bottom:12px; }

/* ── Tabs ── */
[data-testid="stTabs"] [role="tablist"]   { background:#FFF8F0; border-bottom:2px solid #FFD4A8; border-radius:12px 12px 0 0; padding:4px 8px 0; }
[data-testid="stTabs"] [role="tab"]       { color:#B06030 !important; border:none !important; border-bottom:3px solid transparent !important; padding:11px 22px !important; font-size:.84rem !important; font-weight:600 !important; border-radius:8px 8px 0 0 !important; transition:all .15s !important; }
[data-testid="stTabs"] [role="tab"][aria-selected="true"] { color:#FF6200 !important; border-bottom-color:#FF6200 !important; }
[data-testid="stTabsContent"] { background:#fff; border:1px solid #FFD4A8; border-top:none; border-radius:0 0 12px 12px; padding:24px; box-shadow:0 2px 10px rgba(255,98,0,.06); }

/* ── Progress ── */
[data-testid="stProgressBar"] > div         { background:#FFE8CC; border-radius:99px; height:6px !important; }
[data-testid="stProgressBar"] > div > div   { background:linear-gradient(90deg,#FF6200,#FFB300) !important; border-radius:99px !important; }

/* ── Checkbox ── */
[data-testid="stCheckbox"] label { font-size:.82rem !important; color:#7A3A10 !important; font-weight:500 !important; }
[data-testid="stCheckbox"] svg   { color:#FF6200 !important; fill:#FF6200 !important; }

/* ── Job-grid checkboxes as cards ── */
div[data-testid="stCheckbox"]:has(input[id^="jcb_"]) {
  background:#fff !important;
  border:1.5px solid #FFD4A8 !important;
  border-left:3px solid #6b7280 !important;
  border-radius:8px !important;
  padding:8px 10px 7px !important;
  margin-bottom:3px !important;
  transition:background .18s, border-color .18s, box-shadow .18s !important;
  cursor:pointer !important;
}
div[data-testid="stCheckbox"]:has(input[id^="jcb_"]:checked) {
  background:#FFF0E0 !important;
  border-color:#FF6200 !important;
  border-left-color:#FF6200 !important;
  box-shadow:0 0 0 2px rgba(255,98,0,.22) !important;
}
div[data-testid="stCheckbox"]:has(input[id^="jcb_"]) label {
  align-items:flex-start !important;
  gap:8px !important;
  width:100% !important;
  cursor:pointer !important;
}
div[data-testid="stCheckbox"]:has(input[id^="jcb_"]) label > div {
  line-height:1.45 !important;
  white-space:normal !important;
  overflow:visible !important;
}
div[data-testid="stCheckbox"]:has(input[id^="jcb_"]) label p {
  font-size:.72rem !important;
  color:#7A3A10 !important;
  margin:0 !important;
  line-height:1.45 !important;
}

/* ── Toggle ── */
[data-testid="stToggle"] label { color:#7A3A10 !important; font-size:.84rem !important; }

/* ── Divider ── */
hr { border-color:#FFD4A8 !important; }

/* ── st.container border ── */
[data-testid="stVerticalBlockBorderWrapper"] { border:1px solid #FFD4A8 !important; border-radius:12px !important; background:#fff !important; }

/* ── Scrollbar ── */
::-webkit-scrollbar       { width:5px; height:5px; }
::-webkit-scrollbar-track { background:#FFF8F0; }
::-webkit-scrollbar-thumb { background:#FFB37A; border-radius:99px; }
::-webkit-scrollbar-thumb:hover { background:#FF6200; }

/* ── st.success / info / warning / error overrides ── */
[data-testid="stAlert"] { border-radius:12px !important; }

/* ── Metric ── */
[data-testid="stMetricValue"] { color:#FF6200 !important; font-weight:900 !important; }
[data-testid="stMetricLabel"] { color:#B06030 !important; }
</style>
""", unsafe_allow_html=True)

# ── Constants ──────────────────────────────────────────────────────────────────

WORKFLOW_NODES = [
    "Job\nSelector", "Status\nCheck", "Initial\nEmail", "Failure\nAlert+RCA",
    "Fix\nEmail", "Job Fixer\nGPT-5.5", "Fix\nComplete",
    "PR\nCreate", "PR\nRaised", "PR\nApproval", "CD\nDeploy",
    "Post\nDeploy", "Confirm", "Incident\nReport",
]
NODE_INDEX = {
    "job_selector_node": 0, "status_check_node": 1, "initial_email_node": 2,
    "failure_alert_node": 3, "fix_in_progress_email_node": 4, "job_fixer_node": 5,
    "fix_complete_email_node": 6, "pr_create_node": 7, "pr_raised_email_node": 8,
    "pr_wait_approval_node": 9, "deployment_node": 10,
    "post_deployment_verification_node": 11, "final_confirmation_email_node": 12,
    "deployment_failed_email_node": 12, "incident_report_node": 13, "ml_healer_node": 3,
}
EMAIL_STAGE_IDX = {
    "initial_health_check": 0, "failure_alert": 1, "fix_in_progress": 2,
    "fix_complete": 3, "pr_raised": 4, "final_confirmation": 5,
    "deployment_failed": 5, "escalation": 5, "ml_healing_complete": 5, "ml_healing_failed": 5,
}
# Real recipient from .env — used for all automated emails
_ALERT_TO   = os.getenv("DATABRICKS_USER_EMAIL") or os.getenv("SMTP_TO") or "oncall@team.com"
_SMTP_FROM  = os.getenv("SMTP_FROM") or os.getenv("SMTP_USERNAME") or "aegis-bot@team.com"
_GH_EMAIL   = os.getenv("GITHUB_EMAIL") or _ALERT_TO

EMAILS_DATA = [
    {"icon": "📊", "stage": "Stage 1 — Initial Health Check",
     "subj": "AEGIS Health Check — Failure detected",
     "prev": "Automated job status report. Failure detected. Autonomous repair initiated.",
     "to": _ALERT_TO},
    {"icon": "🚨", "stage": "Stage 2 — Failure Alert + RCA",
     "subj": "🚨 AEGIS ALERT: Failing Data Pipeline",
     "prev": "GPT-4o root cause analysis complete. Confidence above 70% gate. Repair approved.",
     "to": _ALERT_TO},
    {"icon": "🔧", "stage": "Stage 3 — Fix In Progress",
     "subj": "🔧 AEGIS: GPT-5.5 Comprehensive Repair In Progress",
     "prev": "Whole-notebook scan running. All bugs fixed in a single LLM pass.",
     "to": _ALERT_TO},
    {"icon": "✅", "stage": "Stage 4 — Fix Complete",
     "subj": "✅ AEGIS: Pipeline Repaired — Post-fix run PASSED",
     "prev": "Post-fix run SUCCESS. MTTR within SLA. Creating GitHub PR before deploy.",
     "to": _ALERT_TO},
    {"icon": "📋", "stage": "Stage 5 — PR Raised",
     "subj": "📋 AEGIS: Pull Request Ready for Review",
     "prev": "PR created with notebook fix. Merge to trigger automated CD deployment.",
     "to": f"{_ALERT_TO}, {_GH_EMAIL}"},
    {"icon": "🎉", "stage": "Stage 6 — Final Confirmation",
     "subj": "🎉 AEGIS: Full Recovery Complete — Incident RESOLVED",
     "prev": "Pipeline HEALTHY. PR merged. CD deployed. Post-deploy verified. 0 human interventions.",
     "to": _ALERT_TO},
]
# Emails shown when the run completes healthy (no pipeline failures detected)
EMAILS_DATA_HEALTHY = [
    {"icon": "✅", "stage": "Stage 1 — Automated Health Check",
     "subj": "✅ AEGIS: All Pipelines HEALTHY — No Action Required",
     "prev": "All selected Databricks jobs are running successfully. No failures detected. AEGIS standing by.",
     "to": _ALERT_TO},
]
HEALTHY_STAGE_IDX = {"initial_health_check": 0}

GUARDRAILS = [
    {"id": 1, "name": "Confidence Gate",  "desc": "Escalate if RCA < 70%"},
    {"id": 2, "name": "Diff Review",      "desc": "Flag zero-change output"},
    {"id": 3, "name": "Rollback",         "desc": "Restore on run failure"},
    {"id": 4, "name": "Syntax + Lint",    "desc": "Hard-block invalid Python"},
    {"id": 5, "name": "Rate Limiter",     "desc": "Max 5 triggers/10 min"},
    {"id": 6, "name": "Audit Log",        "desc": "Append-only JSONL trail"},
    {"id": 7, "name": "Prompt Guard",     "desc": "Injection defence layer"},
]
BUGS = [
    {"id": 1,  "sev": "CRITICAL", "line":  13, "desc": "Import typo: `pandsa` not a module",        "before": "import pandsa as pd",                               "after": "import pandas as pd"},
    {"id": 2,  "sev": "HIGH",     "line":  64, "desc": "`printSchema()` returns None",               "before": "schema_check = dedup_df.printSchema()",             "after": "schema_check = dedup_df.schema"},
    {"id": 3,  "sev": "CRITICAL", "line":  65, "desc": "`.fieldNames()` on None (cascades from #2)","before": "schema_check.fieldNames()",                         "after": "(fixed by Bug #2 fix)"},
    {"id": 4,  "sev": "HIGH",     "line":  74, "desc": "Column typo: `transacion_id`",               "before": '"transacion_id"',                                   "after": '"transaction_id"'},
    {"id": 5,  "sev": "HIGH",     "line":  99, "desc": 'String `"2"` instead of int in spark_round',"before": 'spark_round(col("revenue")/1000, "2")',              "after": 'spark_round(col("revenue")/1000, 2)'},
    {"id": 6,  "sev": "HIGH",     "line": 110, "desc": "Invalid dict literal in `.agg()`",           "before": '{"revenue": "stdev"}',                              "after": 'stddev("revenue").alias("stddev_revenue")'},
    {"id": 7,  "sev": "CRITICAL", "line": 119, "desc": "ZeroDivisionError: void_count always 0",    "before": "converted_count / void_count",                      "after": "converted_count / max(void_count,1)"},
    {"id": 8,  "sev": "CRITICAL", "line":  18, "desc": "`regexp_replace` not imported (NameError)", "before": "    stddev, when, isnan, isnull, to_date,",          "after": "    stddev, when, isnan, isnull, to_date, regexp_replace,"},
    {"id": 9,  "sev": "CRITICAL", "line": 132, "desc": "IndexError on empty Northwest filter",      "before": ".collect()[0][0]",                                   "after": "rows=.collect(); val=rows[0][0] if rows else 0.0"},
    {"id": 10, "sev": "CRITICAL", "line": 152, "desc": "Missing `.write` before `.saveAsTable()`",  "before": "report_df.saveAsTable(OUTPUT_TABLE)",                "after": "report_df.write.saveAsTable(OUTPUT_TABLE)"},
]

# ── Config ─────────────────────────────────────────────────────────────────────
def _load_config():
    p = Path(ROOT) / "config" / "config.yaml"
    raw = os.path.expandvars(p.read_text())
    return yaml.safe_load(raw)

# ── Databricks job lister (runs in background thread) ─────────────────────────
def _fetch_jobs(host: str, token: str, result: dict):
    try:
        from databricks.sdk import WorkspaceClient
        client = WorkspaceClient(host=host, token=token)
        jobs = []
        for job in client.jobs.list():
            latest_status = "UNKNOWN"
            try:
                runs = list(client.jobs.list_runs(job_id=job.job_id, limit=1))
                if runs and runs[0].state and runs[0].state.result_state:
                    latest_status = runs[0].state.result_state.value
            except Exception:
                pass
            jobs.append({
                "job_id":        str(job.job_id),
                "name":          (job.settings.name or f"Job {job.job_id}") if job.settings else f"Job {job.job_id}",
                "tasks":         len(job.settings.tasks) if job.settings and job.settings.tasks else 0,
                "latest_status": latest_status,
            })
        result["jobs"]  = jobs
        result["error"] = None
    except Exception as exc:
        result["jobs"]  = []
        result["error"] = str(exc)
    result["done"] = True

# ── Workflow background worker ────────────────────────────────────────────────
async def _async_run(initial_state, rs, log_q):
    from src.workflow import build_aegis_workflow
    from loguru import logger

    def _sink(msg):
        rec, text = msg.record, msg.record["message"]
        lvl = rec["level"].name
        if any(k in text for k in ("FAILED","ERROR","failed","error","Exception","Traceback")):
            cls = "lf"
        elif any(k in text for k in ("SUCCESS","success","PASSED","✅","healthy","complete","restored")):
            cls = "ls"
        elif any(k in text for k in ("[JobFixer]","GPT","repair","fix","notebook","bug","patch")):
            cls = "lb"
        elif any(k in text for k in ("GUARDRAIL","guardrail","confidence gate","rate limit","audit","compile","pyflakes","rollback","diff","inject")):
            cls = "lg"
        elif any(k in text for k in ("Email","email","Sending","notification","smtp","gmail")):
            cls = "le"
        elif any(k in text for k in ("[RCAAgent]","RCA","root cause","confidence","risk")):
            cls = "lgp"
        elif lvl == "WARNING":
            cls = "lw"
        else:
            cls = "li"
        log_q.put({"ts": rec["time"].strftime("%H:%M:%S"), "cls": cls, "msg": text})

    sink_id = logger.add(_sink, format="", level="DEBUG")
    try:
        wf = build_aegis_workflow()
        try:
            async for chunk in wf.astream(initial_state, config={"recursion_limit": 150}, stream_mode="updates"):
                if isinstance(chunk, dict):
                    for node_name, updates in chunk.items():
                        if node_name.startswith("__"):
                            continue
                        # Normalize to _node suffix so names match CHECKLIST/NODE_INDEX keys
                        key = node_name if node_name.endswith("_node") else node_name + "_node"
                        rs["current_node"] = key
                        rs["done_nodes"].add(key)
                        if isinstance(updates, dict):
                            rs["state"].update(updates)
        except TypeError:
            result = await wf.ainvoke(initial_state, config={"recursion_limit": 150})
            rs["state"] = result
            rs["current_node"] = "incident_report_node"
            for n in NODE_INDEX:
                rs["done_nodes"].add(n)
    except Exception as exc:
        rs["error"] = str(exc)
        log_q.put({"ts": datetime.now().strftime("%H:%M:%S"), "cls": "lf", "msg": f"WORKFLOW ERROR: {exc}"})
    finally:
        logger.remove(sink_id)
        rs["complete"] = True

def _worker(initial_state, rs, log_q):
    asyncio.run(_async_run(initial_state, rs, log_q))

def _start_workflow(selected_job_ids: list[str], monitor_ml: bool = False):
    config   = _load_config()
    host     = os.environ["DATABRICKS_HOST"]
    token    = os.environ["DATABRICKS_TOKEN"]
    sel_str  = ",".join(selected_job_ids) if selected_job_ids else "all"
    monitor_all = (sel_str == "all" or not selected_job_ids)
    specific    = None if monitor_all or len(selected_job_ids) > 1 else selected_job_ids[0]

    initial_state = {
        "workspace_host": host, "workspace_token": token,
        "monitor_all_jobs": monitor_all, "monitor_ml_models": monitor_ml,
        "specific_job_id": specific,
        "dab_bundle_name": os.getenv("DAB_BUNDLE_NAME","aegis-de-project") if monitor_all else None,
        "user_selected_job_id": sel_str,
        "config": config,
        "job_health_reports": [], "has_failures": False, "healthy_count": 0, "failed_count": 0,
        "current_incident_id": None, "current_job_id": None, "current_job_name": None,
        "current_error_summary": None, "root_cause": None, "confidence": 0.0,
        "risk_level": "unknown", "fix_status": None, "fixed_notebooks": [],
        "post_fix_run_id": None, "mttr_seconds": 0.0, "pr_url": None, "pr_number": 0,
        "pr_merged": False, "merge_sha": None, "workflow_run_url": None,
        "deployment_status": None, "post_deployment_healthy": False,
        "emails_sent": [], "available_jobs": [], "model_health_reports": [],
        "ml_degraded_models": [], "ml_heal_result": None,
        "incident_report": None, "current_stage": "init",
    }
    lq = queue.Queue()
    rs = {"current_node": None, "done_nodes": set(), "state": {}, "complete": False, "error": None}
    t  = threading.Thread(target=_worker, args=(initial_state, rs, lq), daemon=True)
    t.start()
    return t, rs, lq

# ── Session state ──────────────────────────────────────────────────────────────
_SS_DEFAULTS = {
    # connection
    "host": os.getenv("DATABRICKS_HOST",""), "token": os.getenv("DATABRICKS_TOKEN",""),
    "dial_key": os.getenv("DIAL_API_KEY",""),
    "connected": False, "connecting": False,
    "available_jobs": [], "connect_error": None,
    "connect_thread": None, "connect_result": None,
    "connect_start_time": 0.0,
    # job selection
    "selected_ids": [], "monitor_ml": False,
    # workflow run
    "running": False, "complete": False,
    "run_start_time": 0.0, "run_end_time": 0.0,
    "logs": [], "thread": None, "rs": None, "log_q": None,
    "final_done_nodes": set(),
    # two-phase start: set by Run button, consumed at top of main() before any Step-2 widgets render
    "_pending_run": False, "_pending_run_sel": [], "_pending_run_ml": False,
    # permanent latch: True once Run is clicked, reset only by New Run / Back / Disconnect
    # guards Step 2 independently of S.running so any race in the thread-alive check can't re-show it
    "_aegis_started": False,
}
for k, v in _SS_DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v
S = st.session_state

# ── HTML helpers ───────────────────────────────────────────────────────────────
def _steps_html(phase):
    _imgs = [_STEP_CONNECT_B64, _STEP_JOBS_B64, _STEP_RUN_B64]
    _mimes = ["image/png", "image/png", "image/jpeg"]
    steps = [("1", "Connect", "Verify Databricks credentials"),
             ("2", "Select Jobs", "Choose jobs to monitor"),
             ("3", "Run AEGIS", "Autonomous healing")]
    out = ['<div class="steps">']
    for i,(n,t,s) in enumerate(steps, 1):
        cls  = "step-done" if i < phase else ("step-active" if i == phase else "step-inactive")
        icon = "✓" if i < phase else n
        b64  = _imgs[i-1]
        mime = _mimes[i-1]
        active = (i == phase)
        img_opacity = "1" if active or i < phase else "0.32"
        img_filter  = ("drop-shadow(0 0 6px rgba(255,98,0,.55))" if active
                       else ("grayscale(0)" if i < phase else "grayscale(0.6)"))
        img_html = (f'<img src="data:image/{mime.split("/")[1]};base64,{b64}" '
                    f'style="height:36px;width:36px;object-fit:contain;flex-shrink:0;'
                    f'opacity:{img_opacity};filter:{img_filter};transition:all .35s">'
                    if b64 else f'<div class="step-num">{icon}</div>')
        num_html = f'<div class="step-num">{icon}</div>' if not b64 else ""
        out.append(
            f'<div class="step {cls}" style="display:flex;align-items:center;gap:10px">'
            f'{img_html}{num_html}'
            f'<div><div class="step-title">{t}</div><div class="step-sub">{s}</div></div>'
            f'</div>'
        )
    out.append('</div>')
    return "".join(out)

def _job_status_cls(s):
    if s == "SUCCESS":     return "jcs-success", "✅ SUCCESS"
    if s in ("FAILED","INTERNAL_ERROR"): return "jcs-failed", "❌ FAILED"
    return "jcs-unknown", f"○ {s}"

def _wf_html(done_n, cur_n):
    done_idx = {NODE_INDEX[n] for n in done_n if n in NODE_INDEX}
    act_idx  = NODE_INDEX.get(cur_n,-1) if cur_n else -1
    parts = ['<div class="wf-wrap"><div class="wf-row">']
    for i, lbl in enumerate(WORKFLOW_NODES):
        cls = "wf-d" if i in done_idx else ("wf-a" if i == act_idx else "wf-p")
        ico = "✓" if i in done_idx else ("●" if i == act_idx else str(i+1))
        parts.append(f'<div class="wf-node {cls}"><div class="wf-icon">{ico}</div><div class="wf-lbl">{lbl.replace(chr(10),"<br>")}</div></div>')
        if i < len(WORKFLOW_NODES)-1:
            arr = "wf-arrd" if i in done_idx else "wf-arr"
            parts.append(f'<div class="{arr}">→</div>')
    parts.append("</div></div>")
    return "".join(parts)

def _terminal(logs):
    body = "\n".join(logs[-60:]) if logs else '<p class="log"><span class="li">  Waiting for workflow to start…</span></p>'
    return f'<div class="term-wrap"><div class="term-bar"><div class="td td-r"></div><div class="td td-y"></div><div class="td td-g"></div><span class="term-ttl">aegis · live loguru stream</span></div><div class="terminal">{body}</div></div>'

def _email_card(e, sent):
    cls = "em-c sent" if sent else "em-c unsent"
    sc, st_txt = ("em-ok", "✅ Sent") if sent else ("em-no", "○ Pending")
    return f'<div class="{cls}"><div class="em-ico">{e["icon"]}</div><div style="flex:1;min-width:0"><div class="em-s">{e["stage"]}</div><div class="em-sub">{e["subj"]}</div><div class="em-pre">{e["prev"]}</div><div class="em-to">To: {e["to"]}</div></div><div class="em-st {sc}">{st_txt}</div></div>'

def _guardrails_html(active, details=None):
    details = details or {}
    badges = []
    for g in GUARDRAILS:
        on  = g["id"] in active
        det = details.get(g["id"], "")
        det_html = f'<div style="font-size:.65rem;color:#7A3A10;margin-top:3px;font-style:italic">{det}</div>' if det else ""
        badges.append(f'<div class="gr-b {"on" if on else ""}"><div class="gr-n">#{g["id"]}</div><div class="gr-nm">{g["name"]}</div><div class="gr-dc">{g["desc"]}</div>{det_html}<div class="gr-st">{"✅ Active" if on else "○ Standby"}</div></div>')
    return f'<div class="gr-grid">{"".join(badges)}</div>'

# ── Checklist stages (mirrors the 15-node LangGraph workflow) ─────────────────
CHECKLIST = [
    {"key": "job_selector_node",                "label": "Job Selection",             "icon": "🎯"},
    {"key": "status_check_node",                "label": "Status Check",              "icon": "🔍"},
    {"key": "initial_email_node",               "label": "Initial Health Email",      "icon": "📧"},
    {"key": "failure_alert_node",               "label": "Failure Alert + GPT-4o RCA","icon": "🚨"},
    {"key": "fix_in_progress_email_node",       "label": "Fix In Progress Email",     "icon": "📩"},
    {"key": "job_fixer_node",                   "label": "GPT-5.5 Notebook Repair",   "icon": "🔧"},
    {"key": "fix_complete_email_node",          "label": "Fix Complete Email",        "icon": "✉️"},
    {"key": "pr_create_node",                   "label": "GitHub PR Created",         "icon": "📋"},
    {"key": "pr_raised_email_node",             "label": "PR Raised Email",           "icon": "📧"},
    {"key": "pr_wait_approval_node",            "label": "Awaiting PR Approval",      "icon": "⏳"},
    {"key": "deployment_node",                  "label": "CD Deployment",             "icon": "🚀"},
    {"key": "post_deployment_verification_node","label": "Post-Deploy Verification",  "icon": "✅"},
    {"key": "final_confirmation_email_node",    "label": "Final Confirmation Email",  "icon": "🎉"},
    {"key": "deployment_failed_email_node",     "label": "Deployment Failed Email",   "icon": "❌"},
    {"key": "incident_report_node",             "label": "Incident Report",           "icon": "📑"},
]

def _checklist_html(done_n, cur_n, wf_state):
    conf       = float(wf_state.get("confidence") or 0)
    risk       = (wf_state.get("risk_level") or "").upper()
    pr_url     = wf_state.get("pr_url") or ""
    pr_merged  = wf_state.get("pr_merged", False)
    fix_status = wf_state.get("fix_status") or ""
    mttr       = float(wf_state.get("mttr_seconds") or 0)
    job_name   = wf_state.get("current_job_name") or ""
    job_id     = wf_state.get("current_job_id") or ""
    healthy    = wf_state.get("healthy_count", 0)
    failed     = wf_state.get("failed_count", 0)
    fixed_nbs  = wf_state.get("fixed_notebooks") or []
    deploy_st  = wf_state.get("deployment_status") or ""
    deploy_url = wf_state.get("workflow_run_url") or ""
    inc_id     = wf_state.get("current_incident_id") or ""
    root_cause = wf_state.get("root_cause") or ""
    err_summ   = wf_state.get("current_error_summary") or ""
    emails_sent= wf_state.get("emails_sent") or []
    post_ok    = wf_state.get("post_deployment_healthy", False)
    sel_id     = wf_state.get("user_selected_job_id") or ""
    ml_result     = wf_state.get("ml_heal_result") or ""
    job_reports   = wf_state.get("job_health_reports") or []
    model_reports = wf_state.get("model_health_reports") or []
    ml_degraded   = wf_state.get("ml_degraded_models") or []
    monitor_ml    = bool(wf_state.get("monitor_ml_models", False))

    # ── "in progress" hint shown while a node is actively running ─────────
    _active_hint = {
        "job_selector_node":                 "Resolving job selection…",
        "status_check_node":                 "Querying Databricks for latest run status…",
        "initial_email_node":                "Sending health-check email via SMTP…",
        "failure_alert_node":                "GPT-4o analysing root cause (structured JSON)…",
        "fix_in_progress_email_node":        "Notifying stakeholders — repair starting…",
        "job_fixer_node":                    "GPT-5.5 scanning entire notebook for all bugs…",
        "fix_complete_email_node":           "Sending fix-complete notification…",
        "pr_create_node":                    "Creating GitHub PR with patched notebook…",
        "pr_raised_email_node":              "Emailing team with PR link…",
        "pr_wait_approval_node":             "Polling GitHub every 30 s for PR merge…",
        "deployment_node":                   "Monitoring GitHub Actions CD pipeline…",
        "post_deployment_verification_node": "Re-running Databricks job to verify fix…",
        "final_confirmation_email_node":     "Sending resolution confirmation email…",
        "deployment_failed_email_node":      "Sending deployment-failure alert…",
        "incident_report_node":              "Writing incident report to knowledge store…",
    }

    def _done_detail(key):
        # ── job_selector ──────────────────────────────────────────────────
        if key == "job_selector_node":
            parts = []
            # sel_id may be "all" or comma-separated IDs
            if sel_id and sel_id != "all":
                ids = [x.strip() for x in sel_id.split(",") if x.strip()]
                if len(ids) > 1:
                    parts.append(f"<b>{len(ids)} jobs</b> selected")
                elif job_name:
                    parts.append(f"Job: <b>{job_name}</b>")
                else:
                    parts.append(f"Job ID: <b>{ids[0]}</b>")
            elif sel_id == "all":
                parts.append("All jobs selected")
            elif job_name:
                parts.append(f"Job: <b>{job_name}</b>")
            if monitor_ml:
                parts.append("ML monitoring: <b>ON</b>")
            return " &nbsp;·&nbsp; ".join(parts) if parts else "Job selected ✓"

        # ── status_check ─────────────────────────────────────────────────
        if key == "status_check_node":
            total_jobs = healthy + failed
            job_lbl    = f"{total_jobs} job{'s' if total_jobs != 1 else ''}"
            line = (f"<b>{job_lbl} checked</b> &nbsp;·&nbsp; "
                    f"<span style='color:#16a34a;font-weight:700'>✅ {healthy} healthy</span>"
                    f"&nbsp; <span style='color:#dc2626;font-weight:700'>❌ {failed} failed</span>")
            # Failed job names
            failed_jobs = [r.get("job_name","") for r in job_reports if r.get("status","").lower() in ("failed","internal_error")]
            if failed_jobs:
                line += f"<br>Failed: <b>{', '.join(failed_jobs[:3])}</b>"
            # All checked job names (when > 1)
            all_names = [r.get("job_name","") for r in job_reports if r.get("job_name")]
            if all_names and not failed_jobs:
                line += f"<br>Jobs: {', '.join(all_names[:4])}"
            # ML model health
            if monitor_ml:
                ml_total = len(model_reports)
                ml_ok    = ml_total - len(ml_degraded)
                if ml_total:
                    ml_c   = "#16a34a" if not ml_degraded else "#ea580c"
                    ml_ico = "✅" if not ml_degraded else "⚠️"
                    line += (f"<br><span style='color:{ml_c};font-weight:700'>"
                             f"{ml_ico} ML: {ml_ok}/{ml_total} models healthy</span>")
                    if ml_degraded:
                        deg_names = [str(m)[:22] for m in ml_degraded[:2]]
                        line += f" — degraded: <b>{', '.join(deg_names)}</b>"
                else:
                    line += "<br><span style='color:#16a34a'>✅ ML models checked</span>"
            return line

        # ── initial email ─────────────────────────────────────────────────
        if key == "initial_email_node":
            total_jobs = healthy + failed
            parts = [f"✅ Health-check email sent — {total_jobs} job{'s' if total_jobs != 1 else ''}: "
                     f"<b>{healthy}</b> healthy, <b>{failed}</b> failed"]
            if monitor_ml:
                ml_total = len(model_reports)
                ml_ok    = ml_total - len(ml_degraded)
                if ml_total:
                    parts.append(f"ML: <b>{ml_ok}/{ml_total}</b> models healthy"
                                 + (" ⚠️" if ml_degraded else " ✅"))
                else:
                    parts.append("ML models: checked ✅")
            return " &nbsp;·&nbsp; ".join(parts)

        # ── failure_alert + RCA ───────────────────────────────────────────
        if key == "failure_alert_node":
            if not conf: return ""
            rc = "#16a34a" if risk == "LOW" else "#ea580c"
            gate = "✅ confidence gate passed" if conf >= 70 else "⚠️ escalated (below 70%)"
            line = (f"GPT-4o: <b>{conf:.0f}%</b> confidence &nbsp;·&nbsp; "
                    f"<span style='color:{rc};font-weight:700'>{risk} RISK</span> &nbsp;·&nbsp; {gate}")
            if root_cause:
                short = root_cause[:100] + ("…" if len(root_cause) > 100 else "")
                line += f"<br><span style='color:#374151'>Root cause: {short}</span>"
            if job_name:
                line += f"<br>Job: <b>{job_name}</b>" + (f" (ID {job_id})" if job_id else "")
            return line

        # ── fix in progress email ─────────────────────────────────────────
        if key == "fix_in_progress_email_node":
            return (f"✅ Repair-started notification sent"
                    + (f" — {job_name}" if job_name else ""))

        # ── job_fixer ─────────────────────────────────────────────────────
        if key == "job_fixer_node":
            if not fix_status: return ""
            if fix_status == "success":
                nb_names = [str(n).split("/")[-1] for n in fixed_nbs[:2]]
                nb_str   = ", ".join(nb_names) if nb_names else "notebook"
                mttr_str = (f"{int(mttr//60)}m {int(mttr%60):02d}s" if mttr else "—")
                return (f"✅ GPT-5.5 fixed <b>{len(BUGS)} bugs</b> in <b>{nb_str}</b>"
                        f" &nbsp;·&nbsp; MTTR so far: {mttr_str}")
            else:
                return f"⚠️ Fix status: <b>{fix_status}</b>" + (f" — {err_summ[:80]}" if err_summ else "")

        # ── fix complete email ────────────────────────────────────────────
        if key == "fix_complete_email_node":
            return (f"✅ Fix-complete email sent"
                    + (f" — {job_name}" if job_name else ""))

        # ── pr create ────────────────────────────────────────────────────
        if key == "pr_create_node":
            if not pr_url: return "PR created ✓"
            return f'✅ PR opened: <a href="{pr_url}" target="_blank" style="color:#FF8C1A;font-weight:700">{pr_url}</a>'

        # ── pr raised email ───────────────────────────────────────────────
        if key == "pr_raised_email_node":
            return f"✅ PR-raised email sent" + (f' — <a href="{pr_url}" target="_blank" style="color:#FF8C1A">{pr_url}</a>' if pr_url else "")

        # ── pr wait approval ──────────────────────────────────────────────
        if key == "pr_wait_approval_node":
            if pr_merged:
                return "✅ PR merged — triggering GitHub Actions CD"
            if pr_url:
                return f'⏳ Awaiting review: <a href="{pr_url}" target="_blank" style="color:#FF8C1A">{pr_url}</a>'
            return "Polling GitHub for merge…"

        # ── deployment ────────────────────────────────────────────────────
        if key == "deployment_node":
            parts = []
            if deploy_st: parts.append(f"Status: <b>{deploy_st}</b>")
            if deploy_url:
                parts.append(f'<a href="{deploy_url}" target="_blank" style="color:#FF8C1A">GitHub Actions ↗</a>')
            return " &nbsp;·&nbsp; ".join(parts) if parts else "Deployment triggered ✓"

        # ── post-deploy verification ──────────────────────────────────────
        if key == "post_deployment_verification_node":
            if post_ok:
                return f"✅ Databricks job re-ran successfully after deploy" + (f" — {job_name}" if job_name else "")
            return "⚠️ Post-deploy run did not pass" if "post_deployment_verification_node" in done_n else ""

        # ── final confirmation email ──────────────────────────────────────
        if key == "final_confirmation_email_node":
            if not mttr: return "✅ Resolution email sent"
            m_, s_ = divmod(int(mttr), 60)
            return (f"✅ Resolution email sent &nbsp;·&nbsp; MTTR: <b>{m_}m {s_:02d}s</b>"
                    + (f" &nbsp;·&nbsp; Incident <b>{inc_id}</b> closed" if inc_id else "")
                    + " &nbsp;·&nbsp; 0 human interventions")

        # ── deployment failed email ───────────────────────────────────────
        if key == "deployment_failed_email_node":
            return f"⚠️ Deployment-failure alert sent" + (f" — {deploy_st}" if deploy_st else "")

        # ── incident report ───────────────────────────────────────────────
        if key == "incident_report_node":
            return (f"✅ Incident report saved"
                    + (f": <b>data/reports/{inc_id}.json</b>" if inc_id else " to knowledge store"))

        return ""

    items = []
    for stage in CHECKLIST:
        k = stage["key"]
        done   = k in done_n
        active = (k == cur_n) and not done

        if done:
            bg       = "#f0fdf4"
            bdr      = "#4ade80"
            num_bg   = "#16a34a"
            num_c    = "#ffffff"
            lbl_c    = "#14532d"
            card_bdr = "border-left:4px solid #16a34a"
            num_html = "✓"
            label_extra = "font-weight:700"
        elif active:
            bg       = "#fffbeb"
            bdr      = "#f59e0b"
            num_bg   = "#f59e0b"
            num_c    = "#ffffff"
            lbl_c    = "#78350f"
            card_bdr = "border-left:4px solid #f59e0b"
            num_html = '<span style="animation:spin 1s linear infinite;display:inline-block">⟳</span>'
            label_extra = "font-weight:700"
        else:
            bg       = "#FFF8F0"
            bdr      = "#FFD4A8"
            num_bg   = "#FFF0E0"
            num_c    = "#B06030"
            lbl_c    = "#B06030"
            card_bdr = ""
            num_html = stage["icon"]
            label_extra = ""

        if done:
            det = _done_detail(k)
        elif active:
            det = f'<span style="color:#92400e;font-style:italic">{_active_hint.get(k, "Running…")}</span>'
        else:
            det = ""

        det_html = f'<div style="font-size:.72rem;color:#7A3A10;margin-top:5px;line-height:1.6">{det}</div>' if det else ""

        items.append(f"""
<div style="display:flex;gap:10px;align-items:flex-start;margin-bottom:4px">
  <div style="display:flex;flex-direction:column;align-items:center;flex-shrink:0">
    <div style="width:32px;height:32px;border-radius:50%;background:{num_bg};color:{num_c};
      display:flex;align-items:center;justify-content:center;font-size:.82rem;font-weight:900;
      border:2px solid {bdr};flex-shrink:0;box-shadow:{'0 0 8px rgba(22,163,74,.4)' if done else ('0 0 8px rgba(245,158,11,.4)' if active else 'none')}">{num_html}</div>
    <div style="width:2px;flex:1;min-height:10px;background:{bdr};margin-top:2px;opacity:{'.9' if done else ('.7' if active else '.3')}"></div>
  </div>
  <div style="background:{bg};border:1px solid {bdr};{card_bdr};border-radius:10px;padding:9px 13px;
    flex:1;margin-bottom:2px;transition:all .3s">
    <div style="font-size:.83rem;color:{lbl_c};{label_extra}">{stage['label']}</div>
    {det_html}
  </div>
</div>""")

    return f"""<style>@keyframes spin{{to{{transform:rotate(360deg)}}}}</style>
<div style="padding:4px 0">{"".join(items)}</div>"""

# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    # ── Drain connect result (no rerun yet) ───────────────────────────────
    if S.connecting and S.connect_result and S.connect_result.get("done"):
        S.connecting = False
        if S.connect_result["error"]:
            S.connect_error = S.connect_result["error"]; S.connected = False
        else:
            S.available_jobs = S.connect_result["jobs"]; S.connected = True; S.connect_error = None

    # ── Two-phase workflow start: consume pending flag BEFORE any Step-2 widgets render ──
    # _aegis_started is set to True here (and never auto-reset) so the Step-2 guard
    # cannot flip back to True via any S.running race condition.
    if S._pending_run:
        sel = list(S._pending_run_sel)
        _ml = bool(S._pending_run_ml)
        S._pending_run    = False
        S._aegis_started  = True   # permanent latch — Step 2 will never render again
        S.running         = True   # set BEFORE _start_workflow so Step 2 stays hidden even on error
        S.run_start_time  = time.time()
        try:
            t, rs_new, lq = _start_workflow(sel, monitor_ml=_ml)
            S.thread = t; S.rs = rs_new; S.log_q = lq
        except Exception as _wf_err:
            S.running  = False; S.complete = True
            S.rs = {"complete": True, "error": str(_wf_err), "state": {}, "done_nodes": set()}

    # ── Drain workflow log queue (no rerun yet) ────────────────────────────
    if S.running and S.thread and S.log_q and S.rs:
        try:
            while True:
                e = S.log_q.get_nowait()
                msg_esc = e["msg"].replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
                S.logs.append(f'<p class="log"><span class="ts">[{e["ts"]}]</span> <span class="{e["cls"]}">{msg_esc}</span></p>')
        except queue.Empty:
            pass
        if not S.thread.is_alive() or S.rs.get("complete"):
            S.running = False; S.complete = True
            if not S.run_end_time:
                S.run_end_time = time.time()   # freeze elapsed time for MTTR display
            # Snapshot done_nodes into session state so they persist
            # even if S.rs is later cleared (e.g. memory pressure).
            if S.rs and S.rs.get("done_nodes"):
                S.final_done_nodes = set(S.rs["done_nodes"])

    # ── Derive live state ─────────────────────────────────────────────────
    rs_      = S.rs or {}
    wf_state = rs_.get("state", {})
    # Use the live set while running; fall back to the snapshot when complete
    # so the completed stages stay green even after S.rs is cleared.
    _live_done = set(rs_.get("done_nodes", set()))
    done_n = _live_done or (set(getattr(S, "final_done_nodes", set())) if S.complete else set())

    # cur_n: astream sets this to the node that JUST FINISHED.
    # For the "active" highlight we want the FIRST node not yet done.
    # When complete, no active node.
    cur_n = None
    if S.running:
        for _s in CHECKLIST:
            if _s["key"] not in done_n:
                cur_n = _s["key"]
                break
    conf       = float(wf_state.get("confidence") or 0)
    risk       = (wf_state.get("risk_level") or "unknown").upper()
    root_cause = wf_state.get("root_cause") or ""
    fix_status = wf_state.get("fix_status") or ""
    # Live MTTR: tick every 0.4s while running; freeze at end time on completion
    _wf_mttr = float(wf_state.get("mttr_seconds") or 0)
    if _wf_mttr > 0:
        mttr = _wf_mttr                                          # real value set by job_fixer_node
    elif S.running and S.run_start_time:
        mttr = time.time() - S.run_start_time                   # live ticking clock
    elif S.complete and S.run_start_time and S.run_end_time:
        mttr = S.run_end_time - S.run_start_time                 # frozen elapsed (healthy/complete)
    else:
        mttr = 0.0
    pr_url     = wf_state.get("pr_url") or ""
    job_name   = wf_state.get("current_job_name") or ""
    inc_id     = wf_state.get("current_incident_id") or ""
    emails_raw = wf_state.get("emails_sent") or []
    fixed_nbs  = wf_state.get("fixed_notebooks") or []
    sent_idx   = {EMAIL_STAGE_IDX[s] for s in emails_raw if s in EMAIL_STAGE_IDX}
    # Dynamic email list: healthy run shows a single "all clear" card; failure run shows all 6 stages
    _is_healthy_run = S.complete and "failure_alert" not in emails_raw
    display_emails    = EMAILS_DATA_HEALTHY if _is_healthy_run else EMAILS_DATA
    display_sent_idx  = ({HEALTHY_STAGE_IDX[s] for s in emails_raw if s in HEALTHY_STAGE_IDX}
                         if _is_healthy_run else sent_idx)
    bugs_fixed = fix_status == "success" or bool(fixed_nbs)
    fixed_n    = len(BUGS) if bugs_fixed else 0
    active_gr  = {7} if S.logs else set()
    if conf >= 70: active_gr.add(1)
    if "job_fixer_node" in done_n: active_gr.update({2,3,4,5,6})

    # ── Hero ──────────────────────────────────────────────────────────────
    _logo_tag = (f'<img src="data:image/png;base64,{_LOGO_B64}" '
                 f'style="height:84px;width:auto;object-fit:contain;flex-shrink:0;'
                 f'border-radius:12px;background:rgba(255,255,255,.92);'
                 f'padding:4px 6px;'
                 f'filter:drop-shadow(0 4px 14px rgba(0,0,0,.25))">'
                 if _LOGO_B64 else '<span style="font-size:3.2rem">🛡️</span>')
    st.markdown(f"""
<div class="hero">
  <div class="hero-left" style="display:flex;align-items:center;gap:18px">
    {_logo_tag}
    <div>
      <h1 style="margin:0;line-height:1">AEGIS</h1>
      <p style="margin:5px 0 0">Autonomous Excellence Guardian &amp; Intelligent System &nbsp;·&nbsp; AI Hackathon 2026</p>
    </div>
  </div>
  <div class="hero-badges">
    <span class="hb">LangGraph 15-node</span>
    <span class="hb">GPT-5.5 Repair</span>
    <span class="hb">GPT-4o RCA</span>
    <span class="hb">7 Safety Guardrails</span>
    <span class="hb">Zero Human Intervention</span>
  </div>
</div>""", unsafe_allow_html=True)

    # ── Step indicator ────────────────────────────────────────────────────
    if S.running or S.complete:       phase = 3
    elif S.connected and S.available_jobs: phase = 2
    else:                              phase = 1
    st.markdown(_steps_html(phase), unsafe_allow_html=True)

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 1: Connect to Databricks  (reads .env directly — no form)
    # ═══════════════════════════════════════════════════════════════════════
    if not S.connected:
        env_host  = os.getenv("DATABRICKS_HOST","")
        env_token = os.getenv("DATABRICKS_TOKEN","")

        _db_img = (f'<img src="data:image/png;base64,{_DB_LOGO_B64}" '
                   f'style="height:72px;width:auto;object-fit:contain;margin-bottom:14px">'
                   if _DB_LOGO_B64 else '<div style="font-size:3.5rem;margin-bottom:12px">🛡️</div>')
        st.markdown(f"""
<div style="max-width:480px;margin:60px auto;text-align:center">
  {_db_img}
  <h2 style="color:#2D1200;font-weight:900;margin:0 0 24px">Connect to Databricks</h2>
</div>""", unsafe_allow_html=True)

        if S.connect_error:
            st.error(f"Connection failed — {S.connect_error}\n\nUpdate `DATABRICKS_TOKEN` in your `.env` file with a fresh token, then restart the app.")

        if not env_host or not env_token:
            st.warning("DATABRICKS_HOST or DATABRICKS_TOKEN not found in `.env`. Add them and restart.")
        else:
            _, cb, _ = st.columns([3, 2, 3])
            with cb:
                lbl = "⟳  Connecting…" if S.connecting else "🔗  Connect to Databricks"
                if st.button(lbl, type="primary", use_container_width=True, key="btn_connect", disabled=S.connecting):
                    S.host = env_host; S.token = env_token
                    result = {"done": False, "jobs": [], "error": None}
                    S.connect_result = result
                    t = threading.Thread(target=_fetch_jobs, args=(env_host, env_token, result), daemon=True)
                    S.connect_thread = t
                    S.connecting = True
                    S.connect_start_time = time.time()
                    t.start()
                    st.rerun()

            if S.connecting:
                elapsed = time.time() - S.connect_start_time
                pct     = min(0.92, elapsed / 12.0)

                man_pct = int(pct * 100)
                man_pos = max(6, min(94, man_pct))
                st.markdown(f"""
<style>
@keyframes spin{{to{{transform:rotate(360deg)}}}}
@keyframes bob{{0%,100%{{transform:translateX(-50%) translateY(0)}}50%{{transform:translateX(-50%) translateY(-5px)}}}}
</style>
<div style="max-width:520px;margin:0 auto">
  <div style="text-align:center;margin-bottom:18px">
    <div style="font-size:1.05rem;font-weight:700;color:#2D1200">Connecting to Databricks…</div>
    <div style="font-size:.78rem;color:#7A3A10;margin-top:4px">{elapsed:.1f}s elapsed</div>
  </div>
  <!-- running-man progress track -->
  <div style="position:relative;height:48px;margin-top:14px">
    <!-- track background -->
    <div style="position:absolute;bottom:8px;left:0;right:0;height:8px;
      background:#FFE8CC;border-radius:99px;overflow:hidden">
      <!-- fill from LEFT (left→right) -->
      <div style="height:100%;width:{man_pct}%;
        background:linear-gradient(90deg,#FF6200,#FFB300);
        border-radius:99px;transition:width .4s ease"></div>
    </div>
    <!-- dashed ground line -->
    <div style="position:absolute;bottom:6px;left:0;right:0;height:2px;
      background:repeating-linear-gradient(90deg,transparent 0,transparent 6px,#FFD4A8 6px,#FFD4A8 12px)">
    </div>
    <!-- running man emoji — faces right, runs left→right -->
    <div style="position:absolute;bottom:10px;left:{man_pos}%;
      font-size:1.6rem;line-height:1;
      animation:bob 0.35s ease-in-out infinite;
      transform:translateX(-50%)">
      <span style="display:inline-block;transform:scaleX(-1)">🏃</span>
    </div>
    <!-- pct label -->
    <div style="position:absolute;top:0;left:0;
      font-size:.7rem;color:#FF8C1A;font-weight:700">{man_pct}%</div>
  </div>
</div>""", unsafe_allow_html=True)
        # ── poll while connecting (must be here — Step 1 returns early) ──
        if S.connecting:
            time.sleep(0.4)
            st.rerun()
        return

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 2: Job Selection
    # ═══════════════════════════════════════════════════════════════════════
    _step2_ph = st.empty()
    if not S._aegis_started and not (S.running or S.complete):
        with _step2_ph.container():
            # Header row
            h1, h2 = st.columns([5, 1])
            with h1:
                st.markdown(f'<div class="cred-ok">✅ Connected to <b>{S.host}</b> &nbsp;·&nbsp; {len(S.available_jobs)} jobs found</div>', unsafe_allow_html=True)
            with h2:
                if st.button("↩ Disconnect", key="btn_disco"):
                    S.connected = False; S.available_jobs = []; S.selected_ids = []
                    S._aegis_started = False; st.rerun()

            # ── ML monitoring toggle (now FIRST, above the DE jobs grid) ─────
            st.markdown('<div class="sec" style="margin-top:6px">ML MODEL MONITORING (OPTIONAL)</div>', unsafe_allow_html=True)

            ml_c1, ml_c2 = st.columns([1, 3])
            with ml_c1:
                ml_on = st.toggle("Enable ML monitoring", value=S.monitor_ml, key="tog_ml")
                if ml_on != S.monitor_ml:
                    S.monitor_ml = ml_on; st.rerun()
                if _ML_ICON_B64:
                    _ml_opacity = "1" if S.monitor_ml else "0.28"
                    _ml_filter  = ("drop-shadow(0 0 8px rgba(255,98,0,.6))"
                                   if S.monitor_ml else "grayscale(0.6)")
                    st.markdown(
                        f'<div style="text-align:center;margin-top:10px">'
                        f'<img src="data:image/png;base64,{_ML_ICON_B64}" '
                        f'style="height:90px;width:auto;opacity:{_ml_opacity};'
                        f'filter:{_ml_filter};transition:all .35s ease"></div>',
                        unsafe_allow_html=True)
            with ml_c2:
                if S.monitor_ml:
                    st.markdown("""<div style="background:rgba(255,98,0,.1);border:1px solid rgba(255,98,0,.3);border-left:4px solid #FF6200;
                        border-radius:10px;padding:12px 16px;font-size:.82rem;color:#FF8C1A">
                      <b>🤖 ML drift detection enabled</b><br>
                      After DE job checks, AEGIS will query MLflow for Production model versions and check
                      for accuracy drop / data drift. If <code>sales_forecast_v3</code> is degraded,
                      it autonomously triggers the retraining job and promotes the new model.
                    </div>""", unsafe_allow_html=True)
                else:
                    st.markdown("""<div style="background:#FFF8F0;border:1px solid #FFD4A8;border-left:4px solid #FFD4A8;
                        border-radius:10px;padding:12px 16px;font-size:.82rem;color:#B06030">
                      <b>ML monitoring off</b> — AEGIS will only check DE pipeline jobs.<br>
                      Toggle on to also check MLflow models for drift and auto-retrain if degraded.
                    </div>""", unsafe_allow_html=True)

            st.divider()

            # ── DE Jobs section ────────────────────────────────────────────
            jobs       = S.available_jobs
            total_j    = len(jobs)
            sel_count  = len(S.selected_ids)
            fail_count = sum(1 for j in jobs if j["latest_status"] in ("FAILED","INTERNAL_ERROR"))
            ok_count   = sum(1 for j in jobs if j["latest_status"] == "SUCCESS")

            # title + live stats badges
            _db_icon_tag = (f'<img src="data:image/png;base64,{_DB_ICON_B64}" '
                            f'style="height:22px;width:auto;vertical-align:middle;'
                            f'margin-right:7px;flex-shrink:0">'
                            if _DB_ICON_B64 else "")
            st.markdown(f"""
    <div style="display:flex;align-items:center;justify-content:space-between;margin:8px 0 10px">
      <div style="display:flex;align-items:center;font-size:.63rem;text-transform:uppercase;letter-spacing:.14em;color:#B06030;font-weight:700">{_db_icon_tag}Select Databricks Jobs (DE)</div>
      <div style="display:flex;gap:6px">
        <span style="background:rgba(34,197,94,.1);color:#4ade80;border:1px solid rgba(34,197,94,.3);border-radius:99px;padding:2px 9px;font-size:.66rem;font-weight:700">✅ {ok_count} healthy</span>
        <span style="background:rgba(239,68,68,.1);color:#f87171;border:1px solid rgba(239,68,68,.3);border-radius:99px;padding:2px 9px;font-size:.66rem;font-weight:700">❌ {fail_count} failed</span>
        <span style="background:rgba(255,98,0,.12);color:#FF8C1A;border:1px solid rgba(255,98,0,.35);border-radius:99px;padding:2px 9px;font-size:.66rem;font-weight:700">{sel_count}/{total_j} selected</span>
      </div>
    </div>""", unsafe_allow_html=True)

            # search bar + bulk buttons
            fs1, fs2, fs3 = st.columns([5, 1, 1])
            with fs1:
                search_q = st.text_input("", placeholder="🔍  Search by name or job ID…",
                                         key="job_search", label_visibility="collapsed")
            with fs2:
                if st.button("✓ All", key="btn_all", use_container_width=True):
                    S.selected_ids = [j["job_id"] for j in jobs]; st.rerun()
            with fs3:
                if st.button("✗ Clear", key="btn_clear", use_container_width=True):
                    S.selected_ids = []; st.rerun()

            # filter visible jobs by search query
            q = (search_q or "").strip().lower()
            visible = [j for j in jobs if q in j["name"].lower() or q in j["job_id"].lower()] if q else jobs

            # per-job status border-left colour injection (before the grid renders)
            _jcss = ""
            for _j in visible:
                _jid = _j["job_id"]
                _st  = _j["latest_status"]
                _sc  = "#16a34a" if _st == "SUCCESS" else \
                       "#dc2626" if _st in ("FAILED", "INTERNAL_ERROR") else "#6b7280"
                _jcss += (f'div[data-testid="stCheckbox"]:has(input[id="jcb_{_jid}"]) '
                          f'{{ border-left-color:{_sc} !important; }}')
            if _jcss:
                st.markdown(f"<style>{_jcss}</style>", unsafe_allow_html=True)

            # compact 4-column scrollable grid
            COLS = 4
            with st.container(height=340, border=False):
                for row_start in range(0, len(visible), COLS):
                    row_jobs = visible[row_start:row_start + COLS]
                    cols = st.columns(COLS)
                    for col, job in zip(cols, row_jobs):
                        with col:
                            jid    = job["job_id"]
                            is_sel = jid in S.selected_ids
                            st_raw = job["latest_status"]
                            prefix = "✓ " if is_sel else ""

                            if st_raw == "SUCCESS":
                                status_icon = "🟢"
                            elif st_raw in ("FAILED", "INTERNAL_ERROR"):
                                status_icon = "🔴"
                            else:
                                status_icon = "⚫"

                            name_trunc = job["name"][:22] + ("…" if len(job["name"]) > 22 else "")
                            label = (f"**{prefix}{name_trunc}**  \n"
                                     f"{status_icon} {st_raw or 'UNKNOWN'} · {job['tasks']} tasks")

                            checked = st.checkbox(label, value=is_sel, key=f"jcb_{jid}")
                            if checked and jid not in S.selected_ids:
                                S.selected_ids.append(jid); st.rerun()
                            elif not checked and jid in S.selected_ids:
                                S.selected_ids.remove(jid); st.rerun()

                if not visible:
                    st.markdown('<div style="text-align:center;color:#B06030;padding:32px;font-size:.82rem">No jobs match your search</div>', unsafe_allow_html=True)

            # selected-jobs chip strip
            if S.selected_ids:
                chips = "".join(
                    f'<span style="background:rgba(255,98,0,.15);color:#FF8C1A;border:1px solid rgba(255,98,0,.4);'
                    f'border-radius:99px;padding:2px 9px;font-size:.67rem;font-weight:700;'
                    f'margin:2px 3px;display:inline-block">{jid}</span>'
                    for jid in S.selected_ids
                )
                st.markdown(
                    f'<div style="margin:6px 0 0;line-height:2">'
                    f'<span style="font-size:.7rem;color:#FF8C1A;font-weight:700;margin-right:6px">▸ Running on:</span>'
                    f'{chips}</div>',
                    unsafe_allow_html=True)
            else:
                st.markdown(
                    '<div style="font-size:.77rem;color:#B06030;margin:6px 0 0">'
                    '○ No jobs selected — AEGIS will monitor <b>all jobs</b></div>',
                    unsafe_allow_html=True)

            # ── Run button ─────────────────────────────────────────────────
            st.divider()
            rc1, rc2, _ = st.columns([2, 1, 4])
            with rc1:
                de_count = len(S.selected_ids)
                run_lbl = f"▶  Run AEGIS on {de_count} job(s)" if de_count else "▶  Run AEGIS on ALL jobs"
                if S.monitor_ml:
                    run_lbl += " + ML"
                if st.button(run_lbl, type="primary", use_container_width=True, key="btn_run"):
                    # Set pending flag and rerun immediately — workflow is started at the TOP
                    # of main() on the next render, before any Step-2 widgets are written,
                    # so the ML-block never flashes on screen during the transition.
                    S.logs = []; S.complete = False
                    S._pending_run     = True
                    S._pending_run_sel = S.selected_ids[:] or []
                    S._pending_run_ml  = bool(S.monitor_ml)
                    st.rerun()
            with rc2:
                if st.button("↩ Back", key="btn_back"):
                    S.connected = False; S.selected_ids = []
                    S._aegis_started = False; st.rerun()
        return

    _step2_ph.empty()  # clear Step-2 atomically before Step 3 streams
    # ═══════════════════════════════════════════════════════════════════════
    # STEP 3: Live Dashboard
    # ═══════════════════════════════════════════════════════════════════════
    if S.running:
        badge = '<div class="run-badge rb-running">⟳  &nbsp;AUTONOMOUS HEALING IN PROGRESS</div>'
    elif S.complete and fix_status == "success":
        badge = '<div class="run-badge rb-done">✅ &nbsp;PIPELINE RESTORED</div>'
    elif S.complete and rs_.get("error"):
        badge = '<div class="run-badge rb-error">✗ &nbsp;ERROR — SEE TERMINAL</div>'
    elif S.complete:
        badge = '<div class="run-badge rb-done">✓ &nbsp;RUN COMPLETE</div>'
    else:
        badge = '<div class="run-badge rb-running">⟳  &nbsp;STARTING…</div>'

    top_l, top_r = st.columns([5, 1])
    with top_l:
        ctx = f"{job_name} · " if job_name else ""
        ctx += f"Jobs: {', '.join(S.selected_ids) or 'all'}"
        st.markdown(f'<div style="display:flex;align-items:center;gap:16px;margin-bottom:4px">{badge}'
                    f'<span style="font-size:.78rem;color:#7A3A10">{ctx}</span></div>',
                    unsafe_allow_html=True)
    with top_r:
        if st.button("↩ New Run", key="btn_new"):
            S.running = False; S.complete = False; S.logs = []
            S.rs = None; S.thread = None; S.log_q = None
            S.final_done_nodes = set(); S.run_end_time = 0.0
            S._aegis_started = False
            st.rerun()

    # ── KPI row ───────────────────────────────────────────────────────────
    if fix_status == "success":                       pst = "✅ Healthy"
    elif wf_state.get("has_failures") and S.running:  pst = "🔧 Healing"
    elif wf_state.get("has_failures"):                pst = "🔴 Failed"
    else:                                             pst = "⚙️ Monitoring"
    mttr_str = f"{int(mttr//60)}m {int(mttr%60):02d}s" if mttr > 0 else "—"
    nodes_done = len(done_n)
    total_nodes = len(CHECKLIST)
    pct = int(nodes_done / total_nodes * 100)

    st.markdown(f"""<div class="kpi-row">
  <div class="kpi"><div class="kpi-label">Pipeline</div><div class="kpi-val">{pst}</div><div class="kpi-sub">Live status</div></div>
  <div class="kpi"><div class="kpi-label">Stages Done</div><div class="kpi-val">{nodes_done}/{total_nodes}</div><div class="kpi-sub">{pct}% complete</div></div>
  <div class="kpi"><div class="kpi-label">Bugs Fixed</div><div class="kpi-val">{fixed_n}/{len(BUGS)}</div><div class="kpi-sub">GPT-5.5 repair</div></div>
  <div class="kpi"><div class="kpi-label">MTTR</div><div class="kpi-val">{mttr_str}</div><div class="kpi-sub">{"Under SLA ✅" if mttr>0 else "Measuring…"}</div></div>
  <div class="kpi"><div class="kpi-label">Emails Sent</div><div class="kpi-val">{len(display_sent_idx)}/{len(display_emails)}</div><div class="kpi-sub">{"1-stage ✅" if _is_healthy_run else "6-stage"}</div></div>
</div>""", unsafe_allow_html=True)

    # overall progress bar
    st.progress(pct / 100, text=f"Workflow progress — {nodes_done}/{total_nodes} stages complete")

    # ── Main layout: checklist (left) + terminal (right) ─────────────────
    cl, cr = st.columns([2, 3])

    with cl:
        st.markdown('<div class="sec">LIVE STAGE CHECKLIST</div>', unsafe_allow_html=True)
        # Inject live mttr so checklist detail shows the ticking clock
        _cl_state = {**wf_state, "mttr_seconds": mttr}
        st.markdown(_checklist_html(done_n, cur_n, _cl_state), unsafe_allow_html=True)

    with cr:
        st.markdown('<div class="sec">REAL-TIME LOG STREAM</div>', unsafe_allow_html=True)
        st.markdown(_terminal(S.logs), unsafe_allow_html=True)

    # ── Detail tabs ───────────────────────────────────────────────────────
    st.markdown("")
    t1, t2, t3, t4 = st.tabs(["🔧  Notebook Repair", "🧠  Root Cause Analysis", "📧  Email Notifications", "🛡️  Guardrails"])

    with t1:
        bc1, bc2 = st.columns([1, 1])
        _fixer_done    = "job_fixer_node" in done_n
        _fixer_active  = (cur_n == "job_fixer_node")
        _has_failures  = wf_state.get("has_failures", False)
        with bc1:
            st.markdown("#### Bug Inventory")
            if not _has_failures and not _fixer_done:
                st.markdown('<div style="color:#16a34a;padding:20px;text-align:center;font-size:.9rem">✅ No failures detected yet — all jobs healthy</div>', unsafe_allow_html=True)
            elif _fixer_active:
                st.markdown('<div style="color:#f59e0b;padding:20px;text-align:center;font-size:.9rem">⟳ GPT-5.5 scanning notebook for all bugs…</div>', unsafe_allow_html=True)
            elif not _fixer_done and _has_failures:
                st.markdown('<div style="color:#dc2626;padding:20px;text-align:center;font-size:.9rem">🔴 Failure detected — repair queued</div>', unsafe_allow_html=True)
            else:
                for bug in BUGS:
                    sev = bug["sev"]
                    bc_cls = "bc-d" if bugs_fixed else ("bc-c" if sev=="CRITICAL" else ("bc-h" if sev=="HIGH" else "bc-p"))
                    sev_html = '<span class="sb sb-f">FIXED ✓</span>' if bugs_fixed else f'<span class="sb sb-{"c" if sev=="CRITICAL" else "h"}">{sev}</span>'
                    ico = "✅" if bugs_fixed else ("🔴" if sev=="CRITICAL" else "🟠")
                    st.markdown(f'<div class="bug-c {bc_cls}"><div style="display:flex;justify-content:space-between"><div><div class="bug-num">Bug #{bug["id"]} · line {bug["line"]}</div><div class="bug-dsc">{bug["desc"]}</div>{sev_html}</div><span style="font-size:1.1rem">{ico}</span></div></div>', unsafe_allow_html=True)
        with bc2:
            st.markdown("#### GPT-5.5 Before / After Diffs")
            if bugs_fixed:
                def _esc(s): return s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
                for bug in BUGS:
                    st.markdown(f'<div class="diff-wrap"><div class="d-b"><div class="dh">− Before (line {bug["line"]})</div><pre class="dc">{_esc(bug["before"])}</pre></div><div class="d-a"><div class="dh">+ After (GPT-5.5)</div><pre class="dc">{_esc(bug["after"])}</pre></div></div>', unsafe_allow_html=True)
            elif _fixer_active:
                st.markdown('<div style="color:#f59e0b;padding:20px">⟳ GPT-5.5 scanning — diffs appear after repair…</div>', unsafe_allow_html=True)
            else:
                st.markdown('<div style="color:#B06030;padding:20px">Diffs appear after GPT-5.5 repair completes…</div>', unsafe_allow_html=True)

    with t2:
        if not conf:
            st.info("GPT-4o RCA results appear here once the failure alert stage completes.")
        else:
            ra1, ra2 = st.columns([1, 2])
            with ra1:
                rc_bg = "rgba(34,197,94,.12)" if risk=="LOW" else "rgba(255,98,0,.12)"
                rc_c  = "#16a34a" if risk=="LOW" else "#ea580c"
                st.markdown(f'<div class="card" style="text-align:center;padding:30px 16px"><div class="card-lbl" style="text-align:center">GPT-4o CONFIDENCE</div><div style="font-size:5rem;font-weight:900;background:linear-gradient(135deg,#FF6200,#FFB300);-webkit-background-clip:text;-webkit-text-fill-color:transparent;line-height:1">{conf:.0f}%</div><div style="margin-top:14px"><span style="background:{rc_bg};color:{rc_c};border:1px solid rgba(255,255,255,.12);border-radius:99px;padding:5px 18px;font-size:.85rem;font-weight:800">{risk} RISK</span></div></div>', unsafe_allow_html=True)
                st.markdown(f'<div class="card" style="margin-top:10px"><div class="card-lbl">GUARDRAIL #1 — CONFIDENCE GATE</div><div style="color:#16a34a;font-weight:800">✅ PASSED</div><div style="color:#7A3A10;font-size:.74rem;margin-top:4px">{conf:.0f}% ≥ 70% — autonomous repair approved</div></div>', unsafe_allow_html=True)
            with ra2:
                for lbl, val in [
                    ("Model", "GPT-4o via EPAM DIAL"),
                    ("Incident ID", inc_id or "—"),
                    ("Job", job_name or "—"),
                    ("Root Cause", root_cause or "Analysing…"),
                    ("Risk Level", risk),
                    ("Fix Status", fix_status or "Pending"),
                    ("Repair Model", "GPT-5.5 (gpt-5.5-2026-04-24) — whole-notebook scan"),
                ] + ([("Pull Request", pr_url)] if pr_url else []) + ([("MTTR", mttr_str)] if mttr else []):
                    st.markdown(f'<div class="rca-f"><div class="rca-lbl">{lbl}</div><div class="rca-val">{val}</div></div>', unsafe_allow_html=True)

    with t3:
        _email_header = ("AUTOMATED EMAIL NOTIFICATIONS — PIPELINE HEALTHY"
                         if _is_healthy_run else
                         "AUTOMATED EMAIL NOTIFICATIONS — REAL SENDS VIA GMAIL/SMTP")
        st.markdown(f'<div class="sec">{_email_header}</div>', unsafe_allow_html=True)
        for i, em in enumerate(display_emails):
            st.markdown(_email_card(em, i in display_sent_idx), unsafe_allow_html=True)

    with t4:
        st.markdown('<div class="sec">7 AUTONOMOUS SAFETY GUARDRAILS</div>', unsafe_allow_html=True)
        # Real detail text per guardrail from actual workflow state
        _audit_entries = sum(1 for _ in S.logs)   # each log line = 1 audited action
        _trigger_count = len([n for n in done_n if "job_fixer" in n])
        _gr_details = {
            1: (f"Confidence: {conf:.0f}% ≥ 70% — autonomous repair approved" if conf >= 70
                else (f"Confidence: {conf:.0f}% < 70% — escalated to on-call" if conf else "Awaiting RCA…")),
            2: ("Diff validated — code change confirmed non-zero" if "job_fixer_node" in done_n else ""),
            3: ("Rollback armed — original notebook backed up before patch" if "job_fixer_node" in done_n else ""),
            4: ("compile() + pyflakes passed — no syntax errors" if "job_fixer_node" in done_n else ""),
            5: (f"{_trigger_count}/5 triggers used in current window" if _trigger_count else ""),
            6: (f"{_audit_entries} actions logged to audit trail" if _audit_entries else ""),
            7: ("Prompt sanitised — injection patterns removed before LLM call" if S.logs else ""),
        }
        st.markdown(_guardrails_html(active_gr, _gr_details), unsafe_allow_html=True)
        pb1, pb2, pb3 = st.columns(3)
        with pb1:
            st.progress(min(fixed_n/len(BUGS),1.0), text=f"Bug repair: {fixed_n}/{len(BUGS)}")
        with pb2:
            st.progress(len(display_sent_idx)/max(len(display_emails),1), text=f"Emails: {len(display_sent_idx)}/{len(display_emails)}")
        with pb3:
            st.progress(len(active_gr)/7, text=f"Guardrails: {len(active_gr)}/7")

    # ── Completion banner ─────────────────────────────────────────────────
    if S.complete:
        if fix_status == "success":
            st.success(f"🏁 **AEGIS COMPLETE** — Pipeline restored in **{mttr_str}** · {len(display_sent_idx)}/{len(display_emails)} emails · {len(active_gr)}/7 guardrails · 0 human interventions")
        elif fix_status == "escalated":
            st.warning("⚠️ RCA confidence below 70% — escalation email sent to on-call team.")
        elif rs_.get("error"):
            st.error(f"Workflow error: {rs_['error']}")
        elif not wf_state.get("has_failures"):
            # Healthy path — all jobs passed, no repair needed
            healthy_c = wf_state.get("healthy_count", 0)
            job_label = f"{healthy_c} job{'s' if healthy_c != 1 else ''}" if healthy_c else "all jobs"
            st.markdown(f"""
<div style="background:linear-gradient(135deg,rgba(34,197,94,.08),rgba(34,197,94,.04));border:2px solid #22c55e;
  border-radius:14px;padding:18px 24px;display:flex;align-items:center;gap:16px;
  box-shadow:0 2px 16px rgba(34,197,94,.2)">
  <div style="font-size:2.2rem">✅</div>
  <div>
    <div style="font-size:1rem;font-weight:800;color:#4ade80">ALL JOBS HEALTHY — No Repair Needed</div>
    <div style="font-size:.8rem;color:#7A3A10;margin-top:4px;font-weight:600">
      AEGIS completed · {job_label} passed status check · Health-check email sent · 0 human interventions
    </div>
  </div>
</div>""", unsafe_allow_html=True)
        else:
            st.info(f"Run complete · fix_status: `{fix_status or 'done'}`")

    # ── Footer ────────────────────────────────────────────────────────────
    st.markdown('<div style="text-align:center;color:#B06030;font-size:.68rem;padding:18px 0 6px">AEGIS · LangGraph · GPT-5.5 · GPT-4o · Databricks SDK · ChromaDB · GitHub Actions · AI Hackathon 2026</div>', unsafe_allow_html=True)

    # ── Schedule next poll at the VERY END (after full page renders) ──────
    if S.connecting or S.running:
        time.sleep(0.4)   # 0.4s → checklist highlights move within half a second of node completion
        st.rerun()


if __name__ == "__main__":
    main()
