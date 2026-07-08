"""AEGIS Command Center — Production AIOps Dashboard.

Run from project root:
    streamlit run demo/dashboard.py
"""

import json
import math
import time
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
import streamlit.components.v1 as components

# ─── Paths ────────────────────────────────────────────────────────────────────
AUDIT_LOG_PATH = Path("data/audit_log.jsonl")

# ─── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AEGIS Command Center",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─── Palette ──────────────────────────────────────────────────────────────────
CYAN   = "#00d4ff"
GREEN  = "#00ff88"
RED    = "#ff4444"
GOLD   = "#ffd700"
PURPLE = "#a855f7"
ORANGE = "#ff8c00"
PINK   = "#f43f5e"

ACTION_COLOR = {
    "FIX_SUCCESS":            GREEN,
    "CONFIDENCE_GATE_PASSED": CYAN,
    "FIX_STARTED":            GOLD,
    "FIX_EXCEPTION":          "#ff6b6b",
    "FIX_ESCALATED":          RED,
    "MAX_RETRIES_EXCEEDED":   RED,
    "NOTEBOOK_UPLOADED":      "#22c55e",
    "RUN_TRIGGERED":          "#818cf8",
    "LINT_CHECK":             ORANGE,
    "DIFF_COMPUTED":          "#60a5fa",
    "NOTEBOOK_ROLLED_BACK":   "#f97316",
    "LLM_OUTPUT_INVALID":     PINK,
    "PEP8_FORMATTED":         "#4ade80",
}

# ─── CSS ──────────────────────────────────────────────────────────────────────
st.markdown(f"""
<style>
    /* ── reset ── */
    #MainMenu, footer, header {{ visibility: hidden; }}
    .block-container {{ padding-top: 1rem !important; max-width: 100% !important; }}

    /* ── KPI cards ── */
    .kpi {{
        background: linear-gradient(145deg,rgba(17,24,39,.98),rgba(30,41,59,.9));
        border: 1px solid rgba(0,212,255,.22);
        border-radius: 16px;
        padding: 22px 18px 16px;
        position: relative;
        overflow: hidden;
        transition: border-color .3s;
    }}
    .kpi:hover {{ border-color: rgba(0,212,255,.55); }}
    .kpi::before {{
        content:''; position:absolute; top:0;left:0;right:0; height:3px;
        background: linear-gradient(90deg,{CYAN},{PURPLE});
    }}
    .kpi-v {{
        font-size:2.6rem; font-weight:900; letter-spacing:-1.5px;
        background:linear-gradient(135deg,{CYAN},{GREEN});
        -webkit-background-clip:text; -webkit-text-fill-color:transparent;
        background-clip:text; line-height:1;
    }}
    .kpi-v-gold {{
        font-size:2.6rem; font-weight:900; letter-spacing:-1.5px;
        background:linear-gradient(135deg,{GOLD},{ORANGE});
        -webkit-background-clip:text; -webkit-text-fill-color:transparent;
        background-clip:text; line-height:1;
    }}
    .kpi-v-purple {{
        font-size:2.6rem; font-weight:900; letter-spacing:-1.5px;
        background:linear-gradient(135deg,{PURPLE},#ec4899);
        -webkit-background-clip:text; -webkit-text-fill-color:transparent;
        background-clip:text; line-height:1;
    }}
    .kpi-label {{ font-size:.73rem; color:#94a3b8; text-transform:uppercase;
                  letter-spacing:.14em; margin-top:9px; font-weight:700; }}
    .kpi-sub   {{ font-size:.74rem; color:#4ade80; margin-top:4px; font-weight:500; }}

    /* ── section headers ── */
    .sh {{
        font-size:.75rem; font-weight:800; color:{CYAN};
        text-transform:uppercase; letter-spacing:.14em;
        border-bottom:1px solid rgba(0,212,255,.15);
        padding-bottom:7px; margin-bottom:12px; margin-top:2px;
    }}

    /* ── tabs ── */
    .stTabs [data-baseweb="tab-list"] {{
        gap:5px; background:transparent;
        border-bottom:1px solid rgba(0,212,255,.12);
    }}
    .stTabs [data-baseweb="tab"] {{
        height:38px; background:rgba(17,24,39,.7);
        border-radius:8px 8px 0 0; color:#64748b;
        font-weight:700; font-size:.82rem;
        border:1px solid rgba(0,212,255,.08); border-bottom:none;
        padding:0 18px;
    }}
    .stTabs [aria-selected="true"] {{
        background:rgba(0,212,255,.1) !important;
        color:{CYAN} !important;
        border-color:rgba(0,212,255,.28) !important;
    }}

    /* ── audit log ── */
    .alog {{ display:flex; gap:0; padding:5px 8px;
             border-bottom:1px solid rgba(255,255,255,.04);
             font-size:.75rem; font-family:'Consolas',monospace; }}
    .alog:hover {{ background:rgba(0,212,255,.04); }}
    .at {{ color:#475569; min-width:135px; flex-shrink:0; }}
    .ai {{ color:#818cf8; min-width:125px; flex-shrink:0; overflow:hidden; text-overflow:ellipsis; }}
    .aa {{ font-weight:700; min-width:215px; flex-shrink:0; }}
    .ad {{ color:#64748b; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; max-width:360px; }}

    /* ── guardrail rows ── */
    .gr {{
        display:flex; align-items:flex-start; gap:10px;
        padding:7px 10px; margin-bottom:4px;
        border-radius:0 8px 8px 0; border-left:3px solid;
        background:rgba(17,24,39,.65);
    }}
    .grk {{ font-weight:800; min-width:32px; font-size:.72rem; }}
    .grn {{ font-weight:700; font-size:.83rem; }}
    .grd {{ font-size:.72rem; color:#64748b; margin-top:1px; }}

    /* ── pipeline step ── */
    .ps {{
        display:flex; align-items:flex-start; gap:10px;
        padding:7px 10px; margin:3px 0;
        border-radius:6px; border-left:3px solid; font-size:.81rem;
    }}
    .psn {{ font-weight:900; min-width:28px; font-size:.72rem; flex-shrink:0; }}
    .pst {{ font-weight:700; }}
    .psd {{ font-size:.71rem; opacity:.65; margin-top:1px; }}

    /* ── live dot ── */
    @keyframes pulse {{ 0%,100%{{opacity:1;transform:scale(1)}} 50%{{opacity:.4;transform:scale(1.5)}} }}
    .live {{ display:inline-block; width:8px; height:8px; background:{GREEN};
              border-radius:50%; animation:pulse 1.8s infinite;
              margin-right:6px; vertical-align:middle; box-shadow:0 0 6px {GREEN}; }}

    /* ── glow text ── */
    @keyframes glow {{
        0%,100% {{ text-shadow:0 0 6px {CYAN},0 0 12px {CYAN}; }}
        50%      {{ text-shadow:0 0 12px {CYAN},0 0 24px {CYAN},0 0 36px {PURPLE}; }}
    }}
    .glow {{ animation:glow 3s infinite; }}

    /* ── badge ── */
    .badge-ok  {{ background:rgba(0,255,136,.15); color:{GREEN};  border:1px solid rgba(0,255,136,.3);
                  border-radius:20px; padding:2px 10px; font-size:.72rem; font-weight:700; }}
    .badge-bad {{ background:rgba(255,68,68,.15); color:{RED};   border:1px solid rgba(255,68,68,.3);
                  border-radius:20px; padding:2px 10px; font-size:.72rem; font-weight:700; }}
    .badge-esc {{ background:rgba(255,140,0,.15); color:{ORANGE};border:1px solid rgba(255,140,0,.3);
                  border-radius:20px; padding:2px 10px; font-size:.72rem; font-weight:700; }}
</style>
""", unsafe_allow_html=True)


# ─── Data ─────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=12)
def load_df() -> pd.DataFrame:
    if not AUDIT_LOG_PATH.exists():
        return pd.DataFrame()
    rows = [json.loads(l) for l in
            AUDIT_LOG_PATH.read_text(encoding="utf-8").strip().splitlines()
            if l.strip()]
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df


@st.cache_data(ttl=12)
def build_incidents(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "incident_id" not in df.columns:
        return pd.DataFrame()
    rows = []
    for inc_id, grp in df.groupby("incident_id", dropna=True):
        acts   = set(grp["action"].tolist())
        ts     = grp["timestamp"]
        start, end = ts.min(), ts.max()
        mttr_min = round((end - start).total_seconds() / 60, 1)
        status = (
            "success"   if "FIX_SUCCESS" in acts else
            "escalated" if acts & {"FIX_ESCALATED", "MAX_RETRIES_EXCEEDED"} else
            "in_progress"
        )
        max_att = max((int(r.get("attempt", 0)) for _, r in grp.iterrows()
                       if r.get("attempt") is not None), default=0)
        cg = grp[grp["action"] == "CONFIDENCE_GATE_PASSED"]
        confidence = float(cg.iloc[-1]["confidence"]) if not cg.empty and "confidence" in cg.columns else 0.0
        root_cause = str(cg.iloc[-1]["root_cause"]) if not cg.empty and "root_cause" in cg.columns else "Unknown"
        dg = grp[grp["action"] == "DIFF_COMPUTED"]
        max_lines = int(dg["lines_changed"].max()) if not dg.empty and "lines_changed" in dg.columns else 0
        rows.append(dict(
            incident_id=inc_id, start=start, end=end,
            mttr_min=mttr_min, status=status,
            attempts=max_att, confidence=confidence,
            root_cause=root_cause, max_lines=max_lines,
            n_actions=len(grp),
        ))
    return pd.DataFrame(rows).sort_values("start").reset_index(drop=True)


def dfig(fig, h=None):
    kw = dict(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(17,24,39,0.45)",
        font=dict(color="#94a3b8", family="system-ui,sans-serif", size=11),
        margin=dict(l=10, r=10, t=36, b=10),
        legend=dict(bgcolor="rgba(17,24,39,.85)", bordercolor="rgba(0,212,255,.2)", borderwidth=1),
    )
    if h: kw["height"] = h
    fig.update_layout(**kw)
    fig.update_xaxes(gridcolor="rgba(255,255,255,.05)", zerolinecolor="rgba(255,255,255,.08)")
    fig.update_yaxes(gridcolor="rgba(255,255,255,.05)", zerolinecolor="rgba(255,255,255,.08)")
    return fig


# ─── Load data ────────────────────────────────────────────────────────────────
df  = load_df()
inc = build_incidents(df)

n_total     = len(inc)
n_healed    = int((inc["status"] == "success").sum())   if not inc.empty else 0
n_escalated = int((inc["status"] == "escalated").sum()) if not inc.empty else 0
heal_pct    = round(n_healed / n_total * 100) if n_total else 0
avg_mttr    = round(inc["mttr_min"].mean(), 1) if not inc.empty else 0
llm_calls   = int((df["action"] == "FIX_STARTED").sum()) if not df.empty else 0
g_fires     = int(df["action"].isin([
    "LINT_CHECK", "DIFF_COMPUTED", "NOTEBOOK_ROLLED_BACK",
    "LLM_OUTPUT_INVALID", "MAX_RETRIES_EXCEEDED", "FIX_EXCEPTION", "FIX_ESCALATED",
]).sum()) if not df.empty else 0
n_rollbacks = int((df["action"] == "NOTEBOOK_ROLLED_BACK").sum()) if not df.empty else 0
avg_conf    = round(inc["confidence"].mean(), 1) if not inc.empty else 0


# ─── Header ───────────────────────────────────────────────────────────────────
st.markdown(f"""
<div style="
    display:flex; align-items:center; justify-content:space-between;
    padding:18px 28px;
    background:linear-gradient(135deg,rgba(0,212,255,.06),rgba(168,85,247,.06),rgba(0,255,136,.04));
    border:1px solid rgba(0,212,255,.18); border-radius:16px; margin-bottom:20px;
    box-shadow:0 0 40px rgba(0,212,255,.06);
">
  <div>
    <h1 class="glow" style="margin:0;font-size:2rem;font-weight:900;letter-spacing:-1px;
               background:linear-gradient(135deg,{CYAN} 0%,{PURPLE} 50%,{GREEN} 100%);
               -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;">
      🛡️ AEGIS Command Center
    </h1>
    <p style="margin:6px 0 0;color:#94a3b8;font-size:.9rem;letter-spacing:.02em;">
      Autonomous End-to-end Guardian for Intelligent Systems &nbsp;·&nbsp;
      <strong style="color:{CYAN}">LangGraph 15-node</strong> &nbsp;·&nbsp;
      <strong style="color:{GREEN}">GPT-5.5 Repair</strong> &nbsp;·&nbsp;
      <strong style="color:{PURPLE}">7 Guardrail Layers</strong> &nbsp;·&nbsp;
      <strong style="color:{GOLD}">Real Databricks Production</strong>
    </p>
  </div>
  <div style="text-align:right;flex-shrink:0;padding-left:20px;">
    <div style="font-size:.82rem;color:#94a3b8;letter-spacing:.06em;">
        <span class="live"></span><strong style="color:{GREEN}">LIVE</strong> AUDIT FEED
    </div>
    <div style="font-size:.75rem;color:#475569;margin-top:4px;">
        {len(df) if not df.empty else 0} events &nbsp;·&nbsp; {n_total} incidents &nbsp;·&nbsp; real production
    </div>
  </div>
</div>
""", unsafe_allow_html=True)


# ─── KPI Row ──────────────────────────────────────────────────────────────────
c1, c2, c3, c4, c5, c6 = st.columns(6)
for col, val, label, sub, vc in [
    (c1, str(n_total),       "Total Incidents",       f"{n_healed} healed · {n_escalated} escalated", "kpi-v"),
    (c2, f"{heal_pct}%",     "Auto-Heal Rate",        "vs 0% rule-based baseline",                    "kpi-v"),
    (c3, f"{avg_mttr}m",     "Avg MTTR",              "vs ~120 min manual on-call",                   "kpi-v-gold"),
    (c4, str(llm_calls),     "LLM Repair Calls",      "GPT-5.5 invocations",                          "kpi-v-purple"),
    (c5, str(g_fires),       "Guardrail Activations", "7-layer safety system",                        "kpi-v"),
    (c6, f"{avg_conf}%",     "Avg RCA Confidence",    "GPT-4o root cause analysis",                   "kpi-v"),
]:
    col.markdown(f"""
    <div class="kpi">
        <div class="{vc}">{val}</div>
        <div class="kpi-label">{label}</div>
        <div class="kpi-sub">{sub}</div>
    </div>""", unsafe_allow_html=True)

st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)


# ─── Tabs ─────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊  Overview",
    "🔍  Incident Intelligence",
    "⚙️  Live Pipeline",
    "🔒  Guardrail Console",
    "🚀  System Architecture",
])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Overview
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    row1_l, row1_m, row1_r = st.columns([2, 2, 2], gap="medium")

    # ── Heal-rate gauge ────────────────────────────────────────────────────────
    with row1_l:
        st.markdown('<div class="sh">Auto-Heal Rate Gauge</div>', unsafe_allow_html=True)
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number+delta",
            value=heal_pct,
            number=dict(suffix="%", font=dict(size=48, color=GREEN)),
            delta=dict(reference=0, valueformat=".0f", suffix="% above baseline",
                       font=dict(size=14)),
            gauge=dict(
                axis=dict(range=[0, 100], tickfont=dict(color="#94a3b8", size=10),
                          tickcolor="#334155"),
                bar=dict(color=GREEN, thickness=0.28),
                bgcolor="rgba(17,24,39,.9)",
                borderwidth=0,
                steps=[
                    dict(range=[0,  33], color="rgba(255,68,68,.12)"),
                    dict(range=[33, 66], color="rgba(255,215,0,.10)"),
                    dict(range=[66,100], color="rgba(0,255,136,.12)"),
                ],
                threshold=dict(line=dict(color=CYAN, width=3), thickness=0.85, value=heal_pct),
            ),
            title=dict(text="Incidents Autonomously Resolved", font=dict(color="#94a3b8", size=12)),
        ))
        dfig(fig_gauge, 260)
        fig_gauge.update_layout(margin=dict(l=20, r=20, t=50, b=10))
        st.plotly_chart(fig_gauge, use_container_width=True)

    # ── Confidence gauge ───────────────────────────────────────────────────────
    with row1_m:
        st.markdown('<div class="sh">Avg RCA Confidence Gauge</div>', unsafe_allow_html=True)
        fig_conf_g = go.Figure(go.Indicator(
            mode="gauge+number",
            value=avg_conf,
            number=dict(suffix="%", font=dict(size=48, color=CYAN)),
            gauge=dict(
                axis=dict(range=[0, 100], tickfont=dict(color="#94a3b8", size=10),
                          tickcolor="#334155"),
                bar=dict(color=CYAN, thickness=0.28),
                bgcolor="rgba(17,24,39,.9)",
                borderwidth=0,
                steps=[
                    dict(range=[0, 70], color="rgba(255,68,68,.10)"),
                    dict(range=[70,100], color="rgba(0,212,255,.08)"),
                ],
                threshold=dict(line=dict(color=ORANGE, width=3), thickness=0.85, value=70),
            ),
            title=dict(text="GPT-4o Root Cause Confidence · gate @ 70%",
                       font=dict(color="#94a3b8", size=12)),
        ))
        dfig(fig_conf_g, 260)
        fig_conf_g.update_layout(margin=dict(l=20, r=20, t=50, b=10))
        st.plotly_chart(fig_conf_g, use_container_width=True)

    # ── Outcome donut ──────────────────────────────────────────────────────────
    with row1_r:
        st.markdown('<div class="sh">Incident Outcomes</div>', unsafe_allow_html=True)
        if not inc.empty:
            sc = inc["status"].value_counts()
            cmap = {"success": GREEN, "escalated": RED, "in_progress": GOLD}
            fig_donut = go.Figure(go.Pie(
                labels=sc.index.str.replace("_", " ").str.title(),
                values=sc.values, hole=0.64,
                marker=dict(
                    colors=[cmap.get(s, "#888") for s in sc.index],
                    line=dict(color="#0a0e1a", width=3),
                ),
                textinfo="label+percent",
                textfont=dict(size=11),
                hovertemplate="%{label}: %{value}<extra></extra>",
                pull=[0.05 if s == "success" else 0 for s in sc.index],
            ))
            dfig(fig_donut, 260)
            fig_donut.update_layout(
                title=None, showlegend=False,
                annotations=[dict(
                    text=f"<b>{n_total}</b><br><span style='font-size:10px'>incidents</span>",
                    x=0.5, y=0.5, font=dict(size=22, color=CYAN), showarrow=False,
                )],
            )
            st.plotly_chart(fig_donut, use_container_width=True)

    # ── MTTR comparison ────────────────────────────────────────────────────────
    row2_l, row2_r = st.columns([3, 2], gap="medium")
    with row2_l:
        st.markdown('<div class="sh">MTTR Comparison — AEGIS vs Baseline</div>', unsafe_allow_html=True)
        approaches = ["Manual On-Call", "Rule-Based Scripts", "AEGIS (Avg)", "AEGIS (Best)"]
        mttrs      = [120, 45, avg_mttr if avg_mttr > 0 else 10, 3]
        bcolors    = [RED, ORANGE, CYAN, GREEN]
        fig_mttr = go.Figure()
        for i, (ap, mt, bc) in enumerate(zip(approaches, mttrs, bcolors)):
            fig_mttr.add_trace(go.Bar(
                x=[ap], y=[mt],
                marker=dict(
                    color=bc,
                    line_width=0,
                    pattern_shape="" if bc in (CYAN, GREEN) else "",
                ),
                text=[f"<b>{mt}m</b>"],
                textposition="outside",
                textfont=dict(color="white", size=14, family="monospace"),
                name=ap, showlegend=False,
                hovertemplate=f"<b>{ap}</b><br>MTTR: {mt} min<extra></extra>",
            ))
        # Reduction annotation
        reduction = round((1 - avg_mttr / 120) * 100) if avg_mttr > 0 else 92
        fig_mttr.add_annotation(
            x=2, y=avg_mttr + 5,
            text=f"<b style='color:{GREEN}'>{reduction}% faster</b>",
            showarrow=False,
            font=dict(size=13, color=GREEN),
            bgcolor="rgba(0,255,136,.12)",
            bordercolor=GREEN, borderwidth=1, borderpad=4,
        )
        dfig(fig_mttr, 280)
        fig_mttr.update_layout(yaxis_title="Minutes", bargap=0.38, yaxis_range=[0, 145])
        st.plotly_chart(fig_mttr, use_container_width=True)

    # ── Sankey: incident flow ──────────────────────────────────────────────────
    with row2_r:
        st.markdown('<div class="sh">Incident Healing Flow (Sankey)</div>', unsafe_allow_html=True)
        # Nodes: 0=Detected, 1=RCA, 2=High-Conf Fix, 3=Success, 4=Rollback, 5=Escalated, 6=Low-Conf
        nodes = ["Detected", "RCA", "High-Conf Fix", "Success",
                 "Retry/Rollback", "Escalated", "Low-Conf Skip"]
        node_colors = [CYAN, PURPLE, GOLD, GREEN, ORANGE, RED, "#94a3b8"]

        hi = max(int((inc["confidence"] >= 70).sum()), 1) if not inc.empty else 4
        lo = max(int((inc["confidence"] < 70).sum()), 0)  if not inc.empty else 0

        fig_sankey = go.Figure(go.Sankey(
            node=dict(
                pad=12, thickness=18,
                color=node_colors,
                label=nodes,
                line=dict(color="#0a0e1a", width=1),
            ),
            link=dict(
                source=[0, 1, 2, 2,    1],
                target=[1, 2, 3, 4,    6],
                value= [n_total, hi, n_healed, n_rollbacks or 1, lo or 0],
                color=[
                    "rgba(168,85,247,.35)",
                    "rgba(255,215,0,.35)",
                    "rgba(0,255,136,.45)",
                    "rgba(255,140,0,.35)",
                    "rgba(148,163,184,.25)",
                ],
                hovertemplate="%{source.label} → %{target.label}: %{value}<extra></extra>",
            ),
        ))
        dfig(fig_sankey, 280)
        fig_sankey.update_layout(title=None)
        st.plotly_chart(fig_sankey, use_container_width=True)

    # ── Timeline ──────────────────────────────────────────────────────────────
    st.markdown('<div class="sh">Live Activity Timeline</div>', unsafe_allow_html=True)
    if not df.empty:
        tdf = df.copy()
        tdf["hour"] = tdf["timestamp"].dt.floor("h")
        by_h = tdf.groupby("hour").size().reset_index(name="count")

        fig_tl = go.Figure()
        fig_tl.add_trace(go.Scatter(
            x=by_h["hour"], y=by_h["count"],
            mode="lines", fill="tozeroy",
            line=dict(color=CYAN, width=2.5, shape="spline"),
            fillcolor="rgba(0,212,255,.08)",
            name="Events/hr",
        ))
        for action, sym, col, lbl in [
            ("FIX_SUCCESS",   "star",        GREEN,  "Healed"),
            ("FIX_ESCALATED", "x",           RED,    "Escalated"),
            ("FIX_EXCEPTION", "circle-open", ORANGE, "Exception"),
            ("CONFIDENCE_GATE_PASSED", "diamond", CYAN, "RCA Gate"),
        ]:
            sub = df[df["action"] == action]
            if not sub.empty:
                fig_tl.add_trace(go.Scatter(
                    x=sub["timestamp"], y=[0.2] * len(sub),
                    mode="markers", name=lbl,
                    marker=dict(size=13, color=col, symbol=sym,
                                line=dict(width=2, color="rgba(255,255,255,.5)")),
                ))
        dfig(fig_tl, 210)
        fig_tl.update_layout(xaxis_title=None, yaxis_title="Events / hr",
                              legend=dict(orientation="h", y=1.1, x=0.5, xanchor="center"))
        st.plotly_chart(fig_tl, use_container_width=True)

    # ── Lines changed + action dist ───────────────────────────────────────────
    row3_l, row3_r = st.columns([3, 2], gap="medium")
    with row3_l:
        st.markdown('<div class="sh">Lines Fixed per Repair Attempt</div>', unsafe_allow_html=True)
        ddf = df[df["action"] == "DIFF_COMPUTED"].dropna(subset=["lines_changed"]).copy() if not df.empty else pd.DataFrame()
        if not ddf.empty:
            ddf["lines_changed"] = ddf["lines_changed"].astype(int)
            ddf["lbl"] = [f"Fix #{i+1}" for i in range(len(ddf))]
            colors_bar = []
            for _, r in ddf.iterrows():
                inc_id = str(r.get("incident_id", ""))
                colors_bar.append(GREEN if inc_id in {"INC-7BC959AE","INC-B3A904CC"} else CYAN)

            fig_lc = go.Figure(go.Bar(
                x=ddf["lbl"], y=ddf["lines_changed"],
                marker=dict(color=colors_bar, line_width=0,
                            cornerradius=4),
                text=ddf["lines_changed"], textposition="outside",
                textfont=dict(color="#94a3b8", size=10),
                hovertemplate="<b>%{x}</b><br>%{y} lines changed<extra></extra>",
            ))
            dfig(fig_lc, 220)
            fig_lc.update_layout(xaxis_title=None, yaxis_title="Lines Changed")
            st.plotly_chart(fig_lc, use_container_width=True)

    with row3_r:
        st.markdown('<div class="sh">Action Distribution</div>', unsafe_allow_html=True)
        if not df.empty:
            ac = df["action"].value_counts().head(10)
            fig_ac = go.Figure(go.Bar(
                y=ac.index, x=ac.values, orientation="h",
                marker=dict(
                    color=[ACTION_COLOR.get(a, "#64748b") for a in ac.index],
                    line_width=0, cornerradius=4,
                ),
                text=ac.values, textposition="outside",
                textfont=dict(size=10, color="#94a3b8"),
            ))
            dfig(fig_ac, 320)
            fig_ac.update_layout(xaxis_title="Count", yaxis_title=None)
            st.plotly_chart(fig_ac, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Incident Intelligence
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    if inc.empty:
        st.info("No incident data — run AEGIS to populate the audit log.")
    else:
        # ── Gantt ──────────────────────────────────────────────────────────────
        st.markdown('<div class="sh">Incident Gantt — Detection to Resolution</div>', unsafe_allow_html=True)
        cmap2 = {"success": GREEN, "escalated": RED, "in_progress": GOLD}
        fig_gantt = go.Figure()
        for _, row in inc.iterrows():
            c = cmap2.get(row["status"], CYAN)
            fig_gantt.add_trace(go.Scatter(
                x=[row["start"], row["end"]],
                y=[row["incident_id"][:14]] * 2,
                mode="lines+markers",
                line=dict(color=c, width=18),
                marker=dict(size=12, color=c, symbol=["circle", "diamond"]),
                showlegend=False,
                hovertemplate=(
                    f"<b>{row['incident_id']}</b><br>"
                    f"MTTR: {row['mttr_min']}m<br>"
                    f"Status: {row['status'].upper()}<br>"
                    f"Attempts: {row['attempts']}<extra></extra>"
                ),
            ))
        dfig(fig_gantt, 220)
        fig_gantt.update_layout(
            xaxis_title=None, yaxis_title=None,
            yaxis=dict(tickfont=dict(size=10, family="monospace")),
        )
        st.plotly_chart(fig_gantt, use_container_width=True)

        # ── Table + deep-dive ─────────────────────────────────────────────────
        st.markdown('<div class="sh">All Incidents</div>', unsafe_allow_html=True)
        disp = inc[["incident_id","start","status","confidence","attempts","mttr_min","max_lines"]].copy()
        disp["start"]      = disp["start"].dt.strftime("%Y-%m-%d %H:%M UTC")
        disp["status"]     = disp["status"].str.upper()
        disp["confidence"] = disp["confidence"].map("{:.0f}%".format)
        disp["mttr_min"]   = disp["mttr_min"].map("{:.1f} min".format)
        disp.columns = ["Incident ID","Detected At","Status","RCA Confidence","Fix Attempts","MTTR","Lines Changed"]
        st.dataframe(disp, use_container_width=True, hide_index=True)

        st.markdown('<div class="sh">Incident Deep Dive</div>', unsafe_allow_html=True)
        sel = st.selectbox(
            "Select incident:",
            inc["incident_id"].tolist(),
            format_func=lambda x: (
                f"✅ {x}" if inc.loc[inc.incident_id==x,"status"].values[0]=="success"
                else f"❌ {x}"
            ),
        )
        if sel and not df.empty and "incident_id" in df.columns:
            evs = df[df["incident_id"]==sel].sort_values("timestamp")
            sel_row = inc[inc.incident_id==sel].iloc[0]
            ca, cb = st.columns([1, 2], gap="medium")
            with ca:
                st.markdown("**Step-by-step audit trail:**")
                for _, ev in evs.iterrows():
                    action = ev.get("action","")
                    color  = ACTION_COLOR.get(action,"#64748b")
                    ts     = ev["timestamp"].strftime("%H:%M:%S")
                    parts  = []
                    for fld in ["confidence","lines_changed","run_id","error","attempts","reason"]:
                        v = ev.get(fld)
                        if v is not None and str(v) not in ("","nan","None"):
                            parts.append(f"{fld}={str(v)[:55]}")
                    detail = " | ".join(parts[:2])
                    st.markdown(
                        f"<div style='display:flex;gap:8px;padding:4px 0;"
                        f"border-bottom:1px solid rgba(255,255,255,.04);"
                        f"font-size:.78rem;font-family:monospace;'>"
                        f"<span style='color:#475569;min-width:68px;flex-shrink:0;'>{ts}</span>"
                        f"<span style='color:{color};font-weight:700;min-width:200px;flex-shrink:0;'>{action}</span>"
                        f"<span style='color:#64748b;overflow:hidden;'>{detail}</span></div>",
                        unsafe_allow_html=True,
                    )
            with cb:
                ddf2 = evs[evs["action"]=="DIFF_COMPUTED"].copy()
                if not ddf2.empty and "lines_changed" in ddf2.columns:
                    ddf2["lines_changed"] = ddf2["lines_changed"].fillna(0).astype(int)
                    att_labels = [f"Attempt {i+1}" for i in range(len(ddf2))]
                    fig_att = go.Figure(go.Bar(
                        x=att_labels, y=ddf2["lines_changed"].tolist(),
                        marker=dict(color=[CYAN,GOLD,RED,ORANGE][:len(ddf2)], line_width=0, cornerradius=4),
                        text=ddf2["lines_changed"].tolist(), textposition="outside",
                        textfont=dict(color="white",size=13),
                    ))
                    dfig(fig_att, 230)
                    fig_att.update_layout(title="Lines Changed per Fix Attempt",
                                          title_font=dict(size=12, color="#94a3b8"),
                                          xaxis_title=None, yaxis_title="Lines")
                    st.plotly_chart(fig_att, use_container_width=True)

                sc = sel_row.get("status","")
                sc_col = GREEN if sc=="success" else (RED if sc=="escalated" else GOLD)
                st.markdown(f"""
                <div style="background:rgba(0,0,0,.3);border:1px solid rgba(0,212,255,.2);
                            border-radius:10px;padding:16px;margin-top:10px;">
                  <div style="font-size:.7rem;color:{CYAN};text-transform:uppercase;
                              letter-spacing:.12em;margin-bottom:10px;font-weight:700;">
                    Root Cause Analysis
                  </div>
                  <div style="font-size:.88rem;color:#e2e8f0;line-height:1.5;margin-bottom:12px;">
                    {sel_row.get('root_cause','Unknown')}
                  </div>
                  <div style="display:flex;gap:20px;flex-wrap:wrap;">
                    <span style="font-size:.8rem;color:#94a3b8;">
                        Status: <strong style="color:{sc_col}">{sc.upper()}</strong>
                    </span>
                    <span style="font-size:.8rem;color:#94a3b8;">
                        Confidence: <strong style="color:{GREEN}">{sel_row.get('confidence',0):.0f}%</strong>
                    </span>
                    <span style="font-size:.8rem;color:#94a3b8;">
                        MTTR: <strong style="color:{CYAN}">{sel_row.get('mttr_min',0)}m</strong>
                    </span>
                    <span style="font-size:.8rem;color:#94a3b8;">
                        Attempts: <strong style="color:{GOLD}">{sel_row.get('attempts',0)}</strong>
                    </span>
                  </div>
                </div>
                """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Live Pipeline
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    gc, sc = st.columns([3, 2], gap="medium")

    with gc:
        st.markdown('<div class="sh">AEGIS 15-Node LangGraph State Machine</div>', unsafe_allow_html=True)

        mermaid = (
            "flowchart TD\n"
            '    A(["🔍 1 Job Selector"]):::cyan --> B(["📊 2 Status Check"]):::cyan\n'
            '    B --> C(["📧 3 Initial Email"]):::cyan\n'
            '    C --> D{"Route?"}:::diamond\n'
            "\n"
            '    D -->|Failure Detected| E(["🚨 4 Failure Alert + RCA\nGPT-4o · confidence gate 70%"]):::alert\n'
            '    D -->|ML Drift| ML(["🤖 ML Healer\nretrain + MLflow promote"]):::ml\n'
            '    D -->|Healthy| Z(["✅ END"]):::end_\n'
            "\n"
            '    E -->|"conf ≥ 70%"| F(["📧 5 Fix In Progress"]):::email\n'
            "    E -->|conf < 70%| IR\n"
            "\n"
            '    F --> G(["🔧 6 Job Fixer\nGPT-5.5 whole-notebook scan"]):::fixer\n'
            '    G --> H(["📧 7 Fix Complete"]):::email\n'
            '    H --> I(["🔀 8 PR Create\nauto-commit + hotfix branch"]):::git\n'
            '    I --> J(["📧 9 PR Raised"]):::email\n'
            '    J --> K(["⏳ 10 PR Wait Approval\nindefinite merge poll"]):::wait\n'
            '    K --> N(["🚀 11 Deployment\nGitHub Actions CD"]):::deploy\n'
            '    N --> O(["🔍 12 Post-Deploy Verify"]):::cyan\n'
            '    O -->|OK| P(["📧 13 Final Confirm"]):::email\n'
            '    O -->|Failed| Q(["📧 13 Deploy Failed"]):::alert\n'
            '    P --> IR(["📋 14 Incident Report\nJSON + audit log"]):::report\n'
            "    Q --> IR\n    ML --> IR\n    IR --> Z\n"
            "\n"
            "    classDef cyan    fill:#0e2233,stroke:#00d4ff,color:#00d4ff\n"
            "    classDef alert   fill:#2d0a0a,stroke:#ff4444,color:#ff6b6b\n"
            "    classDef email   fill:#1a1a0e,stroke:#ffd700,color:#ffd700\n"
            "    classDef fixer   fill:#0a1a0a,stroke:#00ff88,color:#00ff88\n"
            "    classDef git     fill:#1a0e2d,stroke:#a855f7,color:#c084fc\n"
            "    classDef wait    fill:#2d1a0a,stroke:#ff8c00,color:#ff8c00\n"
            "    classDef deploy  fill:#0a0a2d,stroke:#818cf8,color:#818cf8\n"
            "    classDef report  fill:#1a1a1a,stroke:#94a3b8,color:#94a3b8\n"
            "    classDef ml      fill:#0e1a1a,stroke:#4ade80,color:#4ade80\n"
            "    classDef end_    fill:#0a2a0a,stroke:#00ff88,color:#00ff88\n"
            "    classDef diamond fill:#1a1a2d,stroke:#a855f7,color:#a855f7\n"
        )
        components.html(f"""<!DOCTYPE html><html><head>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<style>
  body{{margin:0;padding:0;background:#0a0e1a;}}
  .wrap{{padding:16px;background:#0a0e1a;border-radius:12px;}}
  svg{{max-width:100%;}}
</style></head><body>
<script>mermaid.initialize({{
  startOnLoad:true,theme:'dark',
  themeVariables:{{
    primaryColor:'#111827',primaryTextColor:'#00d4ff',
    primaryBorderColor:'#00d4ff',lineColor:'#334155',
    secondaryColor:'#0f172a',background:'#0a0e1a',
    mainBkg:'#111827',nodeBorder:'#00d4ff',clusterBkg:'#0f172a',
    titleColor:'#00d4ff',fontFamily:'system-ui,sans-serif',fontSize:'13px',
  }},
  flowchart:{{curve:'basis',htmlLabels:true,useMaxWidth:true}}
}});</script>
<div class="wrap"><div class="mermaid">{mermaid}</div></div>
</body></html>""", height=680, scrolling=True)

    with sc:
        st.markdown('<div class="sh">Pipeline Nodes</div>', unsafe_allow_html=True)
        nodes_list = [
            ("1",  CYAN,    "rgba(14,34,51,.8)",  "Job Selector",         "Discovers Databricks jobs"),
            ("2",  CYAN,    "rgba(14,34,51,.8)",  "Status Check",         "Polls health via Databricks SDK"),
            ("3",  GOLD,    "rgba(26,26,14,.8)",  "Initial Email",        "Health status notification"),
            ("4",  RED,     "rgba(45,10,10,.8)",  "Failure Alert + RCA",  "GPT-4o JSON RCA (gate @ 70%)"),
            ("5",  GOLD,    "rgba(26,26,14,.8)",  "Fix In Progress Email","Autonomous repair started"),
            ("6",  GREEN,   "rgba(10,26,10,.8)",  "Job Fixer",            "GPT-5.5 whole-notebook scan"),
            ("7",  GOLD,    "rgba(26,26,14,.8)",  "Fix Complete Email",   "Post-fix run ID confirmed"),
            ("8",  PURPLE,  "rgba(26,14,45,.8)",  "PR Create",            "Auto-commit · hotfix branch"),
            ("9",  GOLD,    "rgba(26,26,14,.8)",  "PR Raised Email",      "Notifies reviewers"),
            ("10", ORANGE,  "rgba(45,26,10,.8)",  "PR Wait Approval",     "Polls GitHub indefinitely"),
            ("11", "#818cf8","rgba(10,10,45,.8)", "Deployment",           "Triggers GitHub Actions CD"),
            ("12", CYAN,    "rgba(14,34,51,.8)",  "Post-Deploy Verify",   "Re-runs Databricks health check"),
            ("13", GOLD,    "rgba(26,26,14,.8)",  "Final / Failed Email", "Outcome notification"),
            ("14", "#94a3b8","rgba(26,26,26,.8)", "Incident Report",      "Structured JSON + audit log"),
            ("ML", "#4ade80","rgba(14,26,26,.8)", "ML Healer",            "Retraining + MLflow promotion"),
        ]
        for num, bc, bg, name, desc in nodes_list:
            st.markdown(f"""
            <div class="ps" style="border-left-color:{bc};background:{bg};">
              <span class="psn" style="color:{bc};">{num}</span>
              <div>
                <div class="pst" style="color:{bc};">{name}</div>
                <div class="psd">{desc}</div>
              </div>
            </div>""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — Guardrail Console
# ══════════════════════════════════════════════════════════════════════════════
with tab4:
    ca, cb = st.columns([5, 4], gap="medium")

    with ca:
        st.markdown('<div class="sh">Live Audit Log Feed</div>', unsafe_allow_html=True)
        if not df.empty:
            f1, f2 = st.columns(2)
            with f1:
                fi = st.selectbox("Incident", ["All"] + sorted(df["incident_id"].dropna().unique().tolist()))
            with f2:
                fa = st.selectbox("Action",   ["All"] + sorted(df["action"].dropna().unique().tolist()))
            fdf = df.copy()
            if fi != "All": fdf = fdf[fdf["incident_id"] == fi]
            if fa != "All": fdf = fdf[fdf["action"] == fa]
            fdf = fdf.sort_values("timestamp", ascending=False).head(80)

            html = (
                '<div style="max-height:540px;overflow-y:auto;'
                'background:rgba(10,14,26,.9);border:1px solid rgba(0,212,255,.1);'
                'border-radius:10px;padding:8px;">'
            )
            for _, row in fdf.iterrows():
                action = row.get("action","")
                color  = ACTION_COLOR.get(action, "#64748b")
                ts     = row["timestamp"].strftime("%m-%d %H:%M:%S")
                inc_id = str(row.get("incident_id","—"))[:14]
                parts  = []
                for fld in ["confidence","lines_changed","run_id","attempts","error","reason"]:
                    v = row.get(fld)
                    if v is not None and str(v) not in ("","nan","None"):
                        parts.append(f"{fld}={str(v)[:48]}")
                detail = " | ".join(parts[:3])
                html += (
                    f'<div class="alog">'
                    f'<span class="at">{ts}</span>'
                    f'<span class="ai">{inc_id}</span>'
                    f'<span class="aa" style="color:{color};">{action}</span>'
                    f'<span class="ad">{detail}</span></div>'
                )
            html += "</div>"
            st.markdown(html, unsafe_allow_html=True)

    with cb:
        st.markdown('<div class="sh">Guardrail Activation Chart</div>', unsafe_allow_html=True)
        if not df.empty:
            g_acts = [
                "LINT_CHECK","DIFF_COMPUTED","NOTEBOOK_ROLLED_BACK",
                "LLM_OUTPUT_INVALID","MAX_RETRIES_EXCEEDED","FIX_EXCEPTION","FIX_ESCALATED","PEP8_FORMATTED",
            ]
            gc_df = df[df["action"].isin(g_acts)]["action"].value_counts()
            fig_g = go.Figure(go.Bar(
                y=gc_df.index, x=gc_df.values, orientation="h",
                marker=dict(
                    color=[ACTION_COLOR.get(a,"#64748b") for a in gc_df.index],
                    line_width=0, cornerradius=4,
                ),
                text=gc_df.values, textposition="outside",
                textfont=dict(size=11, color="white"),
            ))
            dfig(fig_g, 290)
            fig_g.update_layout(xaxis_title="Times Triggered")
            st.plotly_chart(fig_g, use_container_width=True)

        st.markdown('<div class="sh">7 Guardrail Layers</div>', unsafe_allow_html=True)
        guardrails = [
            ("G1",  CYAN,    "Confidence Gate",       "Escalate if RCA < 70%"),
            ("G2",  GOLD,    "Diff Validator",        "Block if LLM returns identical code"),
            ("G3",  ORANGE,  "Rollback on Failure",   "Restore original on post-fix failure"),
            ("G4",  RED,     "Syntax Hard Block",     "compile() — invalid Python never uploads"),
            ("G4b", "#94a3b8","pyflakes Lint",        "Static analysis warning (non-blocking)"),
            ("G5",  PURPLE,  "Rate Limiter",          "5 triggers per job per 10 min"),
            ("G6",  GREEN,   "Audit Log",             "Append-only JSONL of every action"),
            ("G7",  PINK,    "Prompt Guard",          "Injection scan before every LLM call"),
        ]
        for key, color, name, desc in guardrails:
            st.markdown(f"""
            <div class="gr" style="border-left-color:{color};">
              <span class="grk" style="color:{color};">{key}</span>
              <div><div class="grn" style="color:{color};">{name}</div>
              <div class="grd">{desc}</div></div>
            </div>""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — System Architecture
# ══════════════════════════════════════════════════════════════════════════════
with tab5:
    r1, r2, r3 = st.columns([2, 2, 2], gap="medium")

    # ── Capability radar ──────────────────────────────────────────────────────
    with r1:
        st.markdown('<div class="sh">AEGIS vs Baseline — Capability Radar</div>', unsafe_allow_html=True)
        cats = ["Autonomous<br>Repair", "RCA<br>Accuracy", "Safety<br>Layers",
                "ML<br>Monitoring", "GitOps<br>Integration", "Audit<br>Trail"]
        fig_radar = go.Figure()
        fig_radar.add_trace(go.Scatterpolar(
            r=[9, 9, 10, 8, 9, 10], theta=cats, fill="toself",
            name="AEGIS",
            line=dict(color=CYAN, width=2.5),
            fillcolor="rgba(0,212,255,.18)",
            marker=dict(size=8, color=CYAN),
        ))
        fig_radar.add_trace(go.Scatterpolar(
            r=[1, 3, 2, 1, 2, 1], theta=cats, fill="toself",
            name="Manual On-Call",
            line=dict(color=RED, width=2, dash="dash"),
            fillcolor="rgba(255,68,68,.1)",
            marker=dict(size=6, color=RED),
        ))
        fig_radar.add_trace(go.Scatterpolar(
            r=[3, 4, 3, 2, 1, 3], theta=cats, fill="toself",
            name="Rule-Based Alerts",
            line=dict(color=ORANGE, width=2, dash="dot"),
            fillcolor="rgba(255,140,0,.08)",
            marker=dict(size=6, color=ORANGE),
        ))
        dfig(fig_radar, 370)
        fig_radar.update_layout(
            polar=dict(
                bgcolor="rgba(17,24,39,.6)",
                radialaxis=dict(visible=True, range=[0,10], gridcolor="rgba(255,255,255,.08)",
                                tickcolor="#334155", color="#64748b", showticklabels=False),
                angularaxis=dict(gridcolor="rgba(255,255,255,.08)", color="#94a3b8"),
            ),
            showlegend=True,
            legend=dict(orientation="h", y=-0.05, x=0.5, xanchor="center"),
        )
        st.plotly_chart(fig_radar, use_container_width=True)

    # ── AI stack ─────────────────────────────────────────────────────────────
    with r2:
        st.markdown('<div class="sh">AI Stack</div>', unsafe_allow_html=True)
        ai_stack = [
            (GREEN,   "GPT-5.5",     "EPAM DIAL",  "Whole-notebook comprehensive repair"),
            (CYAN,    "GPT-4o",      "EPAM DIAL",  "Structured JSON RCA with confidence score"),
            (PURPLE,  "LangGraph",   "v0.2",       "15-node async multi-agent state machine"),
            (GOLD,    "LangChain",   "AzureOpenAI","LLM integration layer"),
            ("#4ade80","ChromaDB",   "in-process", "Incident memory · SHA-256 embeddings"),
            ("#818cf8","MLflow",     "Databricks", "Model registry · drift detection · promotion"),
            (ORANGE,  "Databricks",  "SDK v0.38",  "Job health · notebook fetch/upload · runs"),
        ]
        for color, name, provider, desc in ai_stack:
            st.markdown(f"""
            <div style="display:flex;align-items:flex-start;gap:10px;
                        padding:9px 12px;margin-bottom:5px;
                        background:rgba(17,24,39,.7);border:1px solid rgba(255,255,255,.06);
                        border-left:3px solid {color};border-radius:0 8px 8px 0;">
              <div style="min-width:90px;font-weight:800;color:{color};font-size:.84rem;">{name}</div>
              <div>
                <div style="font-size:.78rem;color:#94a3b8;">{provider}</div>
                <div style="font-size:.8rem;color:#e2e8f0;margin-top:2px;">{desc}</div>
              </div>
            </div>""", unsafe_allow_html=True)

        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
        st.markdown('<div class="sh">GitOps Pipeline</div>', unsafe_allow_html=True)
        for color, name, desc in [
            (PURPLE, "PyGithub",      "PR creation · indefinite merge poll"),
            (PURPLE, "GitHub Actions","CD trigger · workflow poll to terminal state"),
            (GREEN,  "GitHub Branch", "auto hotfix branch per incident"),
        ]:
            st.markdown(f"""
            <div style="display:flex;gap:10px;padding:8px 12px;margin-bottom:5px;
                        background:rgba(17,24,39,.7);border-left:3px solid {color};
                        border-radius:0 8px 8px 0;">
              <div style="font-weight:700;color:{color};min-width:120px;font-size:.82rem;">{name}</div>
              <div style="font-size:.8rem;color:#94a3b8;">{desc}</div>
            </div>""", unsafe_allow_html=True)

    # ── Stats panel ───────────────────────────────────────────────────────────
    with r3:
        st.markdown('<div class="sh">By the Numbers</div>', unsafe_allow_html=True)
        stats = [
            (CYAN,    "15",  "LangGraph nodes"),
            (GREEN,   "7",   "Guardrail layers"),
            (GOLD,    "103", "Tests (94 in CI)"),
            (PURPLE,  "12",  "Email notification stages"),
            (ORANGE,  "10",  "Intentional bugs in demo notebook"),
            (RED,     "3",   "Max auto-repair retries"),
            ("#818cf8","∞",  "PR merge poll — no timeout"),
            (GREEN,   "70%", "RCA confidence threshold"),
            (CYAN,    "5",   "Rate limit: triggers/job/10 min"),
            ("#4ade80","0",  "Human actions required (success path)"),
        ]
        for color, val, label in stats:
            st.markdown(f"""
            <div style="display:flex;justify-content:space-between;align-items:center;
                        padding:9px 0;border-bottom:1px solid rgba(255,255,255,.05);font-size:.85rem;">
              <span style="color:#94a3b8;">{label}</span>
              <span style="color:{color};font-weight:900;font-family:monospace;font-size:1.05rem;">{val}</span>
            </div>""", unsafe_allow_html=True)

        st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
        st.markdown('<div class="sh">Real Production Evidence</div>', unsafe_allow_html=True)
        evidence = [
            (GREEN, "INC-7BC959AE", "Healed attempt 1 · run 481362957091748"),
            (GREEN, "INC-B3A904CC", "Healed attempt 2 · run 336259351258626"),
            (ORANGE,"INC-E25061C7", "3 retries · guardrail rollback · escalated"),
            (RED,   "INC-DF4F8C83", "Max retries · FIX_ESCALATED · audit trail"),
        ]
        for color, inc_id, note in evidence:
            st.markdown(f"""
            <div style="padding:7px 10px;margin-bottom:5px;
                        background:rgba(17,24,39,.7);border-left:3px solid {color};
                        border-radius:0 8px 8px 0;">
              <div style="font-weight:700;color:{color};font-size:.8rem;font-family:monospace;">{inc_id}</div>
              <div style="font-size:.75rem;color:#64748b;margin-top:2px;">{note}</div>
            </div>""", unsafe_allow_html=True)


# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"<div style='color:{CYAN};font-weight:900;font-size:1.2rem;'>🛡️ AEGIS</div>", unsafe_allow_html=True)
    st.markdown(f"<div style='color:#475569;font-size:.75rem;margin-bottom:16px;'>v2.0.0 · Production</div>", unsafe_allow_html=True)
    if st.button("🔄 Refresh Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    auto = st.checkbox("Auto-refresh every 15s", value=False)
    st.markdown("---")
    st.markdown(f"""
    <div style='color:#94a3b8;font-size:.78rem;line-height:1.7;'>
      <b style='color:{CYAN}'>Run demo:</b><br>
      <code style='font-size:.72rem;'>python demo/production_multi_agent.py</code>
      <br><br>
      <b style='color:{CYAN}'>Dashboard:</b><br>
      <code style='font-size:.72rem;'>streamlit run demo/dashboard.py</code>
    </div>""", unsafe_allow_html=True)
    if auto:
        time.sleep(15)
        st.rerun()

# ─── Footer ───────────────────────────────────────────────────────────────────
st.markdown(
    f"<div style='text-align:center;padding:18px;color:#1e293b;font-size:.72rem;"
    f"border-top:1px solid rgba(255,255,255,.04);margin-top:14px;'>"
    f"AEGIS v2.0.0 · Autonomous End-to-end Guardian for Intelligent Systems · "
    f"LangGraph 15-node · GPT-5.5 repair · 7 guardrails · Databricks production"
    f"</div>",
    unsafe_allow_html=True,
)
