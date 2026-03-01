import os
import time
import random
import logging
from typing import Optional, Callable
from pathlib import Path

from crewai import Agent, Crew, Process, Task, LLM
from crewai.project import CrewBase, agent, crew, task

from .tools import (
    authenticate_angel,
    get_angel_ltp,
    get_angel_quote,
    get_angel_historical_data,
    get_screener_fundamentals,
    get_screener_peers,
    get_nse_corporate_actions,
    get_nse_shareholding_pattern,
    get_fii_dii_flows,
    get_rss_news,
    get_bse_announcements,
    get_market_context,
    reset_data_quality,
    get_data_quality,
)
from .utils import get_config_path, get_output_path

logger = logging.getLogger("BharatAlpha.Crew")
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter(
        "%(asctime)s — %(levelname)s — %(name)s — %(message)s",
        "%Y-%m-%d %H:%M:%S"
    ))
    logger.addHandler(ch)
    logger.setLevel(logging.INFO)

# Absolute path to config/ — works regardless of process cwd
# src/crew.py → src/ → project_root/ → config/
_CONFIG_DIR = Path(__file__).parent.parent / "config"


@CrewBase
class BharatAlphaCrew():

    agents_config = str(_CONFIG_DIR / "agents.yaml")
    tasks_config  = str(_CONFIG_DIR / "tasks.yaml")

    def __init__(
        self,
        step_callback: Optional[Callable] = None,
        task_callback: Optional[Callable] = None
    ):
        self._step_callback = step_callback
        self._task_callback = task_callback

        # Ensure output directory exists
        get_output_path("").mkdir(parents=True, exist_ok=True)

        # Reset data quality tracker at the start of each pipeline run
        reset_data_quality()

    # ─────────────────────────────────────────────
    #  LLM INSTANCES
    # ─────────────────────────────────────────────

    def _haiku(self) -> LLM:
        return LLM(
            model="anthropic/claude-haiku-4-5-20251001",
            api_key=os.getenv("ANTHROPIC_API_KEY"),
            temperature=0.1,
            max_tokens=2048        # reduced to stay under rate limit
        )

    def _sonnet(self) -> LLM:
        return LLM(
            model="anthropic/claude-sonnet-4-5",
            api_key=os.getenv("ANTHROPIC_API_KEY"),
            temperature=0.2,
            max_tokens=4096        # reduced to stay under 30k TPM rate limit
        )

    # ─────────────────────────────────────────────
    #  AGENTS
    # ─────────────────────────────────────────────

    @agent
    def market_context_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["market_context_agent"],
            tools=[
                get_market_context,
                get_fii_dii_flows,
            ],
            llm=self._haiku(),
            verbose=True,
            allow_delegation=False
        )

    @agent
    def stock_screener_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["stock_screener_agent"],
            tools=[
                get_angel_ltp,
            ],
            llm=self._haiku(),
            verbose=True,
            allow_delegation=False
        )

    @agent
    def fundamental_analyst_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["fundamental_analyst_agent"],
            tools=[
                get_screener_fundamentals,
                # get_screener_peers removed — returns large HTML tables that
                # spike intra-task conversation to 50k+ tokens, causing 429s.
                # Peer benchmarking is nice-to-have; core valuation metrics
                # from get_screener_fundamentals are sufficient for scoring.
            ],
            llm=self._haiku(),
            verbose=True,
            allow_delegation=False
        )

    @agent
    def technical_analyst_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["technical_analyst_agent"],
            tools=[
                get_angel_historical_data,
                get_angel_quote,
            ],
            llm=self._haiku(),
            verbose=True,
            allow_delegation=False
        )

    @agent
    def sentiment_analyst_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["sentiment_analyst_agent"],
            tools=[
                get_rss_news,
                get_bse_announcements,
                get_nse_corporate_actions,
            ],
            llm=self._haiku(),
            verbose=True,
            allow_delegation=False
        )

    @agent
    def risk_analyst_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["risk_analyst_agent"],
            tools=[
                get_nse_shareholding_pattern,
                get_nse_corporate_actions,
            ],
            llm=self._haiku(),
            verbose=True,
            allow_delegation=False
        )

    @agent
    def portfolio_manager_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["portfolio_manager_agent"],
            tools=[
                get_angel_ltp,
            ],
            llm=self._haiku(),     # downgraded from sonnet — saves ~10k TPM
            verbose=True,
            allow_delegation=False
        )

    @agent
    def report_generator_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["report_generator_agent"],
            tools=[],
            llm=self._haiku(),
            verbose=True,
            allow_delegation=False
        )

    # ─────────────────────────────────────────────
    #  TASKS
    # ─────────────────────────────────────────────

    @task
    def analyze_market_context(self) -> Task:
        return Task(
            config=self.tasks_config["analyze_market_context"]
        )

    @task
    def screen_universe(self) -> Task:
        return Task(
            config=self.tasks_config["screen_universe"]
        )

    @task
    def analyze_fundamentals(self) -> Task:
        return Task(
            config=self.tasks_config["analyze_fundamentals"]
        )

    @task
    def analyze_technicals(self) -> Task:
        return Task(
            config=self.tasks_config["analyze_technicals"]
        )

    @task
    def assess_sentiment(self) -> Task:
        return Task(
            config=self.tasks_config["assess_sentiment"]
        )

    @task
    def evaluate_risk(self) -> Task:
        return Task(
            config=self.tasks_config["evaluate_risk"]
        )

    @task
    def construct_portfolio(self) -> Task:
        return Task(
            config=self.tasks_config["construct_portfolio"]
        )

    @task
    def generate_report(self) -> Task:
        return Task(
            config=self.tasks_config["generate_report"]
        )

    # ─────────────────────────────────────────────
    #  CREW
    # ─────────────────────────────────────────────

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
            memory=False,
            max_rpm=8,             # throttle to ~8 LLM calls/min — prevents 429s
            full_output=True,
            step_callback=self._step_callback,
            task_callback=self._task_callback
        )


# ─────────────────────────────────────────────
#  PIPELINE RUNNER
#  Called by main.py and app.py
# ─────────────────────────────────────────────

def run_pipeline(
    step_callback: Optional[Callable] = None,
    task_callback: Optional[Callable] = None
) -> dict:
    """
    Authenticates Angel One, kicks off the BharatAlpha pipeline,
    and returns the full crew result dict.

    Rate limit strategy:
    - Only report_generator uses Sonnet; all others use Haiku
    - max_tokens capped at 2048 (haiku) / 4096 (sonnet)
    - Exponential backoff retry on 429 errors (30s, 60s, 120s, 240s)
    """
    logger.info("═" * 60)
    logger.info("  BHARATALPHA PIPELINE — STARTING")
    logger.info("═" * 60)

    # Step 1: Authenticate Angel One
    logger.info("Authenticating Angel One SmartAPI...")
    auth = authenticate_angel.func()
    if auth.get("status") != "success":
        logger.error(f"Angel One auth failed: {auth.get('message')}")
        logger.warning("Continuing pipeline — price data tools will be unavailable.")

    # Step 2: Run crew with exponential backoff on rate limit errors.
    # Anthropic free tier = 30k input tokens/min. 8 agents × ~3k tokens = risk of 429.
    # Backoff: 30s → 60s → 120s → 240s (+jitter).
    MAX_RETRIES = 4
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            crew_instance = BharatAlphaCrew(
                step_callback=step_callback,
                task_callback=task_callback
            )
            logger.info(f"Starting CrewAI pipeline (attempt {attempt}/{MAX_RETRIES})...")
            result = crew_instance.crew().kickoff()

            # Success
            dq = get_data_quality()
            logger.info("═" * 60)
            logger.info("  BHARATALPHA PIPELINE — COMPLETE")
            logger.info(f"  Data Quality: {dq.summary()}")
            logger.info("═" * 60)
            return {
                "status":       "success",
                "result":       result,
                "data_quality": dq.to_dict(),
                "error":        None
            }

        except Exception as e:
            last_error = e
            err_str = str(e)
            is_rate_limit = (
                "rate_limit" in err_str
                or "429" in err_str
                or "RateLimitError" in err_str
            )
            if is_rate_limit and attempt < MAX_RETRIES:
                wait = (2 ** attempt) * 30 + random.uniform(0, 10)
                logger.warning(
                    f"Rate limit hit (attempt {attempt}/{MAX_RETRIES}). "
                    f"Waiting {wait:.0f}s before retry..."
                )
                if step_callback:
                    try:
                        step_callback(
                            f"⏳ Rate limit — waiting {wait:.0f}s "
                            f"(retry {attempt}/{MAX_RETRIES})"
                        )
                    except Exception:
                        pass
                time.sleep(wait)
            else:
                # Non-rate-limit error OR max retries exhausted
                logger.exception(f"Pipeline failed: {e}")
                dq = get_data_quality()
                return {
                    "status":       "failed",
                    "result":       None,
                    "data_quality": dq.to_dict(),
                    "error":        str(e)
                }

    # Should not reach here, but safety net
    logger.error("Pipeline exhausted all retries")
    dq = get_data_quality()
    return {
        "status":       "failed",
        "result":       None,
        "data_quality": dq.to_dict(),
        "error":        str(last_error)
    }