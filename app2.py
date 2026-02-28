"""
BharatAlpha — app.py
====================
Streamlit frontend. 4 views:
  1. Landing / Config
  2. Live Pipeline  (background thread + components.html tracker)
  3. Dashboard      (recommendation cards, charts, metrics)
  4. Report         (rendered markdown)

Design tokens:
  Background : #FFFFFF
  Sidebar    : #0C0C0E
  BUY        : #12A05C
  SELL       : #D93025
  HOLD       : #C49A00
  Brand      : #1400FF
  Fonts      : Cormorant Garamond (display), IBM Plex Mono (data),
               Plus Jakarta Sans (body)
"""

import os
import json
import time
import threading
import queue
from datetime import datetime
from pathlib import Path
from typing import Optional

import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

load_dotenv()

# ── Page config (must be first Streamlit call) ────────────────
st.set_page_config(
    page_title="BharatAlpha",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Google Fonts + Global CSS ─────────────────────────────────
st.markdown("""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,600;0,700;1,400&family=IBM+Plex+Mono:wght@300;400;500&family=Plus+Jakarta+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">

<style>
/* ── Reset & Base ─────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

html, body, [data-testid="stAppViewContainer"] {
    background: #06060A;
    font-family: 'Plus Jakarta Sans', sans-serif;
    color: #E8E8EC;
}

/* ── Hide Streamlit chrome ───────────────────── */
#MainMenu, footer, header { visibility: hidden; }
[data-testid="stDecoration"] { display: none; }
.stDeployButton { display: none; }

/* ── Sidebar ─────────────────────────────────── */
[data-testid="stSidebar"] {
    background: #0A0A10 !important;
    border-right: 1px solid rgba(20,0,255,0.15);
}
[data-testid="stSidebar"] * { color: #E8E8E8 !important; }
[data-testid="stSidebar"] .stTextInput input {
    background: #111118 !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    color: #E8E8E8 !important;
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 12px !important;
}
[data-testid="stSidebar"] .stButton button {
    background: linear-gradient(135deg, #1400FF 0%, #0A00CC 100%) !important;
    color: #FFFFFF !important;
    border: none !important;
    font-family: 'Plus Jakarta Sans', sans-serif !important;
    font-weight: 600 !important;
    letter-spacing: 0.05em !important;
    box-shadow: 0 0 20px rgba(20,0,255,0.3) !important;
    transition: all 0.2s ease !important;
}
[data-testid="stSidebar"] .stButton button:hover {
    background: linear-gradient(135deg, #2510FF 0%, #1400DD 100%) !important;
    box-shadow: 0 0 30px rgba(20,0,255,0.5) !important;
    transform: translateY(-1px) !important;
}
[data-testid="stSidebar"] hr {
    border-color: rgba(255,255,255,0.06) !important;
}

/* ── Main content ────────────────────────────── */
.block-container {
    padding: 0 !important;
    max-width: 100% !important;
}

/* ── Typography ──────────────────────────────── */
.ba-display {
    font-family: 'Cormorant Garamond', serif;
    font-weight: 300;
    font-size: 4.5rem;
    line-height: 1.02;
    letter-spacing: -0.03em;
    color: #F0F0F8;
}
.ba-display span {
    color: #1400FF;
    text-shadow: 0 0 60px rgba(20,0,255,0.4);
}
.ba-subtitle {
    font-family: 'Plus Jakarta Sans', sans-serif;
    font-weight: 300;
    font-size: 0.95rem;
    color: rgba(200,200,220,0.6);
    letter-spacing: 0.02em;
    line-height: 1.7;
}
.ba-label {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.68rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: rgba(150,150,180,0.6);
}
.ba-mono {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.85rem;
}

/* ── Section divider ─────────────────────────── */
.ba-divider {
    height: 1px;
    background: linear-gradient(90deg, #1400FF 0%, transparent 60%);
    margin: 2rem 0;
    opacity: 0.2;
}

/* ── Recommendation cards ────────────────────── */
.rec-card {
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 4px;
    padding: 1.5rem;
    position: relative;
    transition: all 0.3s ease;
    background: rgba(255,255,255,0.02);
    backdrop-filter: blur(10px);
    overflow: hidden;
}
.rec-card::before {
    content: '';
    position: absolute;
    inset: 0;
    background: radial-gradient(circle at 50% 0%, rgba(20,0,255,0.05) 0%, transparent 70%);
    pointer-events: none;
}
.rec-card:hover {
    border-color: rgba(20,0,255,0.3);
    box-shadow: 0 8px 40px rgba(0,0,0,0.4), 0 0 0 1px rgba(20,0,255,0.1);
    transform: translateY(-2px);
}
.rec-card .accent-bar {
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    border-radius: 4px 4px 0 0;
}
.rec-card .symbol {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 1.1rem;
    font-weight: 500;
    margin-top: 0.5rem;
    color: #F0F0F8;
}
.rec-card .company {
    font-family: 'Plus Jakarta Sans', sans-serif;
    font-size: 0.75rem;
    color: rgba(200,200,220,0.5);
    margin-top: 0.1rem;
}
.rec-card .score-badge {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 1.6rem;
    font-weight: 500;
    margin-top: 1rem;
}
.rec-card .rec-tag {
    display: inline-block;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.62rem;
    font-weight: 500;
    letter-spacing: 0.12em;
    padding: 0.2rem 0.6rem;
    border-radius: 2px;
    margin-top: 0.5rem;
}
.rec-card .price-target {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.78rem;
    color: rgba(200,200,220,0.5);
    margin-top: 0.8rem;
    padding-top: 0.8rem;
    border-top: 1px solid rgba(255,255,255,0.05);
}
.tag-buy   { background: rgba(18,160,92,0.15); color: #12A05C; border: 1px solid rgba(18,160,92,0.3); }
.tag-hold  { background: rgba(196,154,0,0.15);  color: #C49A00; border: 1px solid rgba(196,154,0,0.3); }
.tag-sell  { background: rgba(217,48,37,0.15);  color: #D93025; border: 1px solid rgba(217,48,37,0.3); }
.tag-avoid { background: rgba(217,48,37,0.15);  color: #D93025; border: 1px solid rgba(217,48,37,0.3); }

/* ── Metrics strip ───────────────────────────── */
.metric-pill {
    background: rgba(255,255,255,0.02);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 4px;
    padding: 1rem 1.5rem;
    text-align: center;
    transition: all 0.2s ease;
}
.metric-pill:hover {
    border-color: rgba(20,0,255,0.2);
    background: rgba(20,0,255,0.03);
}
.metric-pill .val {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 1.4rem;
    font-weight: 500;
    color: #F0F0F8;
}
.metric-pill .lbl {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.62rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: rgba(150,150,180,0.5);
    margin-top: 0.2rem;
}

/* ── Status badges ───────────────────────────── */
.status-running {
    display: inline-flex; align-items: center; gap: 6px;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.72rem; letter-spacing: 0.08em;
    color: #1400FF;
}
.status-running::before {
    content: '';
    width: 7px; height: 7px;
    background: #1400FF;
    border-radius: 50%;
    animation: pulse 1.2s ease-in-out infinite;
    box-shadow: 0 0 8px rgba(20,0,255,0.6);
}
.status-done {
    display: inline-flex; align-items: center; gap: 6px;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.72rem; letter-spacing: 0.08em;
    color: #12A05C;
}
@keyframes pulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50%       { opacity: 0.4; transform: scale(1.3); }
}

/* ── Nav tabs ────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
    gap: 0;
    border-bottom: 1px solid rgba(255,255,255,0.06);
    background: transparent;
    padding: 0 3rem;
}
.stTabs [data-baseweb="tab"] {
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 0.72rem !important;
    letter-spacing: 0.1em !important;
    text-transform: uppercase !important;
    color: rgba(150,150,180,0.5) !important;
    padding: 1rem 1.5rem !important;
    border-radius: 0 !important;
    border-bottom: 2px solid transparent !important;
}
.stTabs [aria-selected="true"] {
    color: #E8E8EC !important;
    border-bottom: 2px solid #1400FF !important;
    background: transparent !important;
}

/* ── Primary button ──────────────────────────── */
.stButton > button[kind="primary"],
.stButton > button {
    background: linear-gradient(135deg, #1400FF 0%, #0A00CC 100%) !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 3px !important;
    font-family: 'Plus Jakarta Sans', sans-serif !important;
    font-size: 0.82rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.06em !important;
    padding: 0.6rem 1.8rem !important;
    transition: all 0.2s ease !important;
    box-shadow: 0 0 20px rgba(20,0,255,0.25) !important;
}
.stButton > button:hover {
    background: linear-gradient(135deg, #2510FF 0%, #1400DD 100%) !important;
    box-shadow: 0 0 30px rgba(20,0,255,0.45) !important;
    transform: translateY(-1px) !important;
}

/* ── Text inputs ─────────────────────────────── */
.stTextInput input, .stSelectbox select {
    border-radius: 3px !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 0.85rem !important;
    background: rgba(255,255,255,0.03) !important;
    color: #E8E8EC !important;
}
.stTextInput input:focus {
    border-color: rgba(20,0,255,0.5) !important;
    box-shadow: 0 0 0 1px rgba(20,0,255,0.3) !important;
}

/* ── Log viewer ──────────────────────────────── */
.log-viewer {
    background: #06060A;
    border: 1px solid rgba(255,255,255,0.04);
    border-radius: 3px;
    padding: 1rem 1.2rem;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.72rem;
    line-height: 1.7;
    color: #A8B8A8;
    max-height: 280px;
    overflow-y: auto;
}
.log-viewer .log-time { color: #333355; }
.log-viewer .log-agent { color: #1400FF; }
.log-viewer .log-msg { color: #6A7A6A; }

/* ── Tab content padding ─────────────────────── */
[data-testid="stTabsContent"] {
    padding: 2rem 3rem;
}

/* ── Info card grid on landing ───────────────── */
.info-card {
    padding: 1.5rem;
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 4px;
    height: 100%;
    background: rgba(255,255,255,0.015);
    transition: all 0.3s ease;
    position: relative;
    overflow: hidden;
}
.info-card::after {
    content: '';
    position: absolute;
    bottom: 0; left: 0; right: 0;
    height: 1px;
    background: linear-gradient(90deg, transparent, rgba(20,0,255,0.3), transparent);
    opacity: 0;
    transition: opacity 0.3s ease;
}
.info-card:hover {
    border-color: rgba(20,0,255,0.2);
    background: rgba(20,0,255,0.02);
}
.info-card:hover::after { opacity: 1; }
.info-card .card-icon {
    font-size: 1.2rem;
    margin-bottom: 0.8rem;
    opacity: 0.6;
}
.info-card .card-title {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.62rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: rgba(150,150,180,0.5);
    margin-bottom: 0.8rem;
}
.info-card .card-content {
    font-family: 'Plus Jakarta Sans', sans-serif;
    font-size: 0.82rem;
    line-height: 1.85;
    color: rgba(200,200,220,0.55);
}
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
#  SESSION STATE INITIALISATION
# ─────────────────────────────────────────────

def _init_state():
    defaults = {
        "pipeline_running":  False,
        "pipeline_done":     False,
        "pipeline_result":   None,
        "pipeline_error":    None,
        "task_status":       {t: "pending" for t in [
            "analyze_market_context",
            "screen_universe",
            "analyze_fundamentals",
            "analyze_technicals",
            "assess_sentiment",
            "evaluate_risk",
            "construct_portfolio",
            "generate_report",
        ]},
        "agent_logs":        [],      # list of (timestamp, agent, message)
        "current_agent":     None,
        "log_queue":         queue.Queue(),
        "watchlist":         [],
        "active_tab":        0,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()


# ─────────────────────────────────────────────
#  CONSTANTS
# ─────────────────────────────────────────────

TASK_LABELS = {
    "analyze_market_context": "Market Context",
    "screen_universe":        "Screen Universe",
    "analyze_fundamentals":   "Fundamentals",
    "analyze_technicals":     "Technicals",
    "assess_sentiment":       "Sentiment",
    "evaluate_risk":          "Risk Assessment",
    "construct_portfolio":    "Portfolio",
    "generate_report":        "Report",
}

TASK_AGENTS = {
    "analyze_market_context": "market_context_agent",
    "screen_universe":        "stock_screener_agent",
    "analyze_fundamentals":   "fundamental_analyst_agent",
    "analyze_technicals":     "technical_analyst_agent",
    "assess_sentiment":       "sentiment_analyst_agent",
    "evaluate_risk":          "risk_analyst_agent",
    "construct_portfolio":    "portfolio_manager_agent",
    "generate_report":        "report_generator_agent",
}

OUTPUT_DIR = Path(__file__).parent / "output"


# ─────────────────────────────────────────────
#  PIPELINE CALLBACKS & RUNNER
# ─────────────────────────────────────────────

def _make_callbacks(q):
    def step_callback(step_output):
        try:
            msg = str(step_output)[:300]
            ts  = datetime.now().strftime("%H:%M:%S")
            q.put(("step", ts, "agent", msg))
        except Exception:
            pass

    def task_callback(task_output):
        try:
            ts = datetime.now().strftime("%H:%M:%S")
            q.put(("task_done", ts, "", ""))
        except Exception:
            pass

    return step_callback, task_callback


def _run_pipeline_thread(q):
    try:
        from src.crew import run_pipeline
        step_cb, task_cb = _make_callbacks(q)
        result = run_pipeline(
            step_callback=step_cb,
            task_callback=task_cb
        )
        q.put(("done", "", "", json.dumps(result, default=str)))
    except Exception as e:
        q.put(("error", "", "", str(e)))


def _drain_log_queue():
    completed = False
    q = st.session_state["log_queue"]

    while not q.empty():
        try:
            item = q.get_nowait()
            kind = item[0]

            if kind == "step":
                _, ts, agent, msg = item
                st.session_state["agent_logs"].append((ts, agent, msg))
                st.session_state["current_agent"] = agent
                if len(st.session_state["agent_logs"]) > 120:
                    st.session_state["agent_logs"] = st.session_state["agent_logs"][-120:]

            elif kind == "task_done":
                for task_key in st.session_state["task_status"]:
                    if st.session_state["task_status"][task_key] == "running":
                        st.session_state["task_status"][task_key] = "done"
                        break
                for task_key in st.session_state["task_status"]:
                    if st.session_state["task_status"][task_key] == "pending":
                        st.session_state["task_status"][task_key] = "running"
                        st.session_state["current_agent"] = TASK_AGENTS.get(task_key, "")
                        break

            elif kind == "done":
                _, _, _, payload = item
                try:
                    result = json.loads(payload)
                except Exception:
                    result = {"status": "success", "raw": payload}
                st.session_state["pipeline_result"]  = result
                st.session_state["pipeline_running"] = False
                st.session_state["pipeline_done"]    = True
                for k in st.session_state["task_status"]:
                    st.session_state["task_status"][k] = "done"
                completed = True

            elif kind == "error":
                _, _, _, err = item
                st.session_state["pipeline_error"]   = err
                st.session_state["pipeline_running"] = False
                st.session_state["pipeline_done"]    = True
                completed = True

        except queue.Empty:
            break

    return completed


def _start_pipeline():
    st.session_state["pipeline_running"] = True
    st.session_state["pipeline_done"]    = False
    st.session_state["pipeline_result"]  = None
    st.session_state["pipeline_error"]   = None
    st.session_state["agent_logs"]       = []
    st.session_state["task_status"]      = {t: "pending" for t in TASK_LABELS}
    st.session_state["log_queue"]        = queue.Queue()

    first = list(TASK_LABELS.keys())[0]
    st.session_state["task_status"][first] = "running"
    st.session_state["current_agent"] = TASK_AGENTS[first]

    q = st.session_state["log_queue"]
    thread = threading.Thread(target=_run_pipeline_thread, args=(q,), daemon=True)
    thread.start()


# ─────────────────────────────────────────────
#  OUTPUT FILE HELPERS
# ─────────────────────────────────────────────

def _load_json(filename: str) -> Optional[dict]:
    path = OUTPUT_DIR / filename
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return None
    return None


def _load_report() -> Optional[str]:
    path = OUTPUT_DIR / "08_research_report.md"
    if path.exists():
        return path.read_text()
    return None


# ─────────────────────────────────────────────
#  PIPELINE TRACKER HTML
# ─────────────────────────────────────────────

def _render_pipeline_tracker():
    statuses = st.session_state["task_status"]
    stages   = list(TASK_LABELS.items())

    stage_html = ""
    for i, (key, label) in enumerate(stages):
        status = statuses.get(key, "pending")
        if status == "done":
            icon    = "✓"
            cls     = "stage-done"
            dot_cls = "dot-done"
        elif status == "running":
            icon    = "◉"
            cls     = "stage-running"
            dot_cls = "dot-running"
        else:
            icon    = str(i + 1)
            cls     = "stage-pending"
            dot_cls = "dot-pending"

        connector = '<div class="connector"></div>' if i < len(stages) - 1 else ""
        stage_html += f"""
        <div class="stage-wrap">
            <div class="stage {cls}">
                <div class="dot {dot_cls}">{icon}</div>
                <div class="stage-label">{label}</div>
            </div>
            {connector}
        </div>
        """

    logs = st.session_state.get("agent_logs", [])[-8:]
    log_lines = ""
    for ts, agent, msg in logs:
        short_msg = msg[:120].replace("<", "&lt;").replace(">", "&gt;")
        log_lines += f'<div class="log-line"><span class="t">{ts}</span> <span class="a">{agent}</span> <span class="m">{short_msg}</span></div>'

    if not log_lines:
        log_lines = '<div class="log-line idle"><span class="m">Waiting for agent output...</span></div>'

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;500&family=Plus+Jakarta+Sans:wght@300;400;500&display=swap" rel="stylesheet">
    <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
        font-family: 'Plus Jakarta Sans', sans-serif;
        background: #06060A;
        padding: 20px;
    }}
    .tracker {{
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        gap: 0;
        margin-bottom: 20px;
    }}
    .stage-wrap {{
        display: flex;
        align-items: center;
    }}
    .stage {{
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 8px 12px;
        border-radius: 3px;
        transition: all 0.3s ease;
    }}
    .dot {{
        width: 26px; height: 26px;
        border-radius: 50%;
        display: flex; align-items: center; justify-content: center;
        font-family: 'IBM Plex Mono', monospace;
        font-size: 11px;
        font-weight: 500;
        flex-shrink: 0;
        transition: all 0.3s ease;
    }}
    .dot-done    {{ background: rgba(18,160,92,0.15); color: #12A05C; border: 1px solid rgba(18,160,92,0.3); }}
    .dot-running {{ background: #1400FF; color: #FFFFFF; animation: pulse 1.2s ease-in-out infinite; box-shadow: 0 0 12px rgba(20,0,255,0.5); }}
    .dot-pending {{ background: rgba(255,255,255,0.04); color: rgba(150,150,180,0.3); border: 1px solid rgba(255,255,255,0.05); }}
    .stage-label {{
        font-family: 'IBM Plex Mono', monospace;
        font-size: 10px;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        white-space: nowrap;
        transition: color 0.3s ease;
    }}
    .stage-done    .stage-label {{ color: #12A05C; }}
    .stage-running .stage-label {{ color: #1400FF; font-weight: 500; }}
    .stage-pending .stage-label {{ color: rgba(150,150,180,0.25); }}
    .connector {{
        width: 20px; height: 1px;
        background: rgba(255,255,255,0.06);
        flex-shrink: 0;
    }}
    @keyframes pulse {{
        0%, 100% {{ opacity: 1; box-shadow: 0 0 0 0 rgba(20,0,255,0.5); }}
        50%       {{ opacity: 0.85; box-shadow: 0 0 0 6px rgba(20,0,255,0); }}
    }}
    .log-panel {{
        background: #03030A;
        border: 1px solid rgba(255,255,255,0.04);
        border-radius: 3px;
        padding: 14px 16px;
        min-height: 140px;
        max-height: 180px;
        overflow-y: auto;
    }}
    .log-header {{
        font-family: 'IBM Plex Mono', monospace;
        font-size: 9px;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        color: rgba(100,100,140,0.5);
        margin-bottom: 10px;
    }}
    .log-line {{
        font-family: 'IBM Plex Mono', monospace;
        font-size: 11px;
        line-height: 1.8;
        display: flex;
        gap: 10px;
        flex-wrap: wrap;
    }}
    .log-line .t {{ color: #22223A; flex-shrink: 0; }}
    .log-line .a {{ color: rgba(20,0,255,0.7); flex-shrink: 0; max-width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .log-line .m {{ color: rgba(120,130,120,0.7); flex: 1; }}
    .log-line.idle .m {{ color: rgba(80,80,100,0.5); font-style: italic; }}
    </style>
    </head>
    <body>
    <div class="tracker">
        {stage_html}
    </div>
    <div class="log-panel">
        <div class="log-header">▸ Live Agent Output</div>
        {log_lines}
    </div>
    </body>
    </html>
    """
    components.html(html, height=320, scrolling=False)


# ─────────────────────────────────────────────
#  SIDEBAR
# ─────────────────────────────────────────────

def _render_sidebar():
    with st.sidebar:
        st.markdown("""
        <div style="padding: 1.5rem 0 1rem;">
            <div style="font-family:'Cormorant Garamond',serif;font-size:1.7rem;
                        font-weight:300;letter-spacing:-0.01em;color:#E8E8EC;">
                Bharat<span style="color:#1400FF;text-shadow:0 0 20px rgba(20,0,255,0.4);">Alpha</span>
            </div>
            <div style="font-family:'IBM Plex Mono',monospace;font-size:0.6rem;
                        letter-spacing:0.14em;text-transform:uppercase;
                        color:rgba(100,100,140,0.5);margin-top:4px;">
                Indian Equity Research
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("---")

        if st.session_state["pipeline_running"]:
            st.markdown('<div class="status-running">PIPELINE RUNNING</div>', unsafe_allow_html=True)
        elif st.session_state["pipeline_done"]:
            st.markdown('<div class="status-done">✓ ANALYSIS COMPLETE</div>', unsafe_allow_html=True)
        else:
            st.markdown("""
            <div style="font-family:'IBM Plex Mono',monospace;font-size:0.68rem;
                        letter-spacing:0.1em;color:rgba(100,100,140,0.4);">
            READY
            </div>""", unsafe_allow_html=True)

        st.markdown("---")

        run_disabled = st.session_state["pipeline_running"]
        if st.button(
            "▶  RUN ANALYSIS" if not run_disabled else "⟳  RUNNING...",
            disabled=run_disabled,
            use_container_width=True
        ):
            _start_pipeline()
            st.rerun()

        st.markdown("---")

        st.markdown("""
        <div style="font-family:'IBM Plex Mono',monospace;font-size:0.62rem;
                    letter-spacing:0.14em;text-transform:uppercase;
                    color:rgba(100,100,140,0.4);margin-bottom:8px;">
            Watchlist
        </div>""", unsafe_allow_html=True)

        new_symbol = st.text_input(
            label="Add symbol",
            placeholder="e.g. ZOMATO",
            label_visibility="collapsed",
            key="watchlist_input"
        )
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Add", use_container_width=True):
                sym = new_symbol.strip().upper()
                if sym and sym not in st.session_state["watchlist"]:
                    st.session_state["watchlist"].append(sym)
                    st.rerun()
        with col2:
            if st.button("Clear", use_container_width=True):
                st.session_state["watchlist"] = []
                st.rerun()

        if st.session_state["watchlist"]:
            for sym in st.session_state["watchlist"]:
                st.markdown(f"""
                <div style="font-family:'IBM Plex Mono',monospace;font-size:0.75rem;
                            color:rgba(200,200,220,0.6);padding:4px 0;
                            border-bottom:1px solid rgba(255,255,255,0.04);">
                    {sym}
                </div>""", unsafe_allow_html=True)
        else:
            st.markdown("""
            <div style="font-family:'IBM Plex Mono',monospace;font-size:0.7rem;
                        color:rgba(100,100,140,0.3);font-style:italic;">
                No symbols added
            </div>""", unsafe_allow_html=True)

        st.markdown("---")

        keys_present = all([
            os.getenv("ANGEL_API_KEY"),
            os.getenv("ANGEL_CLIENT_ID"),
            os.getenv("ANTHROPIC_API_KEY"),
        ])
        env_colour = "#12A05C" if keys_present else "#D93025"
        env_label  = "ENV OK" if keys_present else "ENV MISSING"
        st.markdown(f"""
        <div style="font-family:'IBM Plex Mono',monospace;font-size:0.62rem;
                    letter-spacing:0.1em;color:{env_colour};">
            ● {env_label}
        </div>""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
#  TAB 1 — LANDING / CONFIG  (with particle network)
# ─────────────────────────────────────────────

def _render_landing():
    # ── Particle network hero via components.html ──
    components.html("""
    <!DOCTYPE html>
    <html>
    <head>
    <link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,600&family=IBM+Plex+Mono:wght@300;400;500&family=Plus+Jakarta+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">
    <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
        background: #06060A;
        overflow: hidden;
        font-family: 'Plus Jakarta Sans', sans-serif;
    }
    #hero {
        position: relative;
        width: 100%;
        height: 420px;
        overflow: hidden;
    }
    canvas {
        position: absolute;
        inset: 0;
        width: 100%;
        height: 100%;
    }
    .hero-content {
        position: absolute;
        inset: 0;
        display: flex;
        flex-direction: column;
        justify-content: center;
        padding: 0 3rem;
        z-index: 10;
    }
    .hero-eyebrow {
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.65rem;
        letter-spacing: 0.2em;
        text-transform: uppercase;
        color: rgba(20,0,255,0.7);
        margin-bottom: 1.2rem;
        opacity: 0;
        transform: translateY(10px);
        animation: fadeUp 0.8s ease forwards 0.2s;
    }
    .hero-title {
        font-family: 'Cormorant Garamond', serif;
        font-weight: 300;
        font-size: 4.2rem;
        line-height: 1.02;
        letter-spacing: -0.03em;
        color: #F0F0F8;
        opacity: 0;
        transform: translateY(16px);
        animation: fadeUp 1s ease forwards 0.4s;
    }
    .hero-title .accent {
        color: #1400FF;
        text-shadow: 0 0 80px rgba(20,0,255,0.35);
        font-style: italic;
    }
    .hero-sub {
        font-family: 'Plus Jakarta Sans', sans-serif;
        font-weight: 300;
        font-size: 0.9rem;
        color: rgba(200,200,220,0.5);
        line-height: 1.7;
        max-width: 480px;
        margin-top: 1.2rem;
        opacity: 0;
        transform: translateY(12px);
        animation: fadeUp 0.9s ease forwards 0.7s;
    }
    .hero-stats {
        display: flex;
        gap: 2.5rem;
        margin-top: 2rem;
        opacity: 0;
        transform: translateY(10px);
        animation: fadeUp 0.9s ease forwards 1s;
    }
    .hero-stat-val {
        font-family: 'IBM Plex Mono', monospace;
        font-size: 1.3rem;
        font-weight: 500;
        color: #E8E8EC;
    }
    .hero-stat-lbl {
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.58rem;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: rgba(120,120,160,0.5);
        margin-top: 2px;
    }
    .hero-stat-divider {
        width: 1px;
        height: 36px;
        background: rgba(255,255,255,0.06);
        align-self: center;
    }
    .bottom-gradient {
        position: absolute;
        bottom: 0; left: 0; right: 0;
        height: 100px;
        background: linear-gradient(to bottom, transparent, #06060A);
        pointer-events: none;
        z-index: 5;
    }
    @keyframes fadeUp {
        to { opacity: 1; transform: translateY(0); }
    }
    </style>
    </head>
    <body>
    <div id="hero">
        <canvas id="particle-canvas"></canvas>
        <div class="hero-content">
            <div class="hero-eyebrow">AI-Powered Indian Equity Research</div>
            <div class="hero-title">
                Indian Equity<br>Research &amp; <span class="accent">Intelligence</span>
            </div>
            <div class="hero-sub">
                Eight specialised AI agents analyse the Nifty 500 universe —
                fundamentals, technicals, sentiment, and risk — to surface
                high-conviction investment opportunities.
            </div>
            <div class="hero-stats">
                <div>
                    <div class="hero-stat-val">500+</div>
                    <div class="hero-stat-lbl">Stocks Screened</div>
                </div>
                <div class="hero-stat-divider"></div>
                <div>
                    <div class="hero-stat-val">8</div>
                    <div class="hero-stat-lbl">AI Agents</div>
                </div>
                <div class="hero-stat-divider"></div>
                <div>
                    <div class="hero-stat-val">3–5</div>
                    <div class="hero-stat-lbl">BUY Picks</div>
                </div>
                <div class="hero-stat-divider"></div>
                <div>
                    <div class="hero-stat-val" id="live-time">--:--</div>
                    <div class="hero-stat-lbl">IST</div>
                </div>
            </div>
        </div>
        <div class="bottom-gradient"></div>
    </div>

    <script>
    // ── Live clock ────────────────────────────────────────────
    function updateClock() {
        const now = new Date();
        const ist = new Date(now.getTime() + (5.5 * 60 * 60 * 1000));
        const h = String(ist.getUTCHours()).padStart(2, '0');
        const m = String(ist.getUTCMinutes()).padStart(2, '0');
        const s = String(ist.getUTCSeconds()).padStart(2, '0');
        const el = document.getElementById('live-time');
        if (el) el.textContent = h + ':' + m + ':' + s;
    }
    setInterval(updateClock, 1000);
    updateClock();

    // ── Particle Network ─────────────────────────────────────
    const canvas = document.getElementById('particle-canvas');
    const ctx    = canvas.getContext('2d');

    function resize() {
        canvas.width  = canvas.offsetWidth;
        canvas.height = canvas.offsetHeight;
    }
    resize();
    window.addEventListener('resize', resize);

    const PARTICLE_COUNT = 90;
    const MAX_DIST       = 130;
    const BRAND_BLUE     = [20, 0, 255];
    const ACCENT_GREEN   = [18, 160, 92];

    class Particle {
        constructor() { this.reset(true); }
        reset(init) {
            this.x  = Math.random() * canvas.width;
            this.y  = init ? Math.random() * canvas.height : -10;
            this.vx = (Math.random() - 0.5) * 0.35;
            this.vy = (Math.random() - 0.5) * 0.35;
            this.r  = Math.random() * 1.8 + 0.6;
            // mix of blue, white, and occasional green
            const roll = Math.random();
            if (roll < 0.55)      this.col = BRAND_BLUE;
            else if (roll < 0.70) this.col = ACCENT_GREEN;
            else                  this.col = [180, 180, 220];
            this.baseAlpha = Math.random() * 0.5 + 0.2;
            this.alpha     = 0;
            this.life      = 0;
            this.maxLife   = Math.random() * 400 + 200;
        }
        update() {
            this.x += this.vx;
            this.y += this.vy;
            this.life++;
            // fade in/out
            const lifeRatio = this.life / this.maxLife;
            if (lifeRatio < 0.1)       this.alpha = this.baseAlpha * (lifeRatio / 0.1);
            else if (lifeRatio > 0.85) this.alpha = this.baseAlpha * (1 - (lifeRatio - 0.85) / 0.15);
            else                       this.alpha = this.baseAlpha;
            if (this.life > this.maxLife ||
                this.x < -20 || this.x > canvas.width + 20 ||
                this.y < -20 || this.y > canvas.height + 20) {
                this.reset(false);
            }
        }
        draw() {
            ctx.beginPath();
            ctx.arc(this.x, this.y, this.r, 0, Math.PI * 2);
            ctx.fillStyle = `rgba(${this.col[0]},${this.col[1]},${this.col[2]},${this.alpha})`;
            ctx.fill();
        }
    }

    const particles = Array.from({ length: PARTICLE_COUNT }, () => new Particle());
    let mouse = { x: -9999, y: -9999 };

    canvas.addEventListener('mousemove', e => {
        const rect = canvas.getBoundingClientRect();
        mouse.x = e.clientX - rect.left;
        mouse.y = e.clientY - rect.top;
    });
    canvas.addEventListener('mouseleave', () => { mouse.x = -9999; mouse.y = -9999; });

    function drawConnections() {
        for (let i = 0; i < particles.length; i++) {
            for (let j = i + 1; j < particles.length; j++) {
                const a = particles[i];
                const b = particles[j];
                const dx = a.x - b.x;
                const dy = a.y - b.y;
                const dist = Math.sqrt(dx * dx + dy * dy);
                if (dist < MAX_DIST) {
                    const opacityFactor = (1 - dist / MAX_DIST);
                    const edgeAlpha = opacityFactor * Math.min(a.alpha, b.alpha) * 0.6;
                    // colour-blend the line to match particles
                    const cr = Math.round((a.col[0] + b.col[0]) / 2);
                    const cg = Math.round((a.col[1] + b.col[1]) / 2);
                    const cb = Math.round((a.col[2] + b.col[2]) / 2);
                    ctx.beginPath();
                    ctx.moveTo(a.x, a.y);
                    ctx.lineTo(b.x, b.y);
                    ctx.strokeStyle = `rgba(${cr},${cg},${cb},${edgeAlpha})`;
                    ctx.lineWidth   = 0.5 * opacityFactor;
                    ctx.stroke();
                }
            }

            // mouse attraction lines
            const p  = particles[i];
            const dx = p.x - mouse.x;
            const dy = p.y - mouse.y;
            const md = Math.sqrt(dx * dx + dy * dy);
            if (md < 160) {
                const ma = (1 - md / 160) * p.alpha * 0.9;
                ctx.beginPath();
                ctx.moveTo(p.x, p.y);
                ctx.lineTo(mouse.x, mouse.y);
                ctx.strokeStyle = `rgba(20,0,255,${ma})`;
                ctx.lineWidth   = 0.6;
                ctx.stroke();
            }
        }
    }

    function loop() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);

        // subtle radial glow at center-left
        const grad = ctx.createRadialGradient(
            canvas.width * 0.25, canvas.height * 0.5, 0,
            canvas.width * 0.25, canvas.height * 0.5, canvas.width * 0.5
        );
        grad.addColorStop(0,   'rgba(20,0,255,0.04)');
        grad.addColorStop(0.5, 'rgba(20,0,255,0.01)');
        grad.addColorStop(1,   'transparent');
        ctx.fillStyle = grad;
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        drawConnections();
        particles.forEach(p => { p.update(); p.draw(); });
        requestAnimationFrame(loop);
    }
    loop();
    </script>
    </body>
    </html>
    """, height=420, scrolling=False)

    # ── Info cards row ──────────────────────────
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("""
        <div class="info-card">
            <div class="card-icon">◈</div>
            <div class="card-title">Data Sources</div>
            <div class="card-content">
                Angel One SmartAPI<br>
                Screener.in<br>
                NSE / BSE APIs<br>
                Financial RSS Feeds
            </div>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown("""
        <div class="info-card">
            <div class="card-icon">⬡</div>
            <div class="card-title">Analysis Pipeline</div>
            <div class="card-content">
                Macro context → Screen 500+<br>
                Fundamental deep-dive<br>
                Technical entry timing<br>
                Sentiment + Risk scoring
            </div>
        </div>
        """, unsafe_allow_html=True)
    with col3:
        st.markdown("""
        <div class="info-card">
            <div class="card-icon">◎</div>
            <div class="card-title">Output</div>
            <div class="card-content">
                3–5 BUY recommendations<br>
                Position sizing<br>
                Price targets + stops<br>
                Institutional research report
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown('<div class="ba-divider" style="margin-top:1.5rem;"></div>', unsafe_allow_html=True)

    # ── Environment setup ───────────────────────
    st.markdown('<div class="ba-label" style="margin-bottom:0.8rem;">Environment Setup</div>', unsafe_allow_html=True)

    env_vars = {
        "ANGEL_API_KEY":       os.getenv("ANGEL_API_KEY", ""),
        "ANGEL_CLIENT_ID":     os.getenv("ANGEL_CLIENT_ID", ""),
        "ANGEL_MPIN":          os.getenv("ANGEL_MPIN", ""),
        "ANGEL_TOTP_SECRET":   os.getenv("ANGEL_TOTP_SECRET", ""),
        "ANTHROPIC_API_KEY":   os.getenv("ANTHROPIC_API_KEY", ""),
        "SERPER_API_KEY":      os.getenv("SERPER_API_KEY", ""),
    }

    cols = st.columns(3)
    for i, (key, val) in enumerate(env_vars.items()):
        with cols[i % 3]:
            present = bool(val)
            colour  = "#12A05C" if present else "#D93025"
            status  = "SET" if present else "MISSING"
            bg      = "rgba(18,160,92,0.05)" if present else "rgba(217,48,37,0.05)"
            border  = "rgba(18,160,92,0.15)" if present else "rgba(217,48,37,0.15)"
            st.markdown(f"""
            <div style="font-family:'IBM Plex Mono',monospace;font-size:0.72rem;
                        padding:0.6rem 0.8rem;border:1px solid {border};
                        background:{bg};
                        border-radius:3px;margin-bottom:0.5rem;
                        display:flex;justify-content:space-between;align-items:center;">
                <span style="color:rgba(180,180,210,0.7);">{key}</span>
                <span style="color:{colour};font-size:0.6rem;
                             letter-spacing:0.1em;">{status}</span>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("""
    <div style="margin-top:1rem;font-family:'IBM Plex Mono',monospace;
                font-size:0.72rem;color:rgba(100,100,140,0.5);">
        Add credentials to <code style="background:rgba(255,255,255,0.05);
        padding:2px 6px;border-radius:2px;color:rgba(200,200,220,0.6);">.env</code>
        in the project root, then press
        <strong style="color:#1400FF;">RUN ANALYSIS</strong> in the sidebar.
    </div>
    """, unsafe_allow_html=True)


# ─────────────────────────────────────────────
#  TAB 2 — LIVE PIPELINE
# ─────────────────────────────────────────────

def _render_pipeline():
    if not st.session_state["pipeline_running"] and not st.session_state["pipeline_done"]:
        st.markdown("""
        <div style="text-align:center;padding:4rem 0;color:rgba(100,100,140,0.4);
                    font-family:'IBM Plex Mono',monospace;font-size:0.82rem;">
            Pipeline has not been started.<br>
            <span style="font-size:0.7rem;color:rgba(80,80,120,0.4);">
                Press <strong style="color:#1400FF;">RUN ANALYSIS</strong> in the sidebar.
            </span>
        </div>
        """, unsafe_allow_html=True)
        return

    st.markdown('<div class="ba-label" style="margin-bottom:1rem;">Pipeline Progress</div>', unsafe_allow_html=True)

    if st.session_state["pipeline_running"]:
        _drain_log_queue()

    _render_pipeline_tracker()

    if st.session_state["pipeline_done"]:
        st.markdown('<div class="ba-divider"></div>', unsafe_allow_html=True)

        if st.session_state["pipeline_error"]:
            st.error(f"Pipeline error: {st.session_state['pipeline_error']}")
        else:
            result = st.session_state.get("pipeline_result") or {}
            dq     = result.get("data_quality") or {}

            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.markdown(f"""
                <div class="metric-pill">
                    <div class="val" style="color:#12A05C;">✓</div>
                    <div class="lbl">Complete</div>
                </div>""", unsafe_allow_html=True)
            with c2:
                warnings = dq.get("warnings", 0)
                st.markdown(f"""
                <div class="metric-pill">
                    <div class="val">{warnings}</div>
                    <div class="lbl">Warnings</div>
                </div>""", unsafe_allow_html=True)
            with c3:
                criticals = dq.get("criticals", 0)
                col = "#D93025" if criticals > 0 else "#F0F0F8"
                st.markdown(f"""
                <div class="metric-pill">
                    <div class="val" style="color:{col};">{criticals}</div>
                    <div class="lbl">Critical</div>
                </div>""", unsafe_allow_html=True)
            with c4:
                conf = dq.get("confidence_multiplier", 1.0)
                st.markdown(f"""
                <div class="metric-pill">
                    <div class="val">{conf:.0%}</div>
                    <div class="lbl">Data Confidence</div>
                </div>""", unsafe_allow_html=True)

            st.markdown("""
            <div style="margin-top:1.5rem;font-family:'IBM Plex Mono',monospace;
                        font-size:0.72rem;color:rgba(100,100,140,0.5);text-align:center;">
                Switch to <strong style="color:rgba(200,200,220,0.7);">Dashboard</strong>
                or <strong style="color:rgba(200,200,220,0.7);">Report</strong> tabs to view results.
            </div>
            """, unsafe_allow_html=True)

    if st.session_state["pipeline_running"]:
        time.sleep(1.5)
        st.rerun()


# ─────────────────────────────────────────────
#  TAB 3 — DASHBOARD
# ─────────────────────────────────────────────

def _render_dashboard():
    portfolio = _load_json("07_portfolio_construction.json")
    market    = _load_json("01_market_context.json")
    sentiment = _load_json("05_sentiment_analysis.json")

    if not portfolio and not st.session_state["pipeline_done"]:
        st.markdown("""
        <div style="text-align:center;padding:4rem 0;color:rgba(100,100,140,0.4);
                    font-family:'IBM Plex Mono',monospace;font-size:0.82rem;">
            No results yet. Run the analysis pipeline first.
        </div>
        """, unsafe_allow_html=True)
        return

    # ── Market bias banner ──────────────────────
    if market:
        bias   = market.get("market_bias", "neutral").upper()
        vix    = market.get("india_vix")
        nifty  = (market.get("nifty50") or {}).get("level")
        chg    = (market.get("nifty50") or {}).get("change_pct")
        bias_col = {"BULLISH": "#12A05C", "BEARISH": "#D93025"}.get(bias, "#C49A00")
        vix_str   = f"{vix:.1f}" if vix else "N/A"
        nifty_str = f"{nifty:,.0f}" if nifty else "N/A"
        chg_str   = f"{chg:+.2f}%" if chg else ""
        chg_col   = "#12A05C" if chg_str.startswith("+") else "#D93025"

        st.markdown(f"""
        <div style="display:flex;align-items:center;gap:2rem;
                    padding:1rem 1.5rem;background:rgba(255,255,255,0.02);
                    border:1px solid rgba(255,255,255,0.06);border-radius:4px;
                    margin-bottom:1.5rem;backdrop-filter:blur(8px);">
            <div>
                <div class="ba-label">Market Bias</div>
                <div style="font-family:'IBM Plex Mono',monospace;font-size:1rem;
                            font-weight:500;color:{bias_col};margin-top:3px;
                            text-shadow:0 0 20px {bias_col}55;">{bias}</div>
            </div>
            <div style="width:1px;height:40px;background:rgba(255,255,255,0.05);"></div>
            <div>
                <div class="ba-label">Nifty 50</div>
                <div style="font-family:'IBM Plex Mono',monospace;font-size:1rem;
                            font-weight:500;margin-top:3px;color:#F0F0F8;">
                    {nifty_str}
                    <span style="font-size:0.72rem;color:{chg_col};">{chg_str}</span>
                </div>
            </div>
            <div style="width:1px;height:40px;background:rgba(255,255,255,0.05);"></div>
            <div>
                <div class="ba-label">India VIX</div>
                <div style="font-family:'IBM Plex Mono',monospace;font-size:1rem;
                            font-weight:500;margin-top:3px;color:#F0F0F8;">{vix_str}</div>
            </div>
            <div style="width:1px;height:40px;background:rgba(255,255,255,0.05);"></div>
            <div style="flex:1;">
                <div class="ba-label">Commentary</div>
                <div style="font-family:'Plus Jakarta Sans',sans-serif;font-size:0.78rem;
                            color:rgba(180,180,210,0.6);margin-top:3px;">
                    {(market.get('macro_commentary') or '')[:150]}
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    # ── Recommendation cards ────────────────────
    st.markdown('<div class="ba-label" style="margin-bottom:1rem;">Portfolio Recommendations</div>', unsafe_allow_html=True)

    recs   = (portfolio or {}).get("portfolio", [])
    scores = (portfolio or {}).get("composite_scores", [])

    if recs:
        cols = st.columns(min(len(recs), 5))
        for i, stock in enumerate(recs[:5]):
            rec    = stock.get("recommendation", "HOLD").upper()
            score  = stock.get("composite_score", 0)
            sym    = stock.get("symbol", "")
            co     = stock.get("company", "")
            sec    = stock.get("sector", "")
            sz     = stock.get("position_size_pct", 0)
            entry  = stock.get("entry_zone", "—")
            tgt    = stock.get("target_price_12m")
            sl     = stock.get("stop_loss")
            upside = stock.get("upside_pct")

            colour  = {"BUY": "#12A05C", "HOLD": "#C49A00", "SELL": "#D93025", "AVOID": "#D93025"}.get(rec, "#C49A00")
            tag_cls = {"BUY": "tag-buy", "HOLD": "tag-hold"}.get(rec, "tag-sell")
            tgt_str    = f"₹{tgt:,.0f}" if tgt else "—"
            sl_str     = f"₹{sl:,.0f}"  if sl  else "—"
            upside_str = f"+{upside:.1f}%" if upside else ""

            with cols[i]:
                st.markdown(f"""
                <div class="rec-card">
                    <div class="accent-bar" style="background:{colour};
                         box-shadow:0 0 10px {colour}66;"></div>
                    <div class="symbol">{sym}</div>
                    <div class="company">{co}</div>
                    <div style="font-family:'IBM Plex Mono',monospace;font-size:0.62rem;
                                color:rgba(120,120,160,0.4);margin-top:2px;">{sec}</div>
                    <div class="score-badge" style="color:{colour};
                         text-shadow:0 0 20px {colour}55;">{score:.2f}</div>
                    <div style="font-family:'IBM Plex Mono',monospace;font-size:0.6rem;
                                color:rgba(120,120,160,0.4);">composite score</div>
                    <div>
                        <span class="rec-tag {tag_cls}">{rec}</span>
                        <span style="font-family:'IBM Plex Mono',monospace;font-size:0.62rem;
                                     color:rgba(120,120,160,0.4);margin-left:6px;">{sz:.0f}%</span>
                    </div>
                    <div class="price-target">
                        <div style="display:flex;justify-content:space-between;">
                            <span>Entry</span>
                            <span style="color:rgba(200,200,220,0.6);">{entry}</span>
                        </div>
                        <div style="display:flex;justify-content:space-between;margin-top:3px;">
                            <span>Target</span>
                            <span style="color:#12A05C;">{tgt_str}
                                <span style="font-size:0.6rem;">{upside_str}</span>
                            </span>
                        </div>
                        <div style="display:flex;justify-content:space-between;margin-top:3px;">
                            <span>Stop</span>
                            <span style="color:#D93025;">{sl_str}</span>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
    else:
        if scores:
            cols = st.columns(min(len(scores), 5))
            for i, s in enumerate(scores[:5]):
                rec     = s.get("recommendation", "HOLD").upper()
                colour  = {"BUY": "#12A05C", "HOLD": "#C49A00"}.get(rec, "#D93025")
                tag_cls = {"BUY": "tag-buy", "HOLD": "tag-hold"}.get(rec, "tag-sell")
                with cols[i]:
                    st.markdown(f"""
                    <div class="rec-card">
                        <div class="accent-bar" style="background:{colour};"></div>
                        <div class="symbol">{s.get('symbol','')}</div>
                        <div class="company">{s.get('company','')}</div>
                        <div class="score-badge" style="color:{colour};">{s.get('composite_score',0):.2f}</div>
                        <span class="rec-tag {tag_cls}">{rec}</span>
                    </div>
                    """, unsafe_allow_html=True)
        else:
            st.info("Portfolio data not available yet.")

    st.markdown('<div class="ba-divider"></div>', unsafe_allow_html=True)

    # ── Portfolio metrics strip ─────────────────
    pm = (portfolio or {}).get("portfolio_metrics") or {}
    if pm:
        st.markdown('<div class="ba-label" style="margin-bottom:1rem;">Portfolio Metrics</div>', unsafe_allow_html=True)
        mc1, mc2, mc3, mc4 = st.columns(4)
        metrics = [
            (pm.get("total_stocks", "—"),           "Stocks"),
            (pm.get("avg_composite_score", "—"),     "Avg Score"),
            (pm.get("portfolio_beta_estimate", "—"), "Beta"),
            ((portfolio or {}).get("macro_bias","—").upper(), "Macro Bias"),
        ]
        for col, (val, lbl) in zip([mc1, mc2, mc3, mc4], metrics):
            display_val = f"{val:.2f}" if isinstance(val, float) else str(val)
            with col:
                st.markdown(f"""
                <div class="metric-pill">
                    <div class="val">{display_val}</div>
                    <div class="lbl">{lbl}</div>
                </div>""", unsafe_allow_html=True)

    # ── Sector allocation ───────────────────────
    sector_alloc = pm.get("sector_allocation") or {}
    if sector_alloc:
        st.markdown('<div class="ba-divider"></div>', unsafe_allow_html=True)
        st.markdown('<div class="ba-label" style="margin-bottom:1rem;">Sector Allocation</div>', unsafe_allow_html=True)

        for sector, pct in sorted(sector_alloc.items(), key=lambda x: -x[1]):
            bar_width = min(pct, 100)
            st.markdown(f"""
            <div style="display:flex;align-items:center;gap:12px;margin-bottom:10px;">
                <div style="font-family:'IBM Plex Mono',monospace;font-size:0.7rem;
                            color:rgba(180,180,210,0.5);width:200px;flex-shrink:0;">{sector}</div>
                <div style="flex:1;height:3px;background:rgba(255,255,255,0.04);border-radius:2px;">
                    <div style="height:3px;width:{bar_width}%;
                                background:linear-gradient(90deg,#1400FF,rgba(20,0,255,0.3));
                                border-radius:2px;
                                box-shadow:0 0 8px rgba(20,0,255,0.3);"></div>
                </div>
                <div style="font-family:'IBM Plex Mono',monospace;font-size:0.7rem;
                            color:rgba(150,150,180,0.5);width:40px;text-align:right;">{pct:.0f}%</div>
            </div>
            """, unsafe_allow_html=True)

    # ── FII/DII flow summary ────────────────────
    fii_data = (market or {}).get("institutional_flows") or {}
    if fii_data:
        st.markdown('<div class="ba-divider"></div>', unsafe_allow_html=True)
        st.markdown('<div class="ba-label" style="margin-bottom:1rem;">Institutional Flows (10-Day)</div>', unsafe_allow_html=True)

        fc1, fc2, fc3 = st.columns(3)
        fii_net = fii_data.get("fii_net_10d_cr", 0) or 0
        dii_net = fii_data.get("dii_net_10d_cr", 0) or 0
        bias    = fii_data.get("institutional_bias", "neutral").upper()
        bias_col = {"BULLISH": "#12A05C", "BEARISH": "#D93025"}.get(bias, "#C49A00")

        for col, (val, lbl, col_override) in zip(
            [fc1, fc2, fc3],
            [
                (f"₹{fii_net:,.0f} Cr", "FII Net (10D)", "#12A05C" if fii_net > 0 else "#D93025"),
                (f"₹{dii_net:,.0f} Cr", "DII Net (10D)", "#12A05C" if dii_net > 0 else "#D93025"),
                (bias, "Institutional Bias", bias_col),
            ]
        ):
            with col:
                st.markdown(f"""
                <div class="metric-pill">
                    <div class="val" style="color:{col_override};">{val}</div>
                    <div class="lbl">{lbl}</div>
                </div>""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
#  TAB 4 — REPORT
# ─────────────────────────────────────────────

def _render_report():
    report = _load_report()

    if not report:
        st.markdown("""
        <div style="text-align:center;padding:4rem 0;color:rgba(100,100,140,0.4);
                    font-family:'IBM Plex Mono',monospace;font-size:0.82rem;">
            Report not available. Run the pipeline to generate.
        </div>
        """, unsafe_allow_html=True)
        return

    col1, col2 = st.columns([8, 2])
    with col2:
        st.download_button(
            label="↓ Download .md",
            data=report,
            file_name=f"bharatalpha_report_{datetime.now().strftime('%Y%m%d_%H%M')}.md",
            mime="text/markdown",
            use_container_width=True
        )

    st.markdown('<div class="ba-divider"></div>', unsafe_allow_html=True)

    st.markdown("""
    <style>
    .report-body h1 {
        font-family: 'Cormorant Garamond', serif !important;
        font-weight: 300 !important;
        font-size: 2.6rem !important;
        letter-spacing: -0.02em !important;
        color: #F0F0F8 !important;
        margin-bottom: 1rem !important;
    }
    .report-body h2 {
        font-family: 'IBM Plex Mono', monospace !important;
        font-size: 0.72rem !important;
        font-weight: 500 !important;
        letter-spacing: 0.14em !important;
        text-transform: uppercase !important;
        color: rgba(20,0,255,0.8) !important;
        margin-top: 2.5rem !important;
        margin-bottom: 0.8rem !important;
    }
    .report-body h3 {
        font-family: 'Cormorant Garamond', serif !important;
        font-size: 1.5rem !important;
        font-weight: 600 !important;
        color: #E8E8EC !important;
        margin-top: 1.5rem !important;
    }
    .report-body h4 {
        font-family: 'IBM Plex Mono', monospace !important;
        font-size: 0.7rem !important;
        letter-spacing: 0.1em !important;
        text-transform: uppercase !important;
        color: rgba(120,120,160,0.5) !important;
        margin-top: 1rem !important;
    }
    .report-body p {
        font-family: 'Plus Jakarta Sans', sans-serif !important;
        font-size: 0.9rem !important;
        line-height: 1.8 !important;
        color: rgba(200,200,220,0.65) !important;
        max-width: 780px !important;
    }
    .report-body table {
        font-family: 'IBM Plex Mono', monospace !important;
        font-size: 0.75rem !important;
        border-collapse: collapse !important;
        width: 100% !important;
    }
    .report-body th {
        font-size: 0.62rem !important;
        letter-spacing: 0.1em !important;
        text-transform: uppercase !important;
        color: rgba(120,120,160,0.4) !important;
        border-bottom: 1px solid rgba(255,255,255,0.05) !important;
        padding: 0.5rem 0.8rem !important;
        text-align: left !important;
    }
    .report-body td {
        padding: 0.5rem 0.8rem !important;
        border-bottom: 1px solid rgba(255,255,255,0.03) !important;
        color: rgba(180,180,210,0.6) !important;
    }
    </style>
    <div class="report-body">
    """, unsafe_allow_html=True)

    st.markdown(report)
    st.markdown("</div>", unsafe_allow_html=True)


# ─────────────────────────────────────────────
#  MAIN LAYOUT
# ─────────────────────────────────────────────

def main():
    _render_sidebar()

    tab1, tab2, tab3, tab4 = st.tabs([
        "Overview",
        "Live Pipeline",
        "Dashboard",
        "Report"
    ])

    with tab1:
        _render_landing()

    with tab2:
        _render_pipeline()

    with tab3:
        _render_dashboard()

    with tab4:
        _render_report()


if __name__ == "__main__":
    main()