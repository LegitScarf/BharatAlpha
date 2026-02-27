"""
BharatAlpha — src/tools.py
==========================
All 12 CrewAI tools across 5 data sources:
  1. Angel One SmartAPI     — real-time prices, OHLCV, authentication
  2. Screener.in            — fundamentals, financials, peer comparison
  3. NSE/BSE endpoints      — corporate actions, shareholding, FII/DII
  4. RSS + BSE News         — news aggregation, corporate announcements
  5. NSE Market Context     — macro data, sector performance

Defensive pattern: every API call goes through safe_parse_response()
and is_api_success() from utils.py before any .get() is called.
Data quality issues are logged to a shared DataQualityTracker instance.
"""

import os
import json
import time
import threading
import re
import feedparser
import pyotp
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup

import requests
from crewai.tools import tool

# Suppress logzero file handler (SmartApi side effect)
import logzero as _lz
_lz.logfile = lambda *args, **kwargs: None

from SmartApi import SmartConnect

from .utils import (
    get_logger,
    safe_parse_response,
    is_api_success,
    resolve_symbol,
    canonical_symbol,
    iso_ist,
    now_ist,
    DataQualityTracker,
)

logger = get_logger("BharatAlpha.Tools")

# ─────────────────────────────────────────────
#  SHARED STATE
# ─────────────────────────────────────────────

_smart_api: Optional[SmartConnect] = None
_auth_token: Optional[str]         = None
_feed_token: Optional[str]         = None
_refresh_token: Optional[str]      = None
_auth_lock = threading.Lock()

# Shared data quality tracker for the current pipeline run
_dq = DataQualityTracker()


def get_data_quality() -> DataQualityTracker:
    """Returns the shared DataQualityTracker for the current run."""
    return _dq


def reset_data_quality() -> None:
    """Resets the tracker at the start of each new pipeline run."""
    global _dq
    _dq = DataQualityTracker()


# ─────────────────────────────────────────────
#  NSE SESSION HEADERS
#  NSE requires browser-like headers + a session
#  cookie obtained from the home page first.
# ─────────────────────────────────────────────

_nse_session: Optional[requests.Session] = None
_nse_session_time: float = 0.0
_NSE_SESSION_TTL = 300   # seconds


def _get_nse_session() -> requests.Session:
    """
    Returns a requests Session pre-loaded with NSE cookies.
    Refreshes the session if it has expired.
    """
    global _nse_session, _nse_session_time

    if _nse_session and (time.time() - _nse_session_time) < _NSE_SESSION_TTL:
        return _nse_session

    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept":          "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer":         "https://www.nseindia.com/",
        "Connection":      "keep-alive",
    })

    try:
        # Seed cookies by hitting the NSE home page first
        session.get("https://www.nseindia.com", timeout=10)
        session.get("https://www.nseindia.com/market-data/live-equity-market", timeout=10)
        _nse_session = session
        _nse_session_time = time.time()
        logger.info("NSE session initialised successfully")
    except Exception as e:
        logger.warning(f"NSE session init failed: {e} — will retry on next call")

    return session


# ─────────────────────────────────────────────
#  TOOL 1 — ANGEL ONE AUTHENTICATION
# ─────────────────────────────────────────────

@tool("Authenticate Angel One")
def authenticate_angel() -> Dict[str, Any]:
    """
    Authenticates with Angel One SmartAPI using credentials from .env.
    Must be called before any other Angel One tool.
    Returns status, message, and timestamp.
    """
    global _smart_api, _auth_token, _feed_token, _refresh_token

    with _auth_lock:
        try:
            api_key     = os.getenv("ANGEL_API_KEY")
            client_id   = os.getenv("ANGEL_CLIENT_ID")
            mpin        = os.getenv("ANGEL_MPIN")
            totp_secret = os.getenv("ANGEL_TOTP_SECRET")

            if not all([api_key, client_id, mpin, totp_secret]):
                _dq.add_critical("angel_auth", "Missing Angel One credentials in .env")
                return {
                    "status":  "failed",
                    "error":   "missing_credentials",
                    "message": "Set ANGEL_API_KEY, ANGEL_CLIENT_ID, ANGEL_MPIN, ANGEL_TOTP_SECRET in .env"
                }

            totp = pyotp.TOTP(totp_secret).now()
            _smart_api = SmartConnect(api_key=api_key)

            session_data = safe_parse_response(
                _smart_api.generateSession(client_id, mpin, totp)
            )

            if session_data and is_api_success(session_data):
                data = session_data.get("data") or {}
                if isinstance(data, str):
                    data = {}

                _auth_token   = data.get("jwtToken")
                _feed_token   = data.get("feedToken")
                _refresh_token = data.get("refreshToken")

                if not _auth_token:
                    _dq.add_critical("angel_auth", "Session created but jwtToken missing")
                    return {
                        "status":  "failed",
                        "error":   "missing_jwt",
                        "message": "jwtToken empty — verify credentials"
                    }

                logger.info("Angel One authentication successful")
                return {
                    "status":    "success",
                    "message":   "Authenticated with Angel One",
                    "timestamp": iso_ist()
                }

            msg = (session_data or {}).get("message", "Unknown auth error")
            _dq.add_critical("angel_auth", f"Auth failed: {msg}")
            return {"status": "failed", "error": "auth_failed", "message": str(msg)}

        except Exception as e:
            _dq.add_critical("angel_auth", f"Auth exception: {e}")
            logger.exception(f"Angel auth exception: {e}")
            return {"status": "failed", "error": "exception", "message": str(e)}


def _ensure_authenticated() -> bool:
    """
    Ensures Angel One is authenticated.
    Returns True if ready, False if authentication failed.
    """
    global _smart_api, _auth_token
    if _smart_api and _auth_token:
        return True
    result = authenticate_angel.func()
    return result.get("status") == "success"


# ─────────────────────────────────────────────
#  TOOL 2 — ANGEL ONE LTP
# ─────────────────────────────────────────────

@tool("Get Stock LTP from Angel One")
def get_angel_ltp(symbol: str, exchange: str = "NSE") -> Dict[str, Any]:
    """
    Fetches the Last Traded Price (LTP) for any NSE/BSE listed stock.

    Args:
        symbol:   NSE ticker symbol e.g. 'RELIANCE', 'TCS', 'INFY'
        exchange: 'NSE' or 'BSE' (default: 'NSE')

    Returns:
        Dict with status, symbol, ltp, exchange, timestamp.

    Example:
        get_angel_ltp('RELIANCE')
        get_angel_ltp('HDFCBANK', 'NSE')
    """
    if not _ensure_authenticated():
        return {"status": "failed", "error": "auth_failed", "symbol": symbol}

    symbol = resolve_symbol(canonical_symbol(symbol), "angel")

    try:
        # Fetch instrument token from Angel One symbol search
        search_resp = safe_parse_response(
            _smart_api.searchScrip(exchange, symbol)
        )

        token = None
        if search_resp and is_api_success(search_resp):
            scrips = search_resp.get("data") or []
            for scrip in scrips:
                if scrip.get("tradingsymbol") == symbol:
                    token = scrip.get("symboltoken")
                    break

        if not token:
            _dq.add_warning("angel_ltp", f"Token not found for {symbol}, trying direct fetch")
            # Fallback: try without token (some symbols work with just name)
            return {
                "status":  "failed",
                "error":   "token_not_found",
                "symbol":  symbol,
                "message": f"Could not find instrument token for {symbol}"
            }

        ltp_data = safe_parse_response(
            _smart_api.ltpData(exchange, symbol, token)
        )

        if ltp_data and is_api_success(ltp_data):
            data = ltp_data.get("data") or {}
            if isinstance(data, str):
                data = {}
            return {
                "status":    "success",
                "symbol":    symbol,
                "exchange":  exchange,
                "ltp":       float(data.get("ltp", 0)),
                "token":     token,
                "timestamp": iso_ist()
            }

        msg = (ltp_data or {}).get("message", "LTP fetch failed")
        _dq.add_warning("angel_ltp", f"LTP failed for {symbol}: {msg}")
        return {"status": "failed", "error": "api_error", "message": str(msg), "symbol": symbol}

    except Exception as e:
        logger.exception(f"LTP exception for {symbol}: {e}")
        _dq.add_warning("angel_ltp", f"Exception for {symbol}: {e}")
        return {"status": "failed", "error": "exception", "message": str(e), "symbol": symbol}


# ─────────────────────────────────────────────
#  TOOL 3 — ANGEL ONE FULL QUOTE
# ─────────────────────────────────────────────

@tool("Get Full OHLC Quote from Angel One")
def get_angel_quote(symbol: str, exchange: str = "NSE") -> Dict[str, Any]:
    """
    Fetches full OHLC quote including open, high, low, close,
    volume, 52-week high/low for any NSE/BSE listed stock.

    Args:
        symbol:   NSE ticker symbol e.g. 'RELIANCE', 'TCS'
        exchange: 'NSE' or 'BSE' (default: 'NSE')

    Returns:
        Dict with open, high, low, ltp, close, volume, 52w_high, 52w_low.

    Example:
        get_angel_quote('TCS')
    """
    if not _ensure_authenticated():
        return {"status": "failed", "error": "auth_failed", "symbol": symbol}

    symbol = resolve_symbol(canonical_symbol(symbol), "angel")

    try:
        search_resp = safe_parse_response(_smart_api.searchScrip(exchange, symbol))
        token = None
        if search_resp and is_api_success(search_resp):
            for scrip in (search_resp.get("data") or []):
                if scrip.get("tradingsymbol") == symbol:
                    token = scrip.get("symboltoken")
                    break

        if not token:
            return {"status": "failed", "error": "token_not_found", "symbol": symbol}

        quote_data = safe_parse_response(
            _smart_api.getMarketData(
                mode="FULL",
                exchangeTokens={exchange: [token]}
            )
        )

        if quote_data and is_api_success(quote_data):
            fetched = (quote_data.get("data") or {}).get("fetched", [])
            if fetched:
                q = fetched[0]
                return {
                    "status":    "success",
                    "symbol":    symbol,
                    "exchange":  exchange,
                    "open":      float(q.get("open", 0)),
                    "high":      float(q.get("high", 0)),
                    "low":       float(q.get("low", 0)),
                    "ltp":       float(q.get("ltp", 0)),
                    "close":     float(q.get("close", 0)),
                    "volume":    int(q.get("tradedVolume", 0)),
                    "52w_high":  float(q.get("fiftyTwoWeekHighPrice", 0)),
                    "52w_low":   float(q.get("fiftyTwoWeekLowPrice", 0)),
                    "timestamp": iso_ist()
                }

        msg = (quote_data or {}).get("message", "Quote fetch failed")
        _dq.add_warning("angel_quote", f"Quote failed for {symbol}: {msg}")
        return {"status": "failed", "error": "no_data", "symbol": symbol}

    except Exception as e:
        logger.exception(f"Quote exception for {symbol}: {e}")
        _dq.add_warning("angel_quote", f"Exception for {symbol}: {e}")
        return {"status": "failed", "error": "exception", "message": str(e), "symbol": symbol}


# ─────────────────────────────────────────────
#  TOOL 4 — ANGEL ONE HISTORICAL DATA
# ─────────────────────────────────────────────

@tool("Get Historical OHLCV from Angel One")
def get_angel_historical_data(
    symbol:   str,
    days:     int = 365,
    interval: str = "ONE_DAY"
) -> Dict[str, Any]:
    """
    Fetches historical OHLCV candle data for any NSE listed stock.

    Args:
        symbol:   NSE ticker symbol e.g. 'RELIANCE', 'INFY'
        days:     Number of calendar days to look back (default: 365)
        interval: Candle interval — 'ONE_DAY', 'ONE_WEEK', 'ONE_MONTH',
                  'FIFTEEN_MINUTE', 'ONE_HOUR' (default: 'ONE_DAY')

    Returns:
        Dict with status, symbol, data (list of OHLCV dicts), count.

    Example:
        get_angel_historical_data('TCS', days=180)
        get_angel_historical_data('RELIANCE', days=30, interval='ONE_HOUR')
    """
    if not _ensure_authenticated():
        return {"status": "failed", "error": "auth_failed", "symbol": symbol}

    symbol = resolve_symbol(canonical_symbol(symbol), "angel")

    try:
        search_resp = safe_parse_response(_smart_api.searchScrip("NSE", symbol))
        token = None
        if search_resp and is_api_success(search_resp):
            for scrip in (search_resp.get("data") or []):
                if scrip.get("tradingsymbol") == symbol:
                    token = scrip.get("symboltoken")
                    break

        if not token:
            return {"status": "failed", "error": "token_not_found", "symbol": symbol}

        now       = now_ist()
        from_date = (now - timedelta(days=days)).strftime("%Y-%m-%d 09:15")
        to_date   = now.strftime("%Y-%m-%d %H:%M")

        hist_data = safe_parse_response(
            _smart_api.getCandleData({
                "exchange":    "NSE",
                "symboltoken": token,
                "interval":    interval,
                "fromdate":    from_date,
                "todate":      to_date
            })
        )

        if hist_data and is_api_success(hist_data):
            candles = hist_data.get("data") or []
            ohlcv = [
                {
                    "date":   c[0],
                    "open":   float(c[1]),
                    "high":   float(c[2]),
                    "low":    float(c[3]),
                    "close":  float(c[4]),
                    "volume": int(c[5])
                }
                for c in candles if len(c) >= 6
            ]
            return {
                "status":   "success",
                "symbol":   symbol,
                "interval": interval,
                "days":     days,
                "count":    len(ohlcv),
                "data":     ohlcv
            }

        msg = (hist_data or {}).get("message", "Historical data fetch failed")
        _dq.add_warning("angel_historical", f"Historical failed for {symbol}: {msg}")
        return {"status": "failed", "error": "api_error", "message": str(msg), "symbol": symbol}

    except Exception as e:
        logger.exception(f"Historical exception for {symbol}: {e}")
        _dq.add_warning("angel_historical", f"Exception for {symbol}: {e}")
        return {"status": "failed", "error": "exception", "message": str(e), "symbol": symbol}


# ─────────────────────────────────────────────
#  TOOL 5 — SCREENER.IN FUNDAMENTALS
# ─────────────────────────────────────────────

@tool("Get Fundamentals from Screener.in")
def get_screener_fundamentals(symbol: str) -> Dict[str, Any]:
    """
    Scrapes fundamental data from Screener.in for any NSE listed stock.
    Returns P/E, P/B, EPS, ROE, ROCE, debt/equity, sales growth,
    profit growth, promoter holding, and 10-year financial summary.

    Args:
        symbol: NSE ticker symbol e.g. 'RELIANCE', 'TCS', 'INFY'

    Returns:
        Dict with valuation ratios, growth metrics, and financial health data.

    Example:
        get_screener_fundamentals('HDFCBANK')
        get_screener_fundamentals('WIPRO')
    """
    symbol = resolve_symbol(canonical_symbol(symbol), "screener")
    url    = f"https://www.screener.in/company/{symbol}/consolidated/"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Referer":         "https://www.screener.in/",
    }

    try:
        resp = requests.get(url, headers=headers, timeout=15)

        # Try standalone if consolidated not available
        if resp.status_code == 404:
            url  = f"https://www.screener.in/company/{symbol}/"
            resp = requests.get(url, headers=headers, timeout=15)

        if resp.status_code != 200:
            _dq.add_warning("screener", f"Screener returned {resp.status_code} for {symbol}")
            return {
                "status":  "failed",
                "error":   f"http_{resp.status_code}",
                "symbol":  symbol,
                "message": f"Screener.in returned status {resp.status_code}"
            }

        soup = BeautifulSoup(resp.text, "lxml")

        def extract_ratio(label: str) -> Optional[str]:
            """Finds a ratio value by its label in the Screener.in page."""
            for li in soup.find_all("li"):
                text = li.get_text(" ", strip=True)
                if label.lower() in text.lower():
                    # Extract number after the label
                    match = re.search(r"[\d,]+\.?\d*", text.split(label)[-1])
                    if match:
                        return match.group().replace(",", "")
            return None

        def safe_float(val: Optional[str]) -> Optional[float]:
            try:
                return float(val) if val else None
            except (ValueError, TypeError):
                return None

        # Extract key ratios from the top ratios section
        ratios_section = soup.find("section", id="top-ratios")
        ratios = {}
        if ratios_section:
            for li in ratios_section.find_all("li"):
                name_tag  = li.find("span", class_="name")
                value_tag = li.find("span", class_="number")
                if name_tag and value_tag:
                    key = name_tag.get_text(strip=True).lower().replace(" ", "_").replace("/", "_")
                    val = value_tag.get_text(strip=True).replace(",", "").replace("%", "").strip()
                    ratios[key] = val

        # Extract company name and sector
        company_name = ""
        name_tag = soup.find("h1", class_="company-name")
        if name_tag:
            company_name = name_tag.get_text(strip=True)

        # Extract about/sector
        sector = ""
        about  = soup.find("div", class_="company-profile")
        if about:
            links = about.find_all("a")
            for link in links:
                if "/screen/stock/" in link.get("href", ""):
                    sector = link.get_text(strip=True)
                    break

        # Extract quarterly results table header dates
        quarterly_dates = []
        quarterly_section = soup.find("section", id="quarters")
        if quarterly_section:
            header_row = quarterly_section.find("tr")
            if header_row:
                quarterly_dates = [
                    th.get_text(strip=True)
                    for th in header_row.find_all("th")[1:]
                ][:8]

        # Build structured output
        result = {
            "status":           "success",
            "symbol":           symbol,
            "company_name":     company_name,
            "sector":           sector,
            "source":           "screener.in",
            "url":              url,
            "timestamp":        iso_ist(),
            "valuation": {
                "market_cap_cr":  safe_float(ratios.get("market_cap")),
                "pe_ratio":       safe_float(ratios.get("stock_p_e") or ratios.get("p_e")),
                "pb_ratio":       safe_float(ratios.get("price_to_book_value") or ratios.get("p_b")),
                "ev_ebitda":      safe_float(ratios.get("ev___ebitda") or ratios.get("ev_ebitda")),
                "dividend_yield": safe_float(ratios.get("dividend_yield")),
            },
            "profitability": {
                "roe":            safe_float(ratios.get("return_on_equity")),
                "roce":           safe_float(ratios.get("roce") or ratios.get("return_on_ce")),
                "face_value":     safe_float(ratios.get("face_value")),
            },
            "financial_health": {
                "debt_to_equity": safe_float(ratios.get("debt___equity")),
                "current_ratio":  safe_float(ratios.get("current_ratio")),
                "interest_coverage": safe_float(ratios.get("interest_coverage_ratio")),
            },
            "per_share": {
                "eps":            safe_float(ratios.get("eps_in_rs") or ratios.get("eps")),
                "book_value":     safe_float(ratios.get("book_value")),
            },
            "raw_ratios":       ratios,
            "quarterly_periods": quarterly_dates,
        }

        logger.info(f"Screener.in fundamentals fetched for {symbol}")
        return result

    except requests.exceptions.Timeout:
        _dq.add_warning("screener", f"Timeout fetching {symbol}")
        return {"status": "failed", "error": "timeout", "symbol": symbol}
    except Exception as e:
        logger.exception(f"Screener exception for {symbol}: {e}")
        _dq.add_warning("screener", f"Exception for {symbol}: {e}")
        return {"status": "failed", "error": "exception", "message": str(e), "symbol": symbol}


# ─────────────────────────────────────────────
#  TOOL 6 — SCREENER.IN PEER COMPARISON
# ─────────────────────────────────────────────

@tool("Get Peer Comparison from Screener.in")
def get_screener_peers(symbol: str) -> Dict[str, Any]:
    """
    Fetches peer comparison data from Screener.in.
    Returns a table of competitor stocks with key ratios for sector benchmarking.

    Args:
        symbol: NSE ticker symbol e.g. 'RELIANCE', 'TCS'

    Returns:
        Dict with list of peer companies and their valuation metrics.

    Example:
        get_screener_peers('INFY')
    """
    symbol = resolve_symbol(canonical_symbol(symbol), "screener")
    url    = f"https://www.screener.in/company/{symbol}/consolidated/"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.screener.in/",
    }

    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            return {"status": "failed", "error": f"http_{resp.status_code}", "symbol": symbol}

        soup  = BeautifulSoup(resp.text, "lxml")
        peers = []

        # Find peers section
        peers_section = soup.find("section", id="peers")
        if not peers_section:
            return {"status": "failed", "error": "peers_section_not_found", "symbol": symbol}

        table = peers_section.find("table")
        if not table:
            return {"status": "failed", "error": "peers_table_not_found", "symbol": symbol}

        # Parse header
        headers_row = table.find("thead")
        col_names   = []
        if headers_row:
            col_names = [
                th.get_text(strip=True)
                for th in headers_row.find_all("th")
            ]

        # Parse rows
        tbody = table.find("tbody")
        if tbody:
            for row in tbody.find_all("tr"):
                cells  = row.find_all("td")
                values = [c.get_text(strip=True) for c in cells]
                if values and len(values) >= 3:
                    peer = {}
                    for i, col in enumerate(col_names):
                        if i < len(values):
                            peer[col] = values[i]
                    peers.append(peer)

        return {
            "status":      "success",
            "symbol":      symbol,
            "peer_count":  len(peers),
            "columns":     col_names,
            "peers":       peers,
            "source":      "screener.in",
            "timestamp":   iso_ist()
        }

    except Exception as e:
        logger.exception(f"Screener peers exception for {symbol}: {e}")
        _dq.add_warning("screener_peers", f"Exception for {symbol}: {e}")
        return {"status": "failed", "error": "exception", "message": str(e), "symbol": symbol}


# ─────────────────────────────────────────────
#  TOOL 7 — NSE CORPORATE ACTIONS
# ─────────────────────────────────────────────

@tool("Get Corporate Actions from NSE")
def get_nse_corporate_actions(symbol: str) -> Dict[str, Any]:
    """
    Fetches upcoming and recent corporate actions for a stock from NSE.
    Includes dividends, bonus issues, stock splits, rights issues, AGMs.

    Args:
        symbol: NSE ticker symbol e.g. 'RELIANCE', 'HDFCBANK'

    Returns:
        Dict with list of corporate actions with dates and details.

    Example:
        get_nse_corporate_actions('WIPRO')
    """
    symbol  = resolve_symbol(canonical_symbol(symbol), "nse")
    session = _get_nse_session()
    url     = (
        f"https://www.nseindia.com/api/corporates-corporateActions"
        f"?index=equities&symbol={symbol}"
    )

    try:
        resp = session.get(url, timeout=15)

        if resp.status_code == 401 or resp.status_code == 403:
            # Session expired — reinit and retry once
            global _nse_session, _nse_session_time
            _nse_session = None
            _nse_session_time = 0.0
            session = _get_nse_session()
            resp    = session.get(url, timeout=15)

        if resp.status_code != 200:
            _dq.add_warning("nse_corporate", f"NSE returned {resp.status_code} for {symbol}")
            return {
                "status":  "failed",
                "error":   f"http_{resp.status_code}",
                "symbol":  symbol
            }

        data    = resp.json()
        actions = []

        for item in (data if isinstance(data, list) else []):
            actions.append({
                "symbol":       item.get("symbol"),
                "company":      item.get("comp"),
                "action":       item.get("subject"),
                "ex_date":      item.get("exDate"),
                "record_date":  item.get("recDate"),
                "bc_start":     item.get("bcStartDate"),
                "bc_end":       item.get("bcEndDate"),
                "series":       item.get("series"),
            })

        return {
            "status":     "success",
            "symbol":     symbol,
            "actions":    actions,
            "count":      len(actions),
            "source":     "nseindia.com",
            "timestamp":  iso_ist()
        }

    except Exception as e:
        logger.exception(f"NSE corporate actions exception for {symbol}: {e}")
        _dq.add_warning("nse_corporate", f"Exception for {symbol}: {e}")
        return {"status": "failed", "error": "exception", "message": str(e), "symbol": symbol}


# ─────────────────────────────────────────────
#  TOOL 8 — NSE SHAREHOLDING PATTERN
# ─────────────────────────────────────────────

@tool("Get Shareholding Pattern from NSE")
def get_nse_shareholding_pattern(symbol: str) -> Dict[str, Any]:
    """
    Fetches the latest shareholding pattern for a stock from NSE.
    Returns promoter holding %, FII %, DII %, public %, and pledge %.
    Critical for detecting promoter pledge risk — a key India-specific signal.

    Args:
        symbol: NSE ticker symbol e.g. 'RELIANCE', 'TATAMOTORS'

    Returns:
        Dict with shareholding breakdown and pledge percentage.

    Example:
        get_nse_shareholding_pattern('ADANIENT')
    """
    symbol  = resolve_symbol(canonical_symbol(symbol), "nse")
    session = _get_nse_session()
    url     = (
        f"https://www.nseindia.com/api/corporate-share-holdings-master"
        f"?symbol={symbol}&industry=_ALL_&startDate=&endDate="
    )

    try:
        resp = session.get(url, timeout=15)

        if resp.status_code != 200:
            _dq.add_warning("nse_shareholding", f"NSE returned {resp.status_code} for {symbol}")
            return {"status": "failed", "error": f"http_{resp.status_code}", "symbol": symbol}

        data = resp.json()

        if not data:
            return {"status": "failed", "error": "no_data", "symbol": symbol}

        # Latest quarter is first entry
        latest = data[0] if isinstance(data, list) else data

        result = {
            "status":          "success",
            "symbol":          symbol,
            "quarter":         latest.get("date"),
            "promoter_pct":    latest.get("promoterAndPromoterGroupTotal"),
            "fii_pct":         latest.get("foreignPortfolioInvestors"),
            "dii_pct":         latest.get("mutualFunds"),
            "public_pct":      latest.get("publicTotal"),
            "pledge_pct":      latest.get("promoterPledgedPct"),
            "total_shares":    latest.get("totalNoOfShares"),
            "source":          "nseindia.com",
            "timestamp":       iso_ist(),
            "risk_flag": (
                "HIGH_PLEDGE"
                if latest.get("promoterPledgedPct") and
                   float(latest.get("promoterPledgedPct", 0)) > 20
                else None
            )
        }

        if result["risk_flag"] == "HIGH_PLEDGE":
            _dq.add_warning(
                "shareholding",
                f"{symbol} promoter pledge is {result['pledge_pct']}% — HIGH RISK"
            )

        return result

    except Exception as e:
        logger.exception(f"NSE shareholding exception for {symbol}: {e}")
        _dq.add_warning("nse_shareholding", f"Exception for {symbol}: {e}")
        return {"status": "failed", "error": "exception", "message": str(e), "symbol": symbol}


# ─────────────────────────────────────────────
#  TOOL 9 — FII/DII FLOWS
# ─────────────────────────────────────────────

@tool("Get FII and DII Flows from NSE")
def get_fii_dii_flows(days: int = 10) -> Dict[str, Any]:
    """
    Fetches recent FII (Foreign Institutional Investor) and
    DII (Domestic Institutional Investor) net buy/sell activity from NSE.
    This is a critical macro signal for Indian equity direction.

    Args:
        days: Number of recent trading days to fetch (default: 10)

    Returns:
        Dict with daily FII/DII net values and aggregate sentiment.

    Example:
        get_fii_dii_flows()
        get_fii_dii_flows(days=20)
    """
    session = _get_nse_session()
    url     = "https://www.nseindia.com/api/fiidiiTradeReact"

    try:
        resp = session.get(url, timeout=15)

        if resp.status_code != 200:
            _dq.add_warning("fii_dii", f"NSE FII/DII endpoint returned {resp.status_code}")
            return {"status": "failed", "error": f"http_{resp.status_code}"}

        raw   = resp.json()
        flows = []

        for entry in (raw if isinstance(raw, list) else [])[:days]:
            try:
                fii_net = float(str(entry.get("fiinet", "0")).replace(",", "") or 0)
                dii_net = float(str(entry.get("diinet", "0")).replace(",", "") or 0)
                flows.append({
                    "date":        entry.get("date"),
                    "fii_buy":     entry.get("fiibuy"),
                    "fii_sell":    entry.get("fiisell"),
                    "fii_net":     fii_net,
                    "dii_buy":     entry.get("diibuy"),
                    "dii_sell":    entry.get("diisell"),
                    "dii_net":     dii_net,
                    "combined_net": round(fii_net + dii_net, 2)
                })
            except (ValueError, TypeError):
                continue

        # Aggregate sentiment
        total_fii = sum(f["fii_net"] for f in flows)
        total_dii = sum(f["dii_net"] for f in flows)
        net_total = total_fii + total_dii

        institutional_sentiment = (
            "bullish"  if net_total > 1000  else
            "bearish"  if net_total < -1000 else
            "neutral"
        )

        return {
            "status":                  "success",
            "flows":                   flows,
            "days_fetched":            len(flows),
            "aggregate_fii_net_cr":    round(total_fii, 2),
            "aggregate_dii_net_cr":    round(total_dii, 2),
            "aggregate_combined_cr":   round(net_total, 2),
            "institutional_sentiment": institutional_sentiment,
            "source":                  "nseindia.com",
            "timestamp":               iso_ist()
        }

    except Exception as e:
        logger.exception(f"FII/DII flows exception: {e}")
        _dq.add_warning("fii_dii", f"Exception: {e}")
        return {"status": "failed", "error": "exception", "message": str(e)}


# ─────────────────────────────────────────────
#  TOOL 10 — RSS NEWS AGGREGATOR
# ─────────────────────────────────────────────

@tool("Get News from RSS Feeds")
def get_rss_news(symbol: str, company_name: str, max_articles: int = 20) -> Dict[str, Any]:
    """
    Aggregates recent financial news about a stock from multiple
    Indian financial RSS feeds: Economic Times, Moneycontrol,
    Business Standard, NDTV Profit, and Google News.

    Args:
        symbol:       NSE ticker symbol e.g. 'RELIANCE'
        company_name: Full company name e.g. 'Reliance Industries'
        max_articles: Maximum articles to return per source (default: 20)

    Returns:
        Dict with aggregated articles, sources, and raw headlines list.

    Example:
        get_rss_news('TCS', 'Tata Consultancy Services')
        get_rss_news('INFY', 'Infosys Limited', max_articles=15)
    """
    symbol       = canonical_symbol(symbol)
    search_terms = [symbol.lower(), company_name.lower().split()[0]]

    RSS_FEEDS = {
        "Economic Times Markets": "https://economictimes.indiatimes.com/markets/stocks/rss.cms",
        "Moneycontrol":           "https://www.moneycontrol.com/rss/results.xml",
        "Business Standard":      "https://www.business-standard.com/rss/markets-106.rss",
        "NDTV Profit":            "https://feeds.feedburner.com/ndtvprofit-latest",
        "Google News":            (
            f"https://news.google.com/rss/search"
            f"?q={symbol}+NSE+stock&hl=en-IN&gl=IN&ceid=IN:en"
        ),
    }

    all_articles = []
    source_stats = {}

    for source_name, feed_url in RSS_FEEDS.items():
        try:
            feed    = feedparser.parse(feed_url)
            matched = 0

            for entry in feed.entries[:50]:
                title   = (entry.get("title", "") or "").lower()
                summary = (entry.get("summary", "") or "").lower()
                content = title + " " + summary

                # Filter to stock-relevant articles
                if any(term in content for term in search_terms):
                    all_articles.append({
                        "title":      entry.get("title", "").strip(),
                        "source":     source_name,
                        "url":        entry.get("link", ""),
                        "published":  entry.get("published", ""),
                        "summary":    (entry.get("summary", "") or "")[:300].strip(),
                    })
                    matched += 1
                    if matched >= max_articles:
                        break

            source_stats[source_name] = matched

        except Exception as e:
            logger.warning(f"RSS feed error for {source_name}: {e}")
            source_stats[source_name] = 0

    # Deduplicate by title
    seen_titles  = set()
    unique_articles = []
    for article in all_articles:
        title_key = article["title"].lower()[:60]
        if title_key not in seen_titles:
            seen_titles.add(title_key)
            unique_articles.append(article)

    headlines = [a["title"] for a in unique_articles]

    return {
        "status":           "success",
        "symbol":           symbol,
        "company_name":     company_name,
        "total_articles":   len(unique_articles),
        "source_breakdown": source_stats,
        "articles":         unique_articles,
        "headlines":        headlines,
        "timestamp":        iso_ist()
    }


# ─────────────────────────────────────────────
#  TOOL 11 — BSE ANNOUNCEMENTS
# ─────────────────────────────────────────────

@tool("Get BSE Corporate Announcements")
def get_bse_announcements(symbol: str, days_back: int = 7) -> Dict[str, Any]:
    """
    Fetches recent corporate announcements for a stock from BSE India.
    Includes earnings results, board meeting notices, mergers, SEBI orders,
    investor presentations, and other material disclosures.

    Args:
        symbol:    NSE ticker symbol (auto-resolved to BSE format)
        days_back: Number of days back to search (default: 7)

    Returns:
        Dict with list of announcements with dates, categories, and headlines.

    Example:
        get_bse_announcements('RELIANCE')
        get_bse_announcements('TATASTEEL', days_back=14)
    """
    symbol   = canonical_symbol(symbol)
    to_date  = now_ist()
    from_date = to_date - timedelta(days=days_back)

    url = (
        "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"
        f"?strCat=-1&strPrevDate={from_date.strftime('%Y%m%d')}"
        f"&strScrip=&strSearch=P&strToDate={to_date.strftime('%Y%m%d')}"
        f"&strType=C"
    )

    headers = {
        "User-Agent":  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer":     "https://www.bseindia.com/",
        "Accept":      "application/json, text/plain, */*",
    }

    try:
        resp = requests.get(url, headers=headers, timeout=15)

        if resp.status_code != 200:
            _dq.add_warning("bse_announcements", f"BSE returned {resp.status_code}")
            return {"status": "failed", "error": f"http_{resp.status_code}", "symbol": symbol}

        data          = resp.json()
        all_items     = data.get("Table", [])
        announcements = []

        # Filter by symbol
        symbol_upper = symbol.upper()
        for item in all_items:
            scrip_name = (item.get("SCRIP_CD", "") or "").upper()
            company    = (item.get("COMP_NAME", "") or "").upper()
            if symbol_upper in scrip_name or symbol_upper in company:
                announcements.append({
                    "date":       item.get("NEWS_DT"),
                    "company":    item.get("COMP_NAME"),
                    "category":   item.get("CATEGORYNAME"),
                    "headline":   item.get("HEADLINE"),
                    "attachment": item.get("ATTACHMENTNAME"),
                    "scrip_code": item.get("SCRIP_CD"),
                })

        return {
            "status":        "success",
            "symbol":        symbol,
            "announcements": announcements,
            "count":         len(announcements),
            "date_range": {
                "from": from_date.strftime("%Y-%m-%d"),
                "to":   to_date.strftime("%Y-%m-%d")
            },
            "source":    "bseindia.com",
            "timestamp": iso_ist()
        }

    except Exception as e:
        logger.exception(f"BSE announcements exception for {symbol}: {e}")
        _dq.add_warning("bse_announcements", f"Exception for {symbol}: {e}")
        return {"status": "failed", "error": "exception", "message": str(e), "symbol": symbol}


# ─────────────────────────────────────────────
#  TOOL 12 — NSE MARKET CONTEXT
# ─────────────────────────────────────────────

@tool("Get Market Context and Macro Data")
def get_market_context() -> Dict[str, Any]:
    """
    Fetches broad market context data for the Indian equity market.
    Returns Nifty 50 and Nifty 500 performance, sector indices,
    market breadth (advances vs declines), VIX, and FII/DII summary.
    Used by the market_context_agent as the first pipeline step.

    Returns:
        Dict with index levels, sector performance, breadth, and macro signals.

    Example:
        get_market_context()
    """
    session = _get_nse_session()
    results = {
        "status":    "success",
        "timestamp": iso_ist(),
        "source":    "nseindia.com"
    }

    # ── Nifty 50 snapshot ────────────────────
    try:
        resp = session.get(
            "https://www.nseindia.com/api/allIndices",
            timeout=15
        )
        if resp.status_code == 200:
            indices_data = resp.json().get("data", [])
            key_indices  = {}
            target_indices = {
                "NIFTY 50", "NIFTY NEXT 50", "NIFTY 500",
                "NIFTY MIDCAP 150", "NIFTY SMALLCAP 250",
                "NIFTY BANK", "NIFTY IT", "NIFTY PHARMA",
                "NIFTY AUTO", "NIFTY FMCG", "INDIA VIX"
            }
            for idx in indices_data:
                name = idx.get("index", "")
                if name in target_indices:
                    key_indices[name] = {
                        "last":          idx.get("last"),
                        "change":        idx.get("change"),
                        "pct_change":    idx.get("percentChange"),
                        "open":          idx.get("open"),
                        "high":          idx.get("high"),
                        "low":           idx.get("low"),
                        "year_high":     idx.get("yearHigh"),
                        "year_low":      idx.get("yearLow"),
                    }
            results["indices"] = key_indices

            # Extract VIX separately for easy access
            if "INDIA VIX" in key_indices:
                vix = key_indices["INDIA VIX"].get("last", 0)
                results["india_vix"] = vix
                results["volatility_regime"] = (
                    "low"    if vix < 13 else
                    "medium" if vix < 20 else
                    "high"
                )
        else:
            _dq.add_warning("market_context", f"NSE indices returned {resp.status_code}")
            results["indices"] = {}

    except Exception as e:
        logger.warning(f"NSE indices fetch failed: {e}")
        _dq.add_warning("market_context", f"Indices fetch failed: {e}")
        results["indices"] = {}

    # ── Market breadth ───────────────────────
    try:
        resp = session.get(
            "https://www.nseindia.com/api/marketStatus",
            timeout=15
        )
        if resp.status_code == 200:
            mkt = resp.json()
            results["market_status"] = mkt.get("marketState", [])
    except Exception as e:
        logger.warning(f"Market status fetch failed: {e}")

    # ── Advance/Decline ──────────────────────
    try:
        resp = session.get(
            "https://www.nseindia.com/api/live-analysis-variations"
            "?index=nifty500",
            timeout=15
        )
        if resp.status_code == 200:
            ad_data = resp.json()
            results["advance_decline"] = {
                "advances":  ad_data.get("advances"),
                "declines":  ad_data.get("declines"),
                "unchanged": ad_data.get("unchanged"),
                "ratio":     (
                    round(ad_data.get("advances", 0) /
                          max(ad_data.get("declines", 1), 1), 2)
                )
            }
    except Exception as e:
        logger.warning(f"Advance/decline fetch failed: {e}")

    # ── FII/DII summary ──────────────────────
    try:
        fii_result = get_fii_dii_flows.func(days=5)
        if fii_result.get("status") == "success":
            results["fii_dii_summary"] = {
                "fii_net_5d_cr":       fii_result.get("aggregate_fii_net_cr"),
                "dii_net_5d_cr":       fii_result.get("aggregate_dii_net_cr"),
                "institutional_bias":  fii_result.get("institutional_sentiment"),
            }
    except Exception as e:
        logger.warning(f"FII/DII summary fetch failed: {e}")

    # ── Overall market bias ──────────────────
    try:
        nifty50 = results.get("indices", {}).get("NIFTY 50", {})
        pct     = float(nifty50.get("pct_change", 0) or 0)
        ad      = results.get("advance_decline", {})
        ad_ratio = float(ad.get("ratio", 1) or 1)
        fii_bias = (results.get("fii_dii_summary") or {}).get("institutional_bias", "neutral")

        bull_signals = sum([
            pct > 0.5,
            ad_ratio > 1.5,
            fii_bias == "bullish"
        ])
        bear_signals = sum([
            pct < -0.5,
            ad_ratio < 0.67,
            fii_bias == "bearish"
        ])

        results["market_bias"] = (
            "bullish" if bull_signals >= 2 else
            "bearish" if bear_signals >= 2 else
            "neutral"
        )
    except Exception:
        results["market_bias"] = "neutral"

    return results


# ─────────────────────────────────────────────
#  TEST ALL TOOLS
# ─────────────────────────────────────────────

def test_all_tools() -> Dict[str, Any]:
    """
    Tests all tools with a sample stock (TCS).
    Run before starting the crew to catch configuration issues.
    """
    results = {"timestamp": iso_ist(), "tests": {}}

    print("\n" + "=" * 65)
    print("  BHARATALPHA — TOOL CONNECTIVITY TEST")
    print("=" * 65 + "\n")

    # 1. Angel One Auth
    print("1. Angel One Authentication...")
    auth = authenticate_angel.func()
    results["tests"]["angel_auth"] = auth.get("status")
    icon = "✅" if auth.get("status") == "success" else "❌"
    print(f"   {icon} {auth.get('message', auth.get('error', ''))}\n")

    # 2. Angel One LTP
    if auth.get("status") == "success":
        print("2. Angel One LTP (TCS)...")
        ltp = get_angel_ltp.func("TCS")
        results["tests"]["angel_ltp"] = ltp.get("status")
        icon = "✅" if ltp.get("status") == "success" else "❌"
        print(f"   {icon} LTP: ₹{ltp.get('ltp', 'N/A')}\n")

        print("3. Angel One Historical (TCS, 30 days)...")
        hist = get_angel_historical_data.func("TCS", days=30)
        results["tests"]["angel_historical"] = hist.get("status")
        icon = "✅" if hist.get("status") == "success" else "❌"
        print(f"   {icon} {hist.get('count', 0)} candles fetched\n")
    else:
        print("   ⏭  Skipping Angel One tools — auth failed\n")
        results["tests"]["angel_ltp"]        = "skipped"
        results["tests"]["angel_historical"] = "skipped"

    # 3. Screener.in
    print("4. Screener.in Fundamentals (TCS)...")
    fund = get_screener_fundamentals.func("TCS")
    results["tests"]["screener_fundamentals"] = fund.get("status")
    icon = "✅" if fund.get("status") == "success" else "❌"
    pe   = (fund.get("valuation") or {}).get("pe_ratio", "N/A")
    print(f"   {icon} P/E: {pe}\n")

    # 4. NSE Corporate Actions
    print("5. NSE Corporate Actions (TCS)...")
    actions = get_nse_corporate_actions.func("TCS")
    results["tests"]["nse_corporate_actions"] = actions.get("status")
    icon = "✅" if actions.get("status") == "success" else "❌"
    print(f"   {icon} {actions.get('count', 0)} actions found\n")

    # 5. NSE Shareholding
    print("6. NSE Shareholding Pattern (TCS)...")
    share = get_nse_shareholding_pattern.func("TCS")
    results["tests"]["nse_shareholding"] = share.get("status")
    icon = "✅" if share.get("status") == "success" else "❌"
    print(f"   {icon} Promoter: {share.get('promoter_pct', 'N/A')}%\n")

    # 6. FII/DII Flows
    print("7. FII/DII Flows (10 days)...")
    flows = get_fii_dii_flows.func(days=10)
    results["tests"]["fii_dii_flows"] = flows.get("status")
    icon = "✅" if flows.get("status") == "success" else "❌"
    print(f"   {icon} Institutional bias: {flows.get('institutional_sentiment', 'N/A')}\n")

    # 7. RSS News
    print("8. RSS News (TCS)...")
    news = get_rss_news.func("TCS", "Tata Consultancy Services")
    results["tests"]["rss_news"] = news.get("status")
    icon = "✅" if news.get("status") == "success" else "❌"
    print(f"   {icon} {news.get('total_articles', 0)} articles found\n")

    # 8. BSE Announcements
    print("9. BSE Announcements (TCS)...")
    ann = get_bse_announcements.func("TCS")
    results["tests"]["bse_announcements"] = ann.get("status")
    icon = "✅" if ann.get("status") == "success" else "❌"
    print(f"   {icon} {ann.get('count', 0)} announcements found\n")

    # 9. Market Context
    print("10. Market Context (NSE)...")
    ctx = get_market_context.func()
    results["tests"]["market_context"] = ctx.get("status")
    icon = "✅" if ctx.get("status") == "success" else "❌"
    print(f"   {icon} Market bias: {ctx.get('market_bias', 'N/A')}\n")

    # Summary
    passed = sum(1 for v in results["tests"].values() if v == "success")
    total  = len(results["tests"])
    skipped = sum(1 for v in results["tests"].values() if v == "skipped")

    print("=" * 65)
    print(f"  RESULTS: {passed}/{total - skipped} passed  ({skipped} skipped)")
    print(f"  Data Quality: {_dq.summary()}")
    print("=" * 65 + "\n")

    results["passed"]  = passed
    results["total"]   = total
    results["skipped"] = skipped
    results["status"]  = "success" if passed == (total - skipped) else "partial"
    return results


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    test_all_tools()