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
    background: #FFFFFF;
    font-family: 'Plus Jakarta Sans', sans-serif;
    color: #0C0C0E;
}

/* ── Hide Streamlit chrome ───────────────────── */
#MainMenu, footer, header { visibility: hidden; }
[data-testid="stDecoration"] { display: none; }
.stDeployButton { display: none; }

/* ── Sidebar ─────────────────────────────────── */
[data-testid="stSidebar"] {
    background: #0C0C0E !important;
    border-right: 1px solid #1a1a1e;
}
[data-testid="stSidebar"] * { color: #E8E8E8 !important; }
[data-testid="stSidebar"] .stTextInput input {
    background: #1a1a1e !important;
    border: 1px solid #2a2a2e !important;
    color: #E8E8E8 !important;
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 12px !important;
}
[data-testid="stSidebar"] .stButton button {
    background: #1400FF !important;
    color: #FFFFFF !important;
    border: none !important;
    font-family: 'Plus Jakarta Sans', sans-serif !important;
    font-weight: 600 !important;
    letter-spacing: 0.05em !important;
}
[data-testid="stSidebar"] .stButton button:hover {
    background: #0E00CC !important;
}
[data-testid="stSidebar"] hr {
    border-color: #2a2a2e !important;
}

/* ── Main content ────────────────────────────── */
.block-container {
    padding: 2rem 3rem !important;
    max-width: 1400px !important;
}

/* ── Typography ──────────────────────────────── */
.ba-display {
    font-family: 'Cormorant Garamond', serif;
    font-weight: 300;
    font-size: 3.5rem;
    line-height: 1.05;
    letter-spacing: -0.02em;
    color: #0C0C0E;
}
.ba-display span {
    color: #1400FF;
}
.ba-subtitle {
    font-family: 'Plus Jakarta Sans', sans-serif;
    font-weight: 300;
    font-size: 0.95rem;
    color: #666;
    letter-spacing: 0.02em;
}
.ba-label {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.7rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #999;
}
.ba-mono {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.85rem;
}

/* ── Section divider ─────────────────────────── */
.ba-divider {
    height: 1px;
    background: linear-gradient(90deg, #1400FF 0%, transparent 100%);
    margin: 2rem 0;
    opacity: 0.3;
}

/* ── Recommendation cards ────────────────────── */
.rec-card {
    border: 1px solid #e8e8e8;
    border-radius: 2px;
    padding: 1.5rem;
    position: relative;
    transition: box-shadow 0.2s ease;
    background: #FAFAFA;
}
.rec-card:hover {
    box-shadow: 0 4px 24px rgba(0,0,0,0.08);
}
.rec-card .accent-bar {
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    border-radius: 2px 2px 0 0;
}
.rec-card .symbol {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 1.1rem;
    font-weight: 500;
    margin-top: 0.5rem;
}
.rec-card .company {
    font-family: 'Plus Jakarta Sans', sans-serif;
    font-size: 0.78rem;
    color: #666;
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
    font-size: 0.65rem;
    font-weight: 500;
    letter-spacing: 0.12em;
    padding: 0.2rem 0.6rem;
    border-radius: 2px;
    margin-top: 0.5rem;
}
.rec-card .price-target {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.8rem;
    color: #444;
    margin-top: 0.8rem;
    padding-top: 0.8rem;
    border-top: 1px solid #e8e8e8;
}
.tag-buy   { background: #E8F7F0; color: #12A05C; }
.tag-hold  { background: #FEF9E7; color: #C49A00; }
.tag-sell  { background: #FEECEB; color: #D93025; }
.tag-avoid { background: #FEECEB; color: #D93025; }

/* ── Metrics strip ───────────────────────────── */
.metric-pill {
    background: #F5F5F5;
    border: 1px solid #E8E8E8;
    border-radius: 2px;
    padding: 1rem 1.5rem;
    text-align: center;
}
.metric-pill .val {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 1.4rem;
    font-weight: 500;
    color: #0C0C0E;
}
.metric-pill .lbl {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.65rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #999;
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
    border-bottom: 1px solid #e8e8e8;
    background: transparent;
}
.stTabs [data-baseweb="tab"] {
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 0.75rem !important;
    letter-spacing: 0.08em !important;
    text-transform: uppercase !important;
    color: #999 !important;
    padding: 0.75rem 1.5rem !important;
    border-radius: 0 !important;
    border-bottom: 2px solid transparent !important;
}
.stTabs [aria-selected="true"] {
    color: #0C0C0E !important;
    border-bottom: 2px solid #1400FF !important;
    background: transparent !important;
}

/* ── Primary button ──────────────────────────── */
.stButton > button[kind="primary"],
.stButton > button {
    background: #1400FF !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 2px !important;
    font-family: 'Plus Jakarta Sans', sans-serif !important;
    font-size: 0.85rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.04em !important;
    padding: 0.6rem 1.8rem !important;
    transition: background 0.15s !important;
}
.stButton > button:hover {
    background: #0E00CC !important;
}

/* ── Text inputs ─────────────────────────────── */
.stTextInput input, .stSelectbox select {
    border-radius: 2px !important;
    border: 1px solid #E0E0E0 !important;
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 0.85rem !important;
}
.stTextInput input:focus {
    border-color: #1400FF !important;
    box-shadow: 0 0 0 1px #1400FF !important;
}

/* ── Log viewer ──────────────────────────────── */
.log-viewer {
    background: #0C0C0E;
    border-radius: 2px;
    padding: 1rem 1.2rem;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.72rem;
    line-height: 1.7;
    color: #A8B8A8;
    max-height: 280px;
    overflow-y: auto;
}
.log-viewer .log-time { color: #555; }
.log-viewer .log-agent { color: #1400FF; }
.log-viewer .log-msg { color: #C8D8C8; }
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
    """
    Returns step/task callbacks that write into a plain Python queue.
    These closures capture `q` directly — they never touch st.session_state,
    which is inaccessible from background threads (no ScriptRunContext).
    """
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
    """
    Runs in a background thread.
    Receives the queue as a direct argument — NEVER accesses st.session_state.
    st.session_state is bound to a Streamlit ScriptRunContext which does not
    exist in background threads, causing KeyError on every access.
    """
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
    """
    Drains the log queue and updates session state.
    Called on every Streamlit rerun via st.empty() polling.
    Returns True if pipeline completed this drain cycle.
    """
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
                # Keep last 120 lines
                if len(st.session_state["agent_logs"]) > 120:
                    st.session_state["agent_logs"] = st.session_state["agent_logs"][-120:]

            elif kind == "task_done":
                # Mark next pending task as complete
                for task_key in st.session_state["task_status"]:
                    if st.session_state["task_status"][task_key] == "running":
                        st.session_state["task_status"][task_key] = "done"
                        break
                # Mark next pending task as running
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
                # Mark all tasks done
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
    """Kicks off the background pipeline thread."""
    # Reset state
    st.session_state["pipeline_running"] = True
    st.session_state["pipeline_done"]    = False
    st.session_state["pipeline_result"]  = None
    st.session_state["pipeline_error"]   = None
    st.session_state["agent_logs"]       = []
    st.session_state["task_status"]      = {t: "pending" for t in TASK_LABELS}
    st.session_state["log_queue"]        = queue.Queue()

    # Mark first task as running
    first = list(TASK_LABELS.keys())[0]
    st.session_state["task_status"][first] = "running"
    st.session_state["current_agent"] = TASK_AGENTS[first]

    # Pass the queue directly — thread must not access st.session_state
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
#  Uses components.html — immune to markdown sanitizer
# ─────────────────────────────────────────────

def _render_pipeline_tracker():
    statuses = st.session_state["task_status"]
    stages   = list(TASK_LABELS.items())

    stage_html = ""
    for i, (key, label) in enumerate(stages):
        status = statuses.get(key, "pending")
        if status == "done":
            icon   = "✓"
            cls    = "stage-done"
            dot_cls = "dot-done"
        elif status == "running":
            icon   = "◉"
            cls    = "stage-running"
            dot_cls = "dot-running"
        else:
            icon   = str(i + 1)
            cls    = "stage-pending"
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

    # Current agent log (last 8 lines)
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
        background: #FAFAFA;
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
        border-radius: 2px;
    }}
    .dot {{
        width: 26px; height: 26px;
        border-radius: 50%;
        display: flex; align-items: center; justify-content: center;
        font-family: 'IBM Plex Mono', monospace;
        font-size: 11px;
        font-weight: 500;
        flex-shrink: 0;
    }}
    .dot-done    {{ background: #E8F7F0; color: #12A05C; }}
    .dot-running {{ background: #1400FF; color: #FFFFFF; animation: pulse 1.2s ease-in-out infinite; }}
    .dot-pending {{ background: #F0F0F0; color: #999; }}
    .stage-label {{
        font-family: 'IBM Plex Mono', monospace;
        font-size: 10px;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        white-space: nowrap;
    }}
    .stage-done    .stage-label {{ color: #12A05C; }}
    .stage-running .stage-label {{ color: #1400FF; font-weight: 500; }}
    .stage-pending .stage-label {{ color: #BBB; }}
    .connector {{
        width: 20px; height: 1px;
        background: #DDD;
        flex-shrink: 0;
    }}
    @keyframes pulse {{
        0%, 100% {{ opacity: 1; box-shadow: 0 0 0 0 rgba(20,0,255,0.4); }}
        50%       {{ opacity: 0.85; box-shadow: 0 0 0 6px rgba(20,0,255,0); }}
    }}
    .log-panel {{
        background: #0C0C0E;
        border-radius: 2px;
        padding: 14px 16px;
        min-height: 140px;
        max-height: 180px;
        overflow-y: auto;
    }}
    .log-header {{
        font-family: 'IBM Plex Mono', monospace;
        font-size: 9px;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: #444;
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
    .log-line .t {{ color: #444; flex-shrink: 0; }}
    .log-line .a {{ color: #1400FF; flex-shrink: 0; max-width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .log-line .m {{ color: #8A9A8A; flex: 1; }}
    .log-line.idle .m {{ color: #555; font-style: italic; }}
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
            <div style="font-family:'Cormorant Garamond',serif;font-size:1.6rem;
                        font-weight:300;letter-spacing:-0.01em;color:#FFFFFF;">
                Bharat<span style="color:#1400FF;">Alpha</span>
            </div>
            <div style="font-family:'IBM Plex Mono',monospace;font-size:0.62rem;
                        letter-spacing:0.12em;text-transform:uppercase;
                        color:#555;margin-top:2px;">
                Indian Equity Research
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("---")

        # Pipeline status indicator
        if st.session_state["pipeline_running"]:
            st.markdown('<div class="status-running">PIPELINE RUNNING</div>', unsafe_allow_html=True)
        elif st.session_state["pipeline_done"]:
            st.markdown('<div class="status-done">✓ ANALYSIS COMPLETE</div>', unsafe_allow_html=True)
        else:
            st.markdown("""
            <div style="font-family:'IBM Plex Mono',monospace;font-size:0.7rem;
                        letter-spacing:0.08em;color:#555;">
            READY
            </div>""", unsafe_allow_html=True)

        st.markdown("---")

        # Run button
        run_disabled = st.session_state["pipeline_running"]
        if st.button(
            "▶  RUN ANALYSIS" if not run_disabled else "⟳  RUNNING...",
            disabled=run_disabled,
            use_container_width=True
        ):
            _start_pipeline()
            st.rerun()

        st.markdown("---")

        # Watchlist
        st.markdown("""
        <div style="font-family:'IBM Plex Mono',monospace;font-size:0.65rem;
                    letter-spacing:0.12em;text-transform:uppercase;
                    color:#888;margin-bottom:8px;">
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
                            color:#CCC;padding:3px 0;border-bottom:1px solid #1a1a1e;">
                    {sym}
                </div>""", unsafe_allow_html=True)
        else:
            st.markdown("""
            <div style="font-family:'IBM Plex Mono',monospace;font-size:0.7rem;
                        color:#444;font-style:italic;">
                No symbols added
            </div>""", unsafe_allow_html=True)

        st.markdown("---")

        # Env check
        keys_present = all([
            os.getenv("ANGEL_API_KEY"),
            os.getenv("ANGEL_CLIENT_ID"),
            os.getenv("ANTHROPIC_API_KEY"),
        ])
        env_colour = "#12A05C" if keys_present else "#D93025"
        env_label  = "ENV OK" if keys_present else "ENV MISSING"
        st.markdown(f"""
        <div style="font-family:'IBM Plex Mono',monospace;font-size:0.65rem;
                    letter-spacing:0.1em;color:{env_colour};">
            ● {env_label}
        </div>""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
#  TAB 1 — LANDING / CONFIG
# ─────────────────────────────────────────────

def _render_landing():
    st.markdown("""
    <div class="ba-display">
        Indian Equity<br>Research &<nbsp;<span>Intelligence</span>
    </div>
    <div class="ba-subtitle" style="margin-top:0.8rem;max-width:520px;">
        Eight specialised AI agents analyse the Nifty 500 universe —
        fundamentals, technicals, sentiment, and risk — to surface
        high-conviction investment opportunities.
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="ba-divider"></div>', unsafe_allow_html=True)

    # Pipeline overview
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("""
        <div style="padding:1.5rem;border:1px solid #E8E8E8;border-radius:2px;height:160px;">
            <div class="ba-label">Data Sources</div>
            <div style="margin-top:0.8rem;font-family:'Plus Jakarta Sans',sans-serif;
                        font-size:0.82rem;line-height:1.8;color:#444;">
                Angel One SmartAPI<br>
                Screener.in<br>
                NSE / BSE APIs<br>
                Financial RSS Feeds
            </div>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown("""
        <div style="padding:1.5rem;border:1px solid #E8E8E8;border-radius:2px;height:160px;">
            <div class="ba-label">Analysis Pipeline</div>
            <div style="margin-top:0.8rem;font-family:'Plus Jakarta Sans',sans-serif;
                        font-size:0.82rem;line-height:1.8;color:#444;">
                Macro context → Screen 500+<br>
                Fundamental deep-dive<br>
                Technical entry timing<br>
                Sentiment + Risk scoring
            </div>
        </div>
        """, unsafe_allow_html=True)
    with col3:
        st.markdown("""
        <div style="padding:1.5rem;border:1px solid #E8E8E8;border-radius:2px;height:160px;">
            <div class="ba-label">Output</div>
            <div style="margin-top:0.8rem;font-family:'Plus Jakarta Sans',sans-serif;
                        font-size:0.82rem;line-height:1.8;color:#444;">
                3–5 BUY recommendations<br>
                Position sizing<br>
                Price targets + stops<br>
                Institutional research report
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown('<div class="ba-divider"></div>', unsafe_allow_html=True)

    # .env setup instructions
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
            st.markdown(f"""
            <div style="font-family:'IBM Plex Mono',monospace;font-size:0.72rem;
                        padding:0.6rem 0.8rem;border:1px solid #E8E8E8;
                        border-radius:2px;margin-bottom:0.5rem;
                        display:flex;justify-content:space-between;align-items:center;">
                <span style="color:#444;">{key}</span>
                <span style="color:{colour};font-size:0.62rem;
                             letter-spacing:0.08em;">{status}</span>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("""
    <div style="margin-top:1rem;font-family:'IBM Plex Mono',monospace;
                font-size:0.72rem;color:#999;">
        Add credentials to <code style="background:#F5F5F5;padding:1px 5px;
        border-radius:2px;">.env</code> in the project root, then press
        <strong>RUN ANALYSIS</strong> in the sidebar.
    </div>
    """, unsafe_allow_html=True)


# ─────────────────────────────────────────────
#  TAB 2 — LIVE PIPELINE
# ─────────────────────────────────────────────

def _render_pipeline():
    if not st.session_state["pipeline_running"] and not st.session_state["pipeline_done"]:
        st.markdown("""
        <div style="text-align:center;padding:4rem 0;color:#BBB;
                    font-family:'IBM Plex Mono',monospace;font-size:0.85rem;">
            Pipeline has not been started.<br>
            <span style="font-size:0.72rem;color:#DDD;">
                Press <strong style="color:#1400FF;">RUN ANALYSIS</strong> in the sidebar.
            </span>
        </div>
        """, unsafe_allow_html=True)
        return

    st.markdown('<div class="ba-label" style="margin-bottom:1rem;">Pipeline Progress</div>', unsafe_allow_html=True)

    # Drain queue and rerender if running
    if st.session_state["pipeline_running"]:
        _drain_log_queue()

    _render_pipeline_tracker()

    # Summary metrics once done
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
                col = "#D93025" if criticals > 0 else "#0C0C0E"
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
                        font-size:0.75rem;color:#888;text-align:center;">
                Switch to <strong>Dashboard</strong> or <strong>Report</strong> tabs to view results.
            </div>
            """, unsafe_allow_html=True)

    # Auto-refresh while running
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
        <div style="text-align:center;padding:4rem 0;color:#BBB;
                    font-family:'IBM Plex Mono',monospace;font-size:0.85rem;">
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

        st.markdown(f"""
        <div style="display:flex;align-items:center;gap:2rem;
                    padding:1rem 1.5rem;background:#FAFAFA;
                    border:1px solid #E8E8E8;border-radius:2px;
                    margin-bottom:1.5rem;">
            <div>
                <div class="ba-label">Market Bias</div>
                <div style="font-family:'IBM Plex Mono',monospace;font-size:1rem;
                            font-weight:500;color:{bias_col};margin-top:2px;">{bias}</div>
            </div>
            <div style="width:1px;height:40px;background:#E8E8E8;"></div>
            <div>
                <div class="ba-label">Nifty 50</div>
                <div style="font-family:'IBM Plex Mono',monospace;font-size:1rem;
                            font-weight:500;margin-top:2px;">
                    {nifty_str}
                    <span style="font-size:0.75rem;color:{'#12A05C' if '+' in chg_str else '#D93025'};">
                        {chg_str}
                    </span>
                </div>
            </div>
            <div style="width:1px;height:40px;background:#E8E8E8;"></div>
            <div>
                <div class="ba-label">India VIX</div>
                <div style="font-family:'IBM Plex Mono',monospace;font-size:1rem;
                            font-weight:500;margin-top:2px;">{vix_str}</div>
            </div>
            <div style="width:1px;height:40px;background:#E8E8E8;"></div>
            <div>
                <div class="ba-label">Commentary</div>
                <div style="font-family:'Plus Jakarta Sans',sans-serif;font-size:0.78rem;
                            color:#555;margin-top:2px;max-width:400px;">
                    {(market.get('macro_commentary') or '')[:150]}
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    # ── Recommendation cards ────────────────────
    st.markdown('<div class="ba-label" style="margin-bottom:1rem;">Portfolio Recommendations</div>', unsafe_allow_html=True)

    recs = (portfolio or {}).get("portfolio", [])
    scores = (portfolio or {}).get("composite_scores", [])

    if recs:
        cols = st.columns(min(len(recs), 5))
        for i, stock in enumerate(recs[:5]):
            rec   = stock.get("recommendation", "HOLD").upper()
            score = stock.get("composite_score", 0)
            sym   = stock.get("symbol", "")
            co    = stock.get("company", "")
            sec   = stock.get("sector", "")
            sz    = stock.get("position_size_pct", 0)
            entry = stock.get("entry_zone", "—")
            tgt   = stock.get("target_price_12m")
            sl    = stock.get("stop_loss")
            upside = stock.get("upside_pct")

            colour = {"BUY": "#12A05C", "HOLD": "#C49A00", "SELL": "#D93025", "AVOID": "#D93025"}.get(rec, "#C49A00")
            tag_cls = {"BUY": "tag-buy", "HOLD": "tag-hold"}.get(rec, "tag-sell")
            tgt_str  = f"₹{tgt:,.0f}" if tgt else "—"
            sl_str   = f"₹{sl:,.0f}"  if sl  else "—"
            upside_str = f"+{upside:.1f}%" if upside else ""

            with cols[i]:
                st.markdown(f"""
                <div class="rec-card">
                    <div class="accent-bar" style="background:{colour};"></div>
                    <div class="symbol">{sym}</div>
                    <div class="company">{co}</div>
                    <div style="font-family:'IBM Plex Mono',monospace;font-size:0.65rem;
                                color:#BBB;margin-top:2px;">{sec}</div>
                    <div class="score-badge" style="color:{colour};">{score:.2f}</div>
                    <div style="font-family:'IBM Plex Mono',monospace;font-size:0.62rem;
                                color:#999;">composite score</div>
                    <div>
                        <span class="rec-tag {tag_cls}">{rec}</span>
                        <span style="font-family:'IBM Plex Mono',monospace;font-size:0.65rem;
                                     color:#999;margin-left:6px;">{sz:.0f}%</span>
                    </div>
                    <div class="price-target">
                        <div style="display:flex;justify-content:space-between;">
                            <span>Entry</span><span style="color:#444;">{entry}</span>
                        </div>
                        <div style="display:flex;justify-content:space-between;margin-top:3px;">
                            <span>Target</span>
                            <span style="color:#12A05C;">{tgt_str}
                                <span style="font-size:0.62rem;">{upside_str}</span>
                            </span>
                        </div>
                        <div style="display:flex;justify-content:space-between;margin-top:3px;">
                            <span>Stop</span><span style="color:#D93025;">{sl_str}</span>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
    else:
        # Show HOLD/AVOID cards from composite_scores if no BUY portfolio
        if scores:
            cols = st.columns(min(len(scores), 5))
            for i, s in enumerate(scores[:5]):
                rec    = s.get("recommendation", "HOLD").upper()
                colour = {"BUY": "#12A05C", "HOLD": "#C49A00"}.get(rec, "#D93025")
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
            <div style="display:flex;align-items:center;gap:12px;margin-bottom:8px;">
                <div style="font-family:'IBM Plex Mono',monospace;font-size:0.72rem;
                            color:#444;width:200px;flex-shrink:0;">{sector}</div>
                <div style="flex:1;height:4px;background:#F0F0F0;border-radius:2px;">
                    <div style="height:4px;width:{bar_width}%;background:#1400FF;
                                border-radius:2px;opacity:0.7;"></div>
                </div>
                <div style="font-family:'IBM Plex Mono',monospace;font-size:0.72rem;
                            color:#666;width:40px;text-align:right;">{pct:.0f}%</div>
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
        <div style="text-align:center;padding:4rem 0;color:#BBB;
                    font-family:'IBM Plex Mono',monospace;font-size:0.85rem;">
            Report not available. Run the pipeline to generate.
        </div>
        """, unsafe_allow_html=True)
        return

    # Download button
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

    # Render markdown with custom typography wrapper
    st.markdown("""
    <style>
    .report-body h1 {
        font-family: 'Cormorant Garamond', serif !important;
        font-weight: 300 !important;
        font-size: 2.4rem !important;
        letter-spacing: -0.02em !important;
        color: #0C0C0E !important;
        margin-bottom: 1rem !important;
    }
    .report-body h2 {
        font-family: 'Plus Jakarta Sans', sans-serif !important;
        font-size: 1rem !important;
        font-weight: 600 !important;
        letter-spacing: 0.06em !important;
        text-transform: uppercase !important;
        color: #1400FF !important;
        margin-top: 2rem !important;
        margin-bottom: 0.8rem !important;
    }
    .report-body h3 {
        font-family: 'Cormorant Garamond', serif !important;
        font-size: 1.4rem !important;
        font-weight: 600 !important;
        color: #0C0C0E !important;
        margin-top: 1.5rem !important;
    }
    .report-body h4 {
        font-family: 'IBM Plex Mono', monospace !important;
        font-size: 0.78rem !important;
        letter-spacing: 0.08em !important;
        text-transform: uppercase !important;
        color: #888 !important;
        margin-top: 1rem !important;
    }
    .report-body p {
        font-family: 'Plus Jakarta Sans', sans-serif !important;
        font-size: 0.9rem !important;
        line-height: 1.75 !important;
        color: #333 !important;
        max-width: 780px !important;
    }
    .report-body table {
        font-family: 'IBM Plex Mono', monospace !important;
        font-size: 0.78rem !important;
        border-collapse: collapse !important;
        width: 100% !important;
    }
    .report-body th {
        font-size: 0.65rem !important;
        letter-spacing: 0.1em !important;
        text-transform: uppercase !important;
        color: #999 !important;
        border-bottom: 1px solid #E8E8E8 !important;
        padding: 0.5rem 0.8rem !important;
        text-align: left !important;
    }
    .report-body td {
        padding: 0.5rem 0.8rem !important;
        border-bottom: 1px solid #F5F5F5 !important;
        color: #444 !important;
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