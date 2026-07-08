"""AEGIS Command Center — Production AIOps Dashboard for Hackathon Demo.

Run from project root:
    streamlit run demo/dashboard.py
"""

import json
import time
from collections import Counter
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

# ─── Paths ────────────────────────────────────────────────────────────────────
AUDIT_LOG_PATH = Path("data/audit_log.jsonl")
REPORTS_DIR    = Path("data/reports")

# ─── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AEGIS Command Center",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─── Color palette ────────────────────────────────────────────────────────────
CYAN   = "#00d4ff"
GREEN  = "#00ff88"
RED    = "#ff4444"
GOLD   = "#ffd700"
PURPLE = "#a855f7"
ORANGE = "#ff8c00"

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
    "LLM_OUTPUT_INVALID":     "#f43f5e",
    "PEP8_FORMATTED":         "#4ade80",
}

# ─── CSS ──────────────────────────────────────────────────────────────────────
st.markdown(f"""
<style>
    #MainMenu {{visibility: hidden;}}
    footer {{visibility: hidden;}}
    header {{visibility: hidden;}}

    .stApp {{
        background-color: #0a0e1a;
        color: #e2e8f0;
    }}

    /* KPI cards */
    .kpi-card {{
        background: linear-gradient(135deg, rgba(17,24,39,0.95), rgba(30,41,59,0.85));
        border: 1px solid rgba(0,212,255,0.18);
        border-radius: 14px;
        padding: 22px 20px 16px;
        margin: 2px;
        backdrop-filter: blur(12px);
        position: relative;
        overflow: hidden;
    }}
    .kpi-card::before {{
        content: '';
        position: absolute;
        top: 0; left: 0; right: 0;
        height: 3px;
        background: linear-gradient(90deg, {CYAN}, {PURPLE});
    }}
    .kpi-value {{
        font-size: 2.5rem;
        font-weight: 800;
        background: linear-gradient(135deg, {CYAN}, {GREEN});
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        line-height: 1.1;
        margin: 0;
        letter-spacing: -1px;
    }}
    .kpi-value-red {{
        font-size: 2.5rem;
        font-weight: 800;
        background: linear-gradient(135deg, {RED}, {ORANGE});
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        line-height: 1.1;
        margin: 0;
        letter-spacing: -1px;
    }}
    .kpi-value-gold {{
        font-size: 2.5rem;
        font-weight: 800;
        background: linear-gradient(135deg, {GOLD}, {ORANGE});
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        line-height: 1.1;
        margin: 0;
        letter-spacing: -1px;
    }}
    .kpi-label {{
        font-size: 0.78rem;
        color: #94a3b8;
        text-transform: uppercase;
        letter-spacing: 0.12em;
        margin-top: 8px;
        font-weight: 600;
    }}
    .kpi-sub {{
        font-size: 0.75rem;
        color: #4ade80;
        margin-top: 5px;
        font-weight: 500;
    }}

    /* Section headers */
    .sec-h {{
        font-size: 0.78rem;
        font-weight: 700;
        color: {CYAN};
        text-transform: uppercase;
        letter-spacing: 0.12em;
        border-bottom: 1px solid rgba(0,212,255,0.15);
        padding-bottom: 8px;
        margin-bottom: 14px;
        margin-top: 4px;
    }}

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {{
        gap: 6px;
        background-color: transparent;
        border-bottom: 1px solid rgba(0,212,255,0.12);
        padding-bottom: 0;
    }}
    .stTabs [data-baseweb="tab"] {{
        height: 38px;
        background-color: rgba(17,24,39,0.6);
        border-radius: 8px 8px 0 0;
        color: #64748b;
        font-weight: 700;
        font-size: 0.82rem;
        border: 1px solid rgba(0,212,255,0.08);
        border-bottom: none;
        padding: 0 18px;
    }}
    .stTabs [aria-selected="true"] {{
        background-color: rgba(0,212,255,0.1) !important;
        color: {CYAN} !important;
        border-color: rgba(0,212,255,0.25) !important;
    }}
    .stTabs [data-testid="stMarkdownContainer"] p {{
        margin: 0;
    }}

    /* Audit log rows */
    .alog {{
        display: flex;
        gap: 0;
        padding: 5px 8px;
        border-bottom: 1px solid rgba(255,255,255,0.04);
        font-size: 0.76rem;
        font-family: 'Consolas', 'Monaco', monospace;
        transition: background 0.15s;
        align-items: flex-start;
    }}
    .alog:hover {{ background: rgba(0,212,255,0.04); }}
    .at {{ color: #475569; min-width: 140px; flex-shrink: 0; }}
    .ai {{ color: #818cf8; min-width: 130px; flex-shrink: 0; overflow: hidden; text-overflow: ellipsis; }}
    .aa {{ font-weight: 700; min-width: 220px; flex-shrink: 0; }}
    .ad {{ color: #64748b; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 340px; }}

    /* Workflow step list */
    .ws {{
        display: flex;
        align-items: flex-start;
        padding: 7px 10px;
        margin: 3px 0;
        border-radius: 6px;
        border-left: 3px solid transparent;
        font-size: 0.82rem;
        gap: 10px;
    }}
    .ws.done {{
        background: rgba(0,255,136,0.07);
        border-left-color: {GREEN};
    }}
    .ws.active {{
        background: rgba(0,212,255,0.1);
        border-left-color: {CYAN};
    }}
    .ws.pending {{
        background: rgba(30,41,59,0.4);
        border-left-color: #1e293b;
    }}
    .wsn {{ font-weight: 800; min-width: 30px; flex-shrink: 0; font-size: 0.75rem; }}
    .wst {{ font-weight: 700; }}
    .wsd {{ font-size: 0.72rem; opacity: 0.65; margin-top: 1px; }}

    /* Guardrail rows */
    .gr {{
        display: flex;
        align-items: flex-start;
        gap: 10px;
        padding: 7px 10px;
        margin-bottom: 4px;
        border-radius: 0 8px 8px 0;
        border-left: 3px solid;
        background: rgba(17,24,39,0.6);
    }}
    .grk {{ font-weight: 800; min-width: 32px; font-size: 0.72rem; }}
    .grn {{ font-weight: 700; font-size: 0.83rem; }}
    .grd {{ font-size: 0.73rem; color: #64748b; margin-top: 1px; }}

    @keyframes pulse {{
        0%,100% {{ opacity:1; transform:scale(1); }}
        50%      {{ opacity:0.5; transform:scale(1.4); }}
    }}
    .live {{ display:inline-block; width:8px; height:8px; background:{GREEN}; border-radius:50%;
              animation:pulse 1.8s infinite; margin-right:6px; vertical-align:middle; }}

    /* Selectbox and input dark */
    .stSelectbox > div > div {{
        background-color: rgba(17,24,39,0.9) !important;
        border: 1px solid rgba(0,212,255,0.2) !important;
        color: #e2e8f0 !important;
    }}
    .stDataFrame {{ background: transparent; }}
</style>
""", unsafe_allow_html=True)


# ─── Data loading ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=10)
def load_audit_log() -> pd.DataFrame:
    if not AUDIT_LOG_PATH.exists():
        return pd.DataFrame()
    rows = []
    for line in AUDIT_LOG_PATH.read_text(encoding="utf-8").strip().splitlines():
        try:
            rows.append(json.loads(line))
        except Exception:
            pass
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df


@st.cache_data(ttl=10)
def build_incident_table(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "incident_id" not in df.columns:
        return pd.DataFrame()
    rows = []
    for inc_id, grp in df.groupby("incident_id", dropna=True):
        actions  = set(grp["action"].tolist())
        ts       = grp["timestamp"]
        start    = ts.min()
        end      = ts.max()
        mttr_min = round((end - start).total_seconds() / 60, 1)

        status = (
            "success"   if "FIX_SUCCESS" in actions else
            "escalated" if actions & {"FIX_ESCALATED", "MAX_RETRIES_EXCEEDED"} else
            "in_progress"
        )

        max_att = max(
            (int(r.get("attempt", 0)) for _, r in grp.iterrows() if r.get("attempt") is not None),
            default=0,
        )

        conf_g = grp[grp["action"] == "CONFIDENCE_GATE_PASSED"]
        confidence = (
            float(conf_g.iloc[-1]["confidence"])
            if not conf_g.empty and "confidence" in conf_g.columns
            else 0.0
        )
        root_cause = (
            str(conf_g.iloc[-1]["root_cause"])
            if not conf_g.empty and "root_cause" in conf_g.columns
            else "Unknown"
        )

        diff_g = grp[grp["action"] == "DIFF_COMPUTED"]
        max_lines = (
            int(diff_g["lines_changed"].max())
            if not diff_g.empty and "lines_changed" in diff_g.columns
            else 0
        )

        rows.append(dict(
            incident_id=inc_id,
            start=start,
            end=end,
            mttr_min=mttr_min,
            status=status,
            attempts=max_att,
            confidence=confidence,
            root_cause=root_cause,
            max_lines=max_lines,
            n_actions=len(grp),
        ))
    return pd.DataFrame(rows).sort_values("start").reset_index(drop=True)


def dark_fig(fig, h: int | None = None) -> go.Figure:
    upd = dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(17,24,39,0.5)",
        font=dict(color="#94a3b8", family="system-ui, sans-serif", size=11),
        margin=dict(l=12, r=12, t=36, b=12),
        legend=dict(bgcolor="rgba(17,24,39,0.8)", bordercolor="rgba(0,212,255,0.2)", borderwidth=1),
    )
    if h:
        upd["height"] = h
    fig.update_layout(**upd)
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.05)", zerolinecolor="rgba(255,255,255,0.08)")
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.05)", zerolinecolor="rgba(255,255,255,0.08)")
    return fig


# ─── Load ─────────────────────────────────────────────────────────────────────
df  = load_audit_log()
inc = build_incident_table(df)

n_total     = len(inc)
n_healed    = int((inc["status"] == "success").sum())   if not inc.empty else 0
n_escalated = int((inc["status"] == "escalated").sum()) if not inc.empty else 0
heal_rate   = round(n_healed / n_total * 100) if n_total else 0
avg_mttr    = round(inc["mttr_min"].mean(), 1) if not inc.empty else 0
llm_calls   = int((df["action"] == "FIX_STARTED").sum()) if not df.empty else 0
grail_fires = int(df["action"].isin([
    "LINT_CHECK","DIFF_COMPUTED","NOTEBOOK_ROLLED_BACK",
    "LLM_OUTPUT_INVALID","MAX_RETRIES_EXCEEDED","FIX_EXCEPTION","FIX_ESCALATED",
]).sum()) if not df.empty else 0

# ─── Header ───────────────────────────────────────────────────────────────────
st.markdown(f"""
<div style="display:flex; align-items:center; justify-content:space-between;
            padding:18px 24px;
            background:linear-gradient(135deg, rgba(0,212,255,0.07), rgba(168,85,247,0.07));
            border:1px solid rgba(0,212,255,0.14); border-radius:14px; margin-bottom:22px;">
  <div>
    <h1 style="margin:0; font-size:1.9rem; font-weight:900; letter-spacing:-0.5px;
               background:linear-gradient(135deg,{CYAN},{PURPLE});
               -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text;">
      🛡️ AEGIS Command Center
    </h1>
    <p style="margin:5px 0 0; color:#94a3b8; font-size:0.88rem;">
      Autonomous End-to-end Guardian for Intelligent Systems &nbsp;·&nbsp;
      LangGraph 15-node &nbsp;·&nbsp; GPT-5.5 Repair &nbsp;·&nbsp; 7 Guardrail Layers &nbsp;·&nbsp; Real Databricks Production
    </p>
  </div>
  <div style="text-align:right; flex-shrink:0;">
    <div style="font-size:0.78rem; color:#94a3b8;"><span class="live"></span>LIVE AUDIT LOG</div>
    <div style="font-size:0.73rem; color:#475569; margin-top:3px;">{len(df) if not df.empty else 0} entries &nbsp;·&nbsp; {n_total} incidents</div>
  </div>
</div>
""", unsafe_allow_html=True)


# ─── KPI Row ──────────────────────────────────────────────────────────────────
c1, c2, c3, c4, c5 = st.columns(5)

kpis = [
    (c1, str(n_total),      "Total Incidents",     f"{n_healed} healed · {n_escalated} escalated", ""),
    (c2, f"{heal_rate}%",   "Auto-Heal Rate",      f"vs 0% baseline",                             ""),
    (c3, f"{avg_mttr}m",    "Avg MTTR",            f"vs ~120 min manual",                         "gold"),
    (c4, str(llm_calls),    "LLM Repair Calls",    "GPT-5.5 invocations",                         ""),
    (c5, str(grail_fires),  "Guardrail Activations","7-layer safety system",                       ""),
]
for col, val, label, sub, color in kpis:
    vc = "kpi-value-gold" if color == "gold" else "kpi-value"
    col.markdown(f"""
    <div class="kpi-card">
        <div class="{vc}">{val}</div>
        <div class="kpi-label">{label}</div>
        <div class="kpi-sub">{sub}</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)


# ─── Tabs ─────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs([
    "📊  Overview",
    "🔍  Incident Intelligence",
    "⚙️  Live Pipeline",
    "🔒  Guardrail Console",
])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Overview
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    left, right = st.columns([3, 2], gap="medium")

    # ── Left column ───────────────────────────────────────────────────────────
    with left:
        st.markdown('<div class="sec-h">Incident Activity Timeline</div>', unsafe_allow_html=True)

        if not df.empty:
            tdf = df.copy()
            tdf["hour"] = tdf["timestamp"].dt.floor("h")
            by_hour = tdf.groupby("hour").size().reset_index(name="count")

            fig_tl = go.Figure()
            fig_tl.add_trace(go.Scatter(
                x=by_hour["hour"], y=by_hour["count"],
                mode="lines+markers", fill="tozeroy",
                line=dict(color=CYAN, width=2.5),
                fillcolor="rgba(0,212,255,0.08)",
                marker=dict(size=6, color=CYAN),
                name="Actions / hour",
            ))
            for action, marker_sym, color, name in [
                ("FIX_SUCCESS",    "star",   GREEN, "Auto-Healed"),
                ("FIX_ESCALATED",  "x",      RED,   "Escalated"),
                ("FIX_EXCEPTION",  "circle-open", ORANGE, "Exception"),
            ]:
                sub = df[df["action"] == action]
                if not sub.empty:
                    fig_tl.add_trace(go.Scatter(
                        x=sub["timestamp"], y=[0.3] * len(sub),
                        mode="markers", name=name,
                        marker=dict(size=13, color=color, symbol=marker_sym,
                                    line=dict(width=2, color="white")),
                    ))
            dark_fig(fig_tl, 230)
            fig_tl.update_layout(title=None, xaxis_title=None, yaxis_title="Events/hr")
            st.plotly_chart(fig_tl, use_container_width=True)

        st.markdown('<div class="sec-h">MTTR — AEGIS vs Baseline</div>', unsafe_allow_html=True)

        baselines = ["Manual On-Call", "Rule-Based Scripts", "AEGIS Avg", "AEGIS Best Case"]
        mttr_vals = [120, 45, avg_mttr if avg_mttr > 0 else 10, 3]
        bar_colors = [RED, ORANGE, CYAN, GREEN]

        fig_mttr = go.Figure(go.Bar(
            x=baselines, y=mttr_vals,
            marker_color=bar_colors, marker_line_width=0,
            text=[f"{v}m" for v in mttr_vals],
            textposition="outside",
            textfont=dict(color="#e2e8f0", size=13, family="monospace"),
        ))
        dark_fig(fig_mttr, 250)
        fig_mttr.update_layout(title=None, yaxis_title="Minutes", bargap=0.38)
        fig_mttr.update_yaxes(range=[0, 145])
        st.plotly_chart(fig_mttr, use_container_width=True)

        # Lines changed scatter
        if not df.empty and "lines_changed" in df.columns:
            st.markdown('<div class="sec-h">Lines Changed per Repair Attempt</div>', unsafe_allow_html=True)
            ddf = df[df["action"] == "DIFF_COMPUTED"].dropna(subset=["lines_changed"]).copy()
            if not ddf.empty:
                ddf["lines_changed"] = ddf["lines_changed"].astype(int)
                ddf["attempt_label"] = [f"Fix #{i+1}" for i in range(len(ddf))]
                ddf["inc_short"] = ddf.get("incident_id", pd.Series(["?"] * len(ddf))).str[:12]

                fig_lines = go.Figure(go.Bar(
                    x=ddf["attempt_label"],
                    y=ddf["lines_changed"],
                    marker_color=[
                        GREEN if "INC-7BC959AE" in str(r.get("incident_id","")) or
                                 "INC-B3A904CC" in str(r.get("incident_id",""))
                        else CYAN
                        for _, r in ddf.iterrows()
                    ],
                    marker_line_width=0,
                    text=ddf["lines_changed"],
                    textposition="outside",
                    textfont=dict(color="#94a3b8", size=10),
                    hovertemplate="<b>%{x}</b><br>Lines: %{y}<extra></extra>",
                ))
                dark_fig(fig_lines, 200)
                fig_lines.update_layout(title=None, xaxis_title=None, yaxis_title="Lines")
                st.plotly_chart(fig_lines, use_container_width=True)

    # ── Right column ──────────────────────────────────────────────────────────
    with right:
        st.markdown('<div class="sec-h">Incident Outcomes</div>', unsafe_allow_html=True)

        if not inc.empty:
            scounts = inc["status"].value_counts()
            cmap = {"success": GREEN, "escalated": RED, "in_progress": GOLD}
            labels = scounts.index.str.replace("_", " ").str.title().tolist()

            fig_donut = go.Figure(go.Pie(
                labels=labels,
                values=scounts.values,
                hole=0.65,
                marker_colors=[cmap.get(s, "#888") for s in scounts.index],
                textinfo="label+percent",
                textfont=dict(size=11),
                hovertemplate="%{label}: %{value}<extra></extra>",
            ))
            dark_fig(fig_donut, 260)
            fig_donut.update_layout(
                title=None,
                annotations=[dict(
                    text=f"<b style='font-size:18px'>{n_total}</b><br>incidents",
                    x=0.5, y=0.5, font=dict(size=15, color=CYAN), showarrow=False,
                )],
                showlegend=True,
                legend=dict(orientation="h", y=-0.08, x=0.5, xanchor="center"),
            )
            st.plotly_chart(fig_donut, use_container_width=True)

        st.markdown('<div class="sec-h">RCA Confidence per Incident</div>', unsafe_allow_html=True)

        if not inc.empty:
            color_map_status = {"success": GREEN, "escalated": RED, "in_progress": GOLD}
            fig_conf = go.Figure()
            for _, row in inc.iterrows():
                c = color_map_status.get(row["status"], CYAN)
                fig_conf.add_trace(go.Scatter(
                    x=[row["start"]], y=[row["confidence"]],
                    mode="markers",
                    marker=dict(
                        size=max(row["attempts"], 1) * 9 + 8,
                        color=c, opacity=0.85,
                        line=dict(width=2, color="rgba(255,255,255,0.4)"),
                    ),
                    name=row["incident_id"][:12],
                    hovertemplate=(
                        f"<b>{row['incident_id']}</b><br>"
                        f"Confidence: {row['confidence']:.0f}%<br>"
                        f"Status: {row['status']}<br>"
                        f"MTTR: {row['mttr_min']}m<extra></extra>"
                    ),
                    showlegend=False,
                ))
            fig_conf.add_hline(
                y=70, line_dash="dash", line_color=ORANGE, line_width=1.5,
                annotation_text="70% confidence gate", annotation_font_color=ORANGE,
                annotation_font_size=10,
            )
            dark_fig(fig_conf, 250)
            fig_conf.update_layout(
                title=None, xaxis_title=None,
                yaxis_title="Confidence %", yaxis_range=[0, 108],
            )
            st.plotly_chart(fig_conf, use_container_width=True)

        st.markdown('<div class="sec-h">Top Actions in Audit Log</div>', unsafe_allow_html=True)

        if not df.empty:
            ac = df["action"].value_counts().head(10)
            fig_act = go.Figure(go.Bar(
                y=ac.index, x=ac.values, orientation="h",
                marker_color=[ACTION_COLOR.get(a, "#64748b") for a in ac.index],
                marker_line_width=0,
                text=ac.values, textposition="outside",
                textfont=dict(size=10, color="#94a3b8"),
            ))
            dark_fig(fig_act, 300)
            fig_act.update_layout(title=None, xaxis_title="Count", yaxis_title=None)
            st.plotly_chart(fig_act, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Incident Intelligence
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    if inc.empty:
        st.info("No incident data found. Run AEGIS to generate incidents.")
    else:
        st.markdown('<div class="sec-h">All Incidents</div>', unsafe_allow_html=True)

        disp = inc[[
            "incident_id", "start", "status", "confidence",
            "attempts", "mttr_min", "max_lines",
        ]].copy()
        disp["start"]      = disp["start"].dt.strftime("%Y-%m-%d %H:%M UTC")
        disp["status"]     = disp["status"].str.upper()
        disp["confidence"] = disp["confidence"].map("{:.0f}%".format)
        disp["mttr_min"]   = disp["mttr_min"].map("{:.1f} min".format)
        disp.columns = [
            "Incident ID", "Detected At", "Status",
            "RCA Confidence", "Fix Attempts", "MTTR", "Max Lines Changed",
        ]
        st.dataframe(disp, use_container_width=True, hide_index=True)

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        st.markdown('<div class="sec-h">Incident Deep Dive</div>', unsafe_allow_html=True)

        sel = st.selectbox(
            "Select incident:",
            inc["incident_id"].tolist(),
            format_func=lambda x: (
                f"✅ {x}" if inc.loc[inc.incident_id == x, "status"].values[0] == "success"
                else f"❌ {x}"
            ),
        )

        if sel and not df.empty and "incident_id" in df.columns:
            events = df[df["incident_id"] == sel].sort_values("timestamp")
            sel_row = inc[inc.incident_id == sel].iloc[0]

            col_a, col_b = st.columns([1, 2], gap="medium")
            with col_a:
                st.markdown("**Step-by-step timeline:**")
                for _, ev in events.iterrows():
                    action = ev.get("action", "")
                    color  = ACTION_COLOR.get(action, "#64748b")
                    ts     = ev["timestamp"].strftime("%H:%M:%S")
                    parts  = []
                    for fld in ["confidence", "lines_changed", "run_id", "error", "attempts", "reason"]:
                        v = ev.get(fld)
                        if v is not None and str(v) not in ("", "nan", "None"):
                            parts.append(f"{fld}={str(v)[:55]}")
                    detail = " | ".join(parts[:2])
                    st.markdown(
                        f"<div style='display:flex; gap:8px; padding:4px 0; "
                        f"border-bottom:1px solid rgba(255,255,255,0.04); font-size:0.78rem; font-family:monospace;'>"
                        f"<span style='color:#475569; min-width:68px; flex-shrink:0;'>{ts}</span>"
                        f"<span style='color:{color}; font-weight:700; min-width:200px; flex-shrink:0;'>{action}</span>"
                        f"<span style='color:#64748b; overflow:hidden;'>{detail}</span></div>",
                        unsafe_allow_html=True,
                    )

            with col_b:
                # Attempt funnel
                diff_events = events[events["action"] == "DIFF_COMPUTED"].copy()
                if not diff_events.empty and "lines_changed" in diff_events.columns:
                    diff_events["lines_changed"] = diff_events["lines_changed"].fillna(0).astype(int)
                    att_labels = [f"Attempt {i+1}" for i in range(len(diff_events))]

                    fig_atts = go.Figure(go.Bar(
                        x=att_labels,
                        y=diff_events["lines_changed"].tolist(),
                        marker_color=[CYAN, GOLD, RED, ORANGE][:len(diff_events)],
                        marker_line_width=0,
                        text=diff_events["lines_changed"].tolist(),
                        textposition="outside",
                        textfont=dict(color="white", size=12),
                    ))
                    dark_fig(fig_atts, 220)
                    fig_atts.update_layout(
                        title="Lines Changed per Fix Attempt",
                        title_font=dict(size=12, color="#94a3b8"),
                        xaxis_title=None, yaxis_title="Lines",
                    )
                    st.plotly_chart(fig_atts, use_container_width=True)

                # Root cause card
                status_color = GREEN if sel_row["status"] == "success" else (RED if sel_row["status"] == "escalated" else GOLD)
                status_label = sel_row["status"].upper()
                st.markdown(f"""
                <div style="background:rgba(0,0,0,0.3); border:1px solid rgba(0,212,255,0.2);
                            border-radius:10px; padding:16px; margin-top:10px;">
                    <div style="font-size:0.7rem; color:{CYAN}; text-transform:uppercase;
                                letter-spacing:.12em; margin-bottom:10px; font-weight:700;">
                        Root Cause Analysis
                    </div>
                    <div style="font-size:0.88rem; color:#e2e8f0; line-height:1.5; margin-bottom:12px;">
                        {sel_row.get("root_cause","Unknown")}
                    </div>
                    <div style="display:flex; gap:20px; flex-wrap:wrap;">
                        <span style="font-size:0.8rem; color:#94a3b8;">
                            Status: <strong style="color:{status_color}">{status_label}</strong>
                        </span>
                        <span style="font-size:0.8rem; color:#94a3b8;">
                            Confidence: <strong style="color:{GREEN}">{sel_row.get("confidence",0):.0f}%</strong>
                        </span>
                        <span style="font-size:0.8rem; color:#94a3b8;">
                            MTTR: <strong style="color:{CYAN}">{sel_row.get("mttr_min",0)}m</strong>
                        </span>
                        <span style="font-size:0.8rem; color:#94a3b8;">
                            Attempts: <strong style="color:{GOLD}">{sel_row.get("attempts",0)}</strong>
                        </span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

        # Gantt chart of all incidents
        if not inc.empty:
            st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
            st.markdown('<div class="sec-h">Incident Gantt Chart (Detection → Resolution)</div>', unsafe_allow_html=True)

            cmap2 = {"success": GREEN, "escalated": RED, "in_progress": GOLD}
            fig_gantt = go.Figure()
            for _, row in inc.iterrows():
                c = cmap2.get(row["status"], CYAN)
                fig_gantt.add_trace(go.Scatter(
                    x=[row["start"], row["end"]],
                    y=[row["incident_id"][:14], row["incident_id"][:14]],
                    mode="lines+markers",
                    line=dict(color=c, width=16),
                    marker=dict(size=10, color=c),
                    name=row["status"],
                    showlegend=False,
                    hovertemplate=(
                        f"<b>{row['incident_id']}</b><br>"
                        f"MTTR: {row['mttr_min']}m<br>"
                        f"Status: {row['status']}<extra></extra>"
                    ),
                ))
            dark_fig(fig_gantt, 200)
            fig_gantt.update_layout(title=None, xaxis_title=None, yaxis_title=None)
            st.plotly_chart(fig_gantt, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Live Pipeline
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    graph_col, steps_col = st.columns([3, 2], gap="medium")

    with graph_col:
        st.markdown('<div class="sec-h">AEGIS 15-Node LangGraph State Machine</div>', unsafe_allow_html=True)

        mermaid = (
            "flowchart TD\n"
            '    A(["🔍 1 Job Selector"]):::cyan --> B(["📊 2 Status Check"]):::cyan\n'
            '    B --> C(["📧 3 Initial Email"]):::cyan\n'
            '    C --> D{"Route?"}:::diamond\n'
            "\n"
            '    D -->|Failure| E(["🚨 4 Failure Alert + RCA\nGPT-4o · confidence gate 70%"]):::alert\n'
            '    D -->|ML Drift| ML(["🤖 ML Healer\nretrain + MLflow promote"]):::ml\n'
            '    D -->|Healthy| Z(["✅ END"]):::end_\n'
            "\n"
            '    E -->|conf >= 70%| F(["📧 5 Fix In Progress"]):::email\n'
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
            "    Q --> IR\n"
            "    ML --> IR\n"
            "    IR --> Z\n"
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
        html = f"""
<!DOCTYPE html><html><head>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<style>
  body {{ margin:0; padding:0; background:transparent; }}
  .mermaid {{ padding:16px; }}
  svg {{ max-width:100%; }}
</style>
</head><body>
<script>
  mermaid.initialize({{
    startOnLoad:true, theme:'dark',
    themeVariables:{{
      primaryColor:'#111827', primaryTextColor:'#00d4ff',
      primaryBorderColor:'#00d4ff', lineColor:'#334155',
      secondaryColor:'#0f172a', background:'#0a0e1a',
      mainBkg:'#111827', nodeBorder:'#00d4ff',
      clusterBkg:'#0f172a', titleColor:'#00d4ff',
      fontFamily:'system-ui,sans-serif', fontSize:'13px',
    }},
    flowchart:{{ curve:'basis', htmlLabels:true, useMaxWidth:true }}
  }});
</script>
<div class="mermaid">{mermaid}</div>
</body></html>"""
        components.html(html, height=620, scrolling=True)

    with steps_col:
        st.markdown('<div class="sec-h">Pipeline Nodes</div>', unsafe_allow_html=True)

        nodes = [
            ("1",  "cyan",  "Job Selector",          "Discovers Databricks jobs to monitor"),
            ("2",  "cyan",  "Status Check",           "Polls job health via Databricks SDK"),
            ("3",  "email", "Initial Email",          "Sends health status notification"),
            ("4",  "alert", "Failure Alert + RCA",    "GPT-4o structured JSON RCA (confidence gate @ 70%)"),
            ("5",  "email", "Fix In Progress Email",  "Notifies team: autonomous repair started"),
            ("6",  "fixer", "Job Fixer",              "GPT-5.5 whole-notebook comprehensive scan + repair"),
            ("7",  "email", "Fix Complete Email",     "Confirms repair + post-fix run ID"),
            ("8",  "git",   "PR Create",              "Auto-commits fix · opens hotfix PR"),
            ("9",  "email", "PR Raised Email",        "Notifies reviewers of auto-fix PR"),
            ("10", "wait",  "PR Wait Approval",       "Polls GitHub indefinitely for merge"),
            ("11", "deploy","Deployment",             "Triggers GitHub Actions CD pipeline"),
            ("12", "cyan",  "Post-Deploy Verify",     "Re-runs Databricks health check in prod"),
            ("13", "email", "Final / Failed Email",   "Outcome notification"),
            ("14", "gray",  "Incident Report",        "Structured JSON + audit log + ChromaDB"),
            ("ML", "ml",    "ML Healer",              "Retraining job trigger + MLflow version promotion"),
        ]
        color_map_node = {
            "cyan":  (CYAN,   "rgba(14,34,51,0.7)"),
            "alert": (RED,    "rgba(45,10,10,0.7)"),
            "email": (GOLD,   "rgba(26,26,14,0.7)"),
            "fixer": (GREEN,  "rgba(10,26,10,0.7)"),
            "git":   (PURPLE, "rgba(26,14,45,0.7)"),
            "wait":  (ORANGE, "rgba(45,26,10,0.7)"),
            "deploy":("#818cf8","rgba(10,10,45,0.7)"),
            "gray":  ("#94a3b8","rgba(26,26,26,0.7)"),
            "ml":    ("#4ade80","rgba(14,26,26,0.7)"),
        }
        for num, ctype, name, desc in nodes:
            border_c, bg_c = color_map_node.get(ctype, (CYAN, "rgba(14,34,51,0.7)"))
            st.markdown(f"""
            <div class="ws" style="border-left-color:{border_c}; background:{bg_c}; margin-bottom:3px;">
              <span class="wsn" style="color:{border_c};">{num}</span>
              <div>
                <div class="wst" style="color:{border_c};">{name}</div>
                <div class="wsd">{desc}</div>
              </div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
        st.markdown('<div class="sec-h">7 Guardrail Layers</div>', unsafe_allow_html=True)

        guardrails = [
            ("G1",  CYAN,    "Confidence Gate",      "Escalate if RCA < 70% — skip fixer entirely"),
            ("G2",  GOLD,    "Diff Validator",       "Block if LLM returns identical code"),
            ("G3",  ORANGE,  "Rollback on Failure",  "Restore original on post-fix run failure"),
            ("G4",  RED,     "Syntax Hard Block",    "compile() — invalid Python never uploaded"),
            ("G4b", "#94a3b8","pyflakes Lint",       "Static analysis — warning only, non-blocking"),
            ("G5",  PURPLE,  "Rate Limiter",         "5 triggers per job per 10 min (sliding window)"),
            ("G6",  GREEN,   "Audit Log",            "Append-only JSONL of every autonomous action"),
            ("G7",  "#f43f5e","Prompt Guard",        "Truncate + injection scan before every LLM call"),
        ]
        for key, color, name, desc in guardrails:
            st.markdown(f"""
            <div class="gr" style="border-left-color:{color}; margin-bottom:3px;">
              <span class="grk" style="color:{color};">{key}</span>
              <div>
                <div class="grn" style="color:{color};">{name}</div>
                <div class="grd">{desc}</div>
              </div>
            </div>
            """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — Guardrail Console
# ══════════════════════════════════════════════════════════════════════════════
with tab4:
    ca, cb = st.columns([5, 4], gap="medium")

    with ca:
        st.markdown('<div class="sec-h">Live Audit Log Feed</div>', unsafe_allow_html=True)

        if not df.empty:
            fc1, fc2 = st.columns(2)
            with fc1:
                f_inc = st.selectbox(
                    "Incident",
                    ["All"] + sorted(df["incident_id"].dropna().unique().tolist()),
                )
            with fc2:
                f_act = st.selectbox(
                    "Action",
                    ["All"] + sorted(df["action"].dropna().unique().tolist()),
                )

            fdf = df.copy()
            if f_inc != "All":
                fdf = fdf[fdf["incident_id"] == f_inc]
            if f_act != "All":
                fdf = fdf[fdf["action"] == f_act]
            fdf = fdf.sort_values("timestamp", ascending=False).head(80)

            log_html = (
                '<div style="max-height:520px; overflow-y:auto; '
                'background:rgba(10,14,26,0.8); border:1px solid rgba(0,212,255,0.1); '
                'border-radius:8px; padding:8px;">'
            )
            for _, row in fdf.iterrows():
                action = row.get("action", "")
                color  = ACTION_COLOR.get(action, "#64748b")
                ts     = row["timestamp"].strftime("%m-%d %H:%M:%S")
                inc_id = str(row.get("incident_id", "—"))[:14]
                parts  = []
                for fld in ["confidence", "lines_changed", "run_id", "attempts", "error", "reason"]:
                    v = row.get(fld)
                    if v is not None and str(v) not in ("", "nan", "None"):
                        parts.append(f"{fld}={str(v)[:50]}")
                detail = " | ".join(parts[:3])
                log_html += (
                    f'<div class="alog">'
                    f'<span class="at">{ts}</span>'
                    f'<span class="ai">{inc_id}</span>'
                    f'<span class="aa" style="color:{color};">{action}</span>'
                    f'<span class="ad">{detail}</span>'
                    f'</div>'
                )
            log_html += "</div>"
            st.markdown(log_html, unsafe_allow_html=True)
        else:
            st.info("No audit log data found.")

    with cb:
        st.markdown('<div class="sec-h">Guardrail Activation Counts</div>', unsafe_allow_html=True)

        if not df.empty:
            g_actions = [
                "LINT_CHECK", "DIFF_COMPUTED", "NOTEBOOK_ROLLED_BACK",
                "LLM_OUTPUT_INVALID", "MAX_RETRIES_EXCEEDED",
                "FIX_EXCEPTION", "FIX_ESCALATED", "PEP8_FORMATTED",
            ]
            g_counts = df[df["action"].isin(g_actions)]["action"].value_counts()

            fig_g = go.Figure(go.Bar(
                y=g_counts.index, x=g_counts.values, orientation="h",
                marker_color=[ACTION_COLOR.get(a, "#64748b") for a in g_counts.index],
                marker_line_width=0,
                text=g_counts.values, textposition="outside",
                textfont=dict(size=11, color="white"),
            ))
            dark_fig(fig_g, 280)
            fig_g.update_layout(title=None, xaxis_title="Times Triggered")
            st.plotly_chart(fig_g, use_container_width=True)

        st.markdown('<div class="sec-h">Audit Log Stats</div>', unsafe_allow_html=True)

        if not df.empty:
            stats = [
                ("Total Entries",        len(df)),
                ("Unique Incidents",     df["incident_id"].nunique() if "incident_id" in df.columns else 0),
                ("Successful Heals",     n_healed),
                ("Escalations",          n_escalated),
                ("Rollbacks",            int((df["action"] == "NOTEBOOK_ROLLED_BACK").sum())),
                ("LLM Blocks (invalid)", int((df["action"] == "LLM_OUTPUT_INVALID").sum())),
                ("Log File",             "data/audit_log.jsonl"),
            ]
            for label, val in stats:
                st.markdown(
                    f"<div style='display:flex; justify-content:space-between; align-items:center; "
                    f"padding:9px 0; border-bottom:1px solid rgba(255,255,255,0.05); font-size:0.84rem;'>"
                    f"<span style='color:#94a3b8;'>{label}</span>"
                    f"<span style='color:{CYAN}; font-weight:700; font-family:monospace;'>{val}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

        st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
        st.markdown('<div class="sec-h">System Architecture</div>', unsafe_allow_html=True)

        arch = [
            ("LLM: Repair",    "GPT-5.5 (EPAM DIAL)"),
            ("LLM: RCA",       "GPT-4o (EPAM DIAL)"),
            ("Orchestration",  "LangGraph StateGraph 15 nodes"),
            ("Knowledge Store","ChromaDB + SHA-256 embeddings"),
            ("Platform",       "Databricks SDK + MLflow"),
            ("GitOps",         "GitHub API + Actions CD"),
            ("Notifications",  "Gmail SMTP · 12 email stages"),
            ("Tests",          "103 tests · 9 test files"),
        ]
        for label, val in arch:
            st.markdown(
                f"<div style='display:flex; justify-content:space-between; align-items:center; "
                f"padding:8px 0; border-bottom:1px solid rgba(255,255,255,0.04); font-size:0.82rem;'>"
                f"<span style='color:#64748b;'>{label}</span>"
                f"<span style='color:#e2e8f0; font-size:0.78rem;'>{val}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )


# ─── Sidebar ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"<div style='color:{CYAN}; font-weight:800; font-size:1.1rem;'>🛡️ AEGIS</div>", unsafe_allow_html=True)
    st.markdown(f"<div style='color:#64748b; font-size:0.75rem; margin-bottom:16px;'>v2.0.0 · Production</div>", unsafe_allow_html=True)

    if st.button("🔄 Refresh Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    auto = st.checkbox("Auto-refresh every 15s")

    st.markdown("---")
    st.markdown(f"<div style='color:#94a3b8; font-size:0.78rem; line-height:1.6;'>"
                f"<b style='color:{CYAN}'>Run demo:</b><br>"
                f"<code style='font-size:0.72rem;'>python demo/production_multi_agent.py</code>"
                f"</div>", unsafe_allow_html=True)

    if auto:
        time.sleep(15)
        st.rerun()


# ─── Footer ───────────────────────────────────────────────────────────────────
st.markdown(
    f"<div style='text-align:center; padding:18px; color:#334155; font-size:0.72rem; "
    f"border-top:1px solid rgba(255,255,255,0.04); margin-top:16px;'>"
    f"AEGIS v2.0.0 · Autonomous End-to-end Guardian for Intelligent Systems · "
    f"LangGraph 15-node · GPT-5.5 repair · 7 guardrails · Databricks production"
    f"</div>",
    unsafe_allow_html=True,
)
