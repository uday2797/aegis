"""
AEGIS Live Dashboard
Streamlit-based real-time monitoring dashboard.
Shows incident feed, MTTR metrics, auto-heal rate, and failure-type breakdown.

Run alongside the demo:
    streamlit run demo/dashboard.py
"""
import sys
import os
import time
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd

# ─── Page config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AEGIS — AI Reliability Dashboard",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─── Custom CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main { background-color: #0e1117; }
    .metric-card {
        background: #1c1f26;
        border-radius: 12px;
        padding: 20px;
        border: 1px solid #2d3139;
    }
    .healed { color: #00d26a; font-weight: bold; }
    .escalated { color: #ff6b6b; font-weight: bold; }
    .risk-low { color: #00d26a; }
    .risk-medium { color: #ffa94d; }
    .risk-high { color: #ff6b6b; }
    div[data-testid="metric-container"] {
        background-color: #1c1f26;
        border: 1px solid #2d3139;
        padding: 16px;
        border-radius: 10px;
    }
</style>
""", unsafe_allow_html=True)


# ─── Load incidents from ChromaDB ────────────────────────────────────────────
@st.cache_resource
def get_knowledge_store():
    """Returns ChromaDB collection or None."""
    try:
        import chromadb
        import yaml
        config = yaml.safe_load(open("config/config.yaml"))
        ks_cfg = config.get("knowledge_store", {})
        persist_dir = ks_cfg.get("persist_dir", "./data/knowledge_store")
        collection_name = ks_cfg.get("collection_name", "aegis_incidents")
        client = chromadb.PersistentClient(path=persist_dir)
        return client.get_or_create_collection(name=collection_name)
    except Exception:
        return None


def load_incidents() -> pd.DataFrame:
    """Pull all resolved incidents from ChromaDB into a DataFrame."""
    collection = get_knowledge_store()
    if collection is None or collection.count() == 0:
        return pd.DataFrame()

    try:
        result = collection.get(include=["metadatas"])
        rows = []
        for meta in result.get("metadatas", []):
            rows.append({
                "incident_id": meta.get("incident_id", ""),
                "job_name": meta.get("job_name", ""),
                "failure_type": meta.get("failure_type", ""),
                "root_cause": meta.get("root_cause", ""),
                "action_taken": meta.get("action_taken", ""),
                "outcome": meta.get("outcome", ""),
                "auto_healed": meta.get("auto_healed", "False") == "True",
                "timestamp": meta.get("timestamp", ""),
            })
        df = pd.DataFrame(rows)
        # Parse MTTR from outcome string (e.g. "... MTTR: 94s.")
        df["mttr_seconds"] = df["outcome"].str.extract(r"MTTR:\s*(\d+)s").astype(float)
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df = df.sort_values("timestamp", ascending=False).reset_index(drop=True)
        return df
    except Exception as e:
        st.error(f"Error loading incidents: {e}")
        return pd.DataFrame()


# ─── Header ──────────────────────────────────────────────────────────────────
col_logo, col_title, col_refresh = st.columns([1, 8, 2])
with col_logo:
    st.markdown("## 🛡️")
with col_title:
    st.markdown("## AEGIS — AI-Engine for Guardian Intelligence & Self-healing")
    st.caption("Autonomous Reliability Dashboard · Live Incident Feed")
with col_refresh:
    st.markdown("<br>", unsafe_allow_html=True)
    auto_refresh = st.toggle("Auto-refresh", value=True)

st.divider()

# ─── Load data ───────────────────────────────────────────────────────────────
df = load_incidents()

if df.empty:
    st.info(
        "No incidents in knowledge store yet.\n\n"
        "Run `python demo/seed_knowledge.py` to pre-seed with historical data,\n"
        "then run `python demo/run_demo.py` to generate live incidents."
    )
    if auto_refresh:
        time.sleep(3)
        st.rerun()
    st.stop()

# ─── KPI Metrics ─────────────────────────────────────────────────────────────
total = len(df)
auto_healed_count = df["auto_healed"].sum()
heal_rate = auto_healed_count / total * 100 if total > 0 else 0
avg_mttr = df["mttr_seconds"].dropna().mean()
avg_mttr_display = f"{avg_mttr:.0f}s" if pd.notna(avg_mttr) else "N/A"
manual_equiv_min = total * 45  # 45 min avg manual MTTR
reduction_pct = int((manual_equiv_min * 60 - df["mttr_seconds"].dropna().sum()) / (manual_equiv_min * 60) * 100) if total > 0 else 0

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total Incidents", total)
col2.metric("Auto-Healed", f"{auto_healed_count}/{total}", f"{heal_rate:.0f}%")
col3.metric("Avg MTTR (AEGIS)", avg_mttr_display, "↓ vs 45 min manual")
col4.metric("Manual Equiv.", f"~{manual_equiv_min} min", f"{total} × 45 min engineer time")
col5.metric("MTTR Reduction", f"~{reduction_pct}%", "vs manual firefighting")

st.divider()

# ─── Charts row ──────────────────────────────────────────────────────────────
chart_col1, chart_col2 = st.columns(2)

with chart_col1:
    st.subheader("Incidents by Failure Type")
    type_counts = df["failure_type"].value_counts().reset_index()
    type_counts.columns = ["Failure Type", "Count"]
    type_counts["Failure Type"] = type_counts["Failure Type"].str.replace("_", " ").str.title()
    st.bar_chart(type_counts.set_index("Failure Type"))

with chart_col2:
    st.subheader("Auto-Heal vs Escalated")
    status_counts = df["auto_healed"].map({True: "Auto-Healed ✅", False: "Escalated ⚠️"}).value_counts()
    st.bar_chart(status_counts)

# ─── MTTR timeline ───────────────────────────────────────────────────────────
if df["mttr_seconds"].notna().sum() >= 2:
    st.subheader("MTTR Timeline (seconds per incident)")
    timeline_df = df[["incident_id", "mttr_seconds", "failure_type"]].dropna(subset=["mttr_seconds"])
    timeline_df = timeline_df.sort_values("incident_id")
    st.line_chart(timeline_df.set_index("incident_id")["mttr_seconds"])

st.divider()

# ─── Incident table ──────────────────────────────────────────────────────────
st.subheader("Recent Incidents")

display_df = df[[
    "incident_id", "failure_type", "job_name", "root_cause",
    "mttr_seconds", "auto_healed", "action_taken"
]].copy()

display_df["failure_type"] = display_df["failure_type"].str.replace("_", " ").str.title()
display_df["auto_healed"] = display_df["auto_healed"].map({True: "✅ Auto-Healed", False: "⚠️ Escalated"})
display_df["mttr_seconds"] = display_df["mttr_seconds"].apply(
    lambda x: f"{x:.0f}s" if pd.notna(x) else "—"
)
display_df.columns = ["Incident ID", "Failure Type", "Job", "Root Cause", "MTTR", "Status", "Action Taken"]

st.dataframe(display_df, use_container_width=True, hide_index=True)

# ─── Detail expander ─────────────────────────────────────────────────────────
st.subheader("Incident Detail")
if not df.empty:
    selected_id = st.selectbox("Select incident to inspect:", df["incident_id"].tolist())
    row = df[df["incident_id"] == selected_id].iloc[0]
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"**Job:** `{row['job_name']}`")
        st.markdown(f"**Failure Type:** `{row['failure_type'].replace('_', ' ').title()}`")
        st.markdown(f"**Auto-Healed:** {'✅ Yes' if row['auto_healed'] else '⚠️ No'}")
        mttr_val = f"{row['mttr_seconds']:.0f}s" if pd.notna(row.get('mttr_seconds')) else "—"
        st.markdown(f"**MTTR:** `{mttr_val}`")
    with c2:
        st.markdown(f"**Root Cause:**\n> {row['root_cause']}")
        st.markdown(f"**Action Taken:**\n> {row['action_taken']}")
        st.markdown(f"**Outcome:**\n> {row['outcome']}")

# ─── Auto-refresh ────────────────────────────────────────────────────────────
if auto_refresh:
    time.sleep(3)
    st.rerun()
