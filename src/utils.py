"""
BharatAlpha — src/utils.py
==========================
Foundation utility layer. Every other module imports from here.
Handles symbol resolution, INR formatting, IST timestamps,
data quality flag aggregation, and confidence score management.
"""

import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

# ─────────────────────────────────────────────
#  LOGGING
# ─────────────────────────────────────────────

def get_logger(name: str) -> logging.Logger:
    """
    Returns a consistently formatted logger for any module in BharatAlpha.
    Call at module level: logger = get_logger("BharatAlpha.Tools")
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter(
            "%(asctime)s — %(levelname)s — %(name)s — %(message)s",
            "%Y-%m-%d %H:%M:%S"
        ))
        logger.addHandler(ch)
        logger.setLevel(logging.INFO)
    return logger

logger = get_logger("BharatAlpha.Utils")


# ─────────────────────────────────────────────
#  IST TIMEZONE
# ─────────────────────────────────────────────

IST = timezone(timedelta(hours=5, minutes=30))


def now_ist() -> datetime:
    """Returns current datetime in IST."""
    return datetime.now(IST)


def iso_ist() -> str:
    """Returns current IST time as ISO 8601 string."""
    return now_ist().isoformat()


def ist_date_str() -> str:
    """Returns today's date in IST as YYYY-MM-DD."""
    return now_ist().strftime("%Y-%m-%d")


def ist_display(dt: Optional[datetime] = None) -> str:
    """
    Returns a human-readable IST timestamp string.
    If dt is None, uses current time.
    """
    if dt is None:
        dt = now_ist()
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    return dt.strftime("%d %b %Y, %I:%M %p IST")


# ─────────────────────────────────────────────
#  INR FORMATTING
# ─────────────────────────────────────────────

def format_inr(value: Optional[float], decimals: int = 2) -> str:
    """
    Formats a number in Indian numbering system with ₹ prefix.
    
    Examples:
        1500        → ₹1,500.00
        150000      → ₹1,50,000.00
        15000000    → ₹1.50 Cr
        1500000000  → ₹150.00 Cr
    """
    if value is None:
        return "N/A"
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "N/A"

    # Use crore for large numbers (≥10 lakh)
    if abs(value) >= 1_00_00_000:          # 1 crore
        return f"₹{value / 1_00_00_000:.2f} Cr"
    if abs(value) >= 1_00_000:             # 1 lakh
        return f"₹{value / 1_00_000:.2f} L"

    # Indian comma formatting: last 3 digits, then groups of 2
    is_negative = value < 0
    value = abs(value)
    integer_part = int(value)
    decimal_part = round(value - integer_part, decimals)

    s = str(integer_part)
    if len(s) > 3:
        last3 = s[-3:]
        rest  = s[:-3]
        groups = []
        while len(rest) > 2:
            groups.append(rest[-2:])
            rest = rest[:-2]
        if rest:
            groups.append(rest)
        groups.reverse()
        s = ",".join(groups) + "," + last3
    
    decimal_str = f"{decimal_part:.{decimals}f}"[1:]  # strip leading 0
    result = f"₹{'−' if is_negative else ''}{s}{decimal_str}"
    return result


def format_crore(value: Optional[float]) -> str:
    """Formats market cap / large numbers directly in crores."""
    if value is None:
        return "N/A"
    try:
        return f"₹{float(value):,.2f} Cr"
    except (TypeError, ValueError):
        return "N/A"


def format_percent(value: Optional[float], decimals: int = 2) -> str:
    """Formats a ratio or percentage value."""
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.{decimals}f}%"
    except (TypeError, ValueError):
        return "N/A"


# ─────────────────────────────────────────────
#  SYMBOL RESOLVER
# ─────────────────────────────────────────────

# NSE uses plain symbols (RELIANCE), Angel One uses the same for equities.
# Screener.in uses the same but some edge cases differ.
# This mapping handles known exceptions.
_SYMBOL_EXCEPTIONS: Dict[str, Dict[str, str]] = {
    # "CANONICAL": {"nse": "NSE_SYMBOL", "screener": "SCREENER_SYMBOL", "angel": "ANGEL_SYMBOL"}
    "M&M":        {"nse": "M&M",        "screener": "M-M",          "angel": "M&M"},
    "L&T":        {"nse": "LT",         "screener": "LT",           "angel": "LT"},
    "HCLTECH":    {"nse": "HCLTECH",    "screener": "HCL-TECHNOLOGIES", "angel": "HCLTECH"},
    "BAJAJ-AUTO": {"nse": "BAJAJ-AUTO", "screener": "BAJAJ-AUTO",   "angel": "BAJAJ-AUTO"},
}


def resolve_symbol(
    ticker: str,
    target: str = "nse"
) -> str:
    """
    Resolves a stock symbol to the correct format for the target data source.

    Args:
        ticker:  Canonical ticker symbol (e.g. 'RELIANCE', 'M&M')
        target:  One of 'nse', 'screener', 'angel', 'display'

    Returns:
        Correctly formatted symbol string for the target source.

    Examples:
        resolve_symbol("M&M", "screener")  → "M-M"
        resolve_symbol("LT", "nse")        → "LT"
        resolve_symbol("RELIANCE", "angel")→ "RELIANCE"
    """
    ticker = ticker.strip().upper()
    if ticker in _SYMBOL_EXCEPTIONS:
        mapping = _SYMBOL_EXCEPTIONS[ticker]
        return mapping.get(target, ticker)
    # Default: symbol is the same across all sources
    return ticker


def canonical_symbol(raw: str) -> str:
    """
    Normalises any raw symbol string to a clean uppercase canonical form.
    Strips exchange suffixes (.NS, .BO, .NSE), whitespace, and lowercasing.

    Examples:
        "reliance.NS" → "RELIANCE"
        "TCS.BO"      → "TCS"
        " Infosys "   → "INFOSYS"
    """
    raw = raw.strip().upper()
    for suffix in [".NS", ".BO", ".NSE", ".BSE", "-EQ"]:
        if raw.endswith(suffix):
            raw = raw[: -len(suffix)]
    return raw


# ─────────────────────────────────────────────
#  DATA QUALITY FLAGS
# ─────────────────────────────────────────────

class DataQualityTracker:
    """
    Accumulates data quality warnings across the pipeline.
    Agents append flags; the portfolio manager reads the aggregate
    confidence multiplier before making final recommendations.

    Usage:
        dq = DataQualityTracker()
        dq.add_warning("screener", "Screener.in rate limited — using cached data")
        dq.add_critical("angel", "Authentication failed — prices are stale")
        multiplier = dq.confidence_multiplier()  # e.g. 0.6
    """

    SEVERITY_WEIGHTS = {
        "info":     0.00,   # no confidence impact
        "warning":  0.10,   # each warning reduces confidence by 10%
        "critical": 0.25,   # each critical reduces confidence by 25%
    }

    def __init__(self):
        self._flags: List[Dict[str, Any]] = []

    def add_info(self, source: str, message: str) -> None:
        self._add("info", source, message)

    def add_warning(self, source: str, message: str) -> None:
        self._add("warning", source, message)
        logger.warning(f"[DataQuality:{source}] {message}")

    def add_critical(self, source: str, message: str) -> None:
        self._add("critical", source, message)
        logger.error(f"[DataQuality:CRITICAL:{source}] {message}")

    def _add(self, severity: str, source: str, message: str) -> None:
        self._flags.append({
            "severity":  severity,
            "source":    source,
            "message":   message,
            "timestamp": iso_ist(),
        })

    def has_critical(self) -> bool:
        return any(f["severity"] == "critical" for f in self._flags)

    def confidence_multiplier(self) -> float:
        """
        Returns a multiplier between 0.1 and 1.0.
        Applied to all downstream confidence scores.
        Falls to 0.1 floor if criticals are present.
        """
        if self.has_critical():
            return 0.10
        total_reduction = sum(
            self.SEVERITY_WEIGHTS.get(f["severity"], 0)
            for f in self._flags
        )
        return max(0.10, round(1.0 - total_reduction, 2))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "flags":                self._flags,
            "total_flags":          len(self._flags),
            "has_critical":         self.has_critical(),
            "confidence_multiplier": self.confidence_multiplier(),
            "generated_at":         iso_ist(),
        }

    def summary(self) -> str:
        """Human-readable one-line summary for logging."""
        counts = {"info": 0, "warning": 0, "critical": 0}
        for f in self._flags:
            counts[f["severity"]] = counts.get(f["severity"], 0) + 1
        return (
            f"{counts['critical']} critical, "
            f"{counts['warning']} warnings, "
            f"{counts['info']} info — "
            f"confidence multiplier: {self.confidence_multiplier()}"
        )


# ─────────────────────────────────────────────
#  CONFIDENCE SCORE UTILITIES
# ─────────────────────────────────────────────

def clamp(value: float, min_val: float = 0.0, max_val: float = 1.0) -> float:
    """Clamps a float to [min_val, max_val]."""
    return max(min_val, min(max_val, float(value)))


def apply_quality_multiplier(
    score: float,
    tracker: DataQualityTracker
) -> float:
    """
    Applies the data quality confidence multiplier to a raw score.
    
    Args:
        score:   Raw confidence score 0.0–1.0
        tracker: DataQualityTracker instance from the pipeline run
    
    Returns:
        Adjusted score, clamped to [0.0, 1.0]
    """
    return clamp(score * tracker.confidence_multiplier())


def composite_score(
    fundamentals: float,
    technical:    float,
    sentiment:    float,
    risk:         float,
    weights:      Optional[Dict[str, float]] = None
) -> float:
    """
    Computes weighted composite score across all four signal sources.

    Default weights:
        Fundamentals: 0.40
        Technical:    0.30
        Sentiment:    0.20
        Risk:         0.10   (inverted — lower risk = higher contribution)

    All inputs should be normalised 0.0–1.0.
    Returns composite score 0.0–1.0.
    """
    if weights is None:
        weights = {
            "fundamentals": 0.40,
            "technical":    0.30,
            "sentiment":    0.20,
            "risk":         0.10,
        }

    # Risk score is inverted: lower risk is better
    risk_contribution = (1.0 - clamp(risk)) * weights["risk"]

    score = (
        clamp(fundamentals) * weights["fundamentals"] +
        clamp(technical)    * weights["technical"]    +
        clamp(sentiment)    * weights["sentiment"]    +
        risk_contribution
    )
    return clamp(score)


def score_to_recommendation(score: float) -> Tuple[str, str]:
    """
    Converts a composite score to a BUY/HOLD/SELL recommendation with colour tag.

    Returns:
        Tuple of (recommendation_str, colour_hex)
    """
    if score >= 0.65:
        return ("BUY",  "#12A05C")
    if score >= 0.40:
        return ("HOLD", "#C49A00")
    return ("SELL", "#D93025")


# ─────────────────────────────────────────────
#  API RESPONSE SAFETY
# ─────────────────────────────────────────────

def safe_parse_response(response: Any) -> Optional[Dict]:
    """
    Normalises any API response to a dict before .get() is called.
    Handles dicts, JSON strings, and raw error strings uniformly.
    Ported and generalised from OptiTrade's _safe_parse_response().
    """
    if response is None:
        return None
    if isinstance(response, dict):
        return response
    if isinstance(response, str):
        stripped = response.strip()
        if not stripped:
            return None
        import json
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass
        logger.warning(f"API returned raw string (not JSON): '{stripped[:120]}'")
        return {"status": False, "message": stripped}
    logger.error(f"Unexpected API response type: {type(response)} — {str(response)[:120]}")
    return None


def is_api_success(parsed: Optional[Dict]) -> bool:
    """
    Checks whether a normalised API response dict represents success.
    Handles both boolean True and string 'true'/'True' status values.
    """
    if not parsed:
        return False
    status = parsed.get("status")
    return status is True or str(status).lower() in ("true", "success", "ok")


# ─────────────────────────────────────────────
#  MARKET HOURS
# ─────────────────────────────────────────────

def is_market_open() -> bool:
    """
    Returns True if NSE/BSE is currently open for trading.
    Market hours: Monday–Friday, 09:15–15:30 IST.
    Excludes weekends only (public holidays not tracked here).
    """
    now = now_ist()
    if now.weekday() >= 5:          # Saturday=5, Sunday=6
        return False
    market_open  = now.replace(hour=9,  minute=15, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return market_open <= now <= market_close


def market_status_label() -> str:
    """Returns a human-readable market status string."""
    now = now_ist()
    if now.weekday() >= 5:
        return "Closed (Weekend)"
    open_time  = now.replace(hour=9,  minute=15, second=0, microsecond=0)
    close_time = now.replace(hour=15, minute=30, second=0, microsecond=0)
    pre_open   = now.replace(hour=9,  minute=0,  second=0, microsecond=0)

    if now < pre_open:
        return "Closed (Pre-Market)"
    if pre_open <= now < open_time:
        return "Pre-Open Session"
    if open_time <= now <= close_time:
        return "Open"
    return "Closed (After-Hours)"


# ─────────────────────────────────────────────
#  PATH HELPERS
# ─────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).parent.parent   # BharatAlpha/


def get_project_root() -> Path:
    """Returns absolute path to the BharatAlpha project root."""
    return _PROJECT_ROOT


def get_config_path(filename: str) -> Path:
    """Returns absolute path to a file inside config/."""
    return _PROJECT_ROOT / "config" / filename


def get_output_path(filename: str) -> Path:
    """Returns absolute path to a file inside output/."""
    return _PROJECT_ROOT / "output" / filename


def ensure_output_dir() -> None:
    """Creates output/ directory if it doesn't exist."""
    (_PROJECT_ROOT / "output").mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────
#  NIFTY 500 SECTOR HELPERS
# ─────────────────────────────────────────────

# Canonical sector names used throughout BharatAlpha.
# Must match entries in config/universe.yaml.
VALID_SECTORS = [
    "Information Technology",
    "Financial Services",
    "Fast Moving Consumer Goods",
    "Automobile",
    "Healthcare",
    "Energy",
    "Metals & Mining",
    "Infrastructure",
    "Real Estate",
    "Telecom",
    "Media & Entertainment",
    "Chemicals",
    "Consumer Durables",
    "Textiles",
    "Diversified",
]


def normalise_sector(raw: str) -> str:
    """
    Normalises a user-supplied sector string to the canonical form.
    Case-insensitive, partial matching supported.

    Examples:
        "IT"          → "Information Technology"
        "fintech"     → "Financial Services"
        "pharma"      → "Healthcare"
        "fmcg"        → "Fast Moving Consumer Goods"
    """
    raw_lower = raw.strip().lower()

    aliases: Dict[str, str] = {
        "it":              "Information Technology",
        "tech":            "Information Technology",
        "software":        "Information Technology",
        "fintech":         "Financial Services",
        "banking":         "Financial Services",
        "finance":         "Financial Services",
        "nbfc":            "Financial Services",
        "fmcg":            "Fast Moving Consumer Goods",
        "consumer staples":"Fast Moving Consumer Goods",
        "auto":            "Automobile",
        "automobiles":     "Automobile",
        "pharma":          "Healthcare",
        "pharmaceutical":  "Healthcare",
        "oil":             "Energy",
        "gas":             "Energy",
        "power":           "Energy",
        "metal":           "Metals & Mining",
        "mining":          "Metals & Mining",
        "steel":           "Metals & Mining",
        "infra":           "Infrastructure",
        "realty":          "Real Estate",
        "realestate":      "Real Estate",
        "telecom":         "Telecom",
        "media":           "Media & Entertainment",
        "entertainment":   "Media & Entertainment",
        "chemical":        "Chemicals",
        "durables":        "Consumer Durables",
        "textile":         "Textiles",
    }

    if raw_lower in aliases:
        return aliases[raw_lower]

    # Partial match against canonical names
    for sector in VALID_SECTORS:
        if raw_lower in sector.lower():
            return sector

    logger.warning(f"Could not normalise sector '{raw}' — returning as-is")
    return raw.strip().title()


# ─────────────────────────────────────────────
#  VALIDATION HELPERS
# ─────────────────────────────────────────────

def validate_env() -> Tuple[bool, List[str]]:
    """
    Validates all required environment variables are present.
    Returns (all_present: bool, missing_keys: List[str]).
    Call at application startup.
    """
    import os
    required = [
        "ANGEL_API_KEY",
        "ANGEL_CLIENT_ID",
        "ANGEL_MPIN",
        "ANGEL_TOTP_SECRET",
        "ANTHROPIC_API_KEY",
        "SERPER_API_KEY",
    ]
    missing = [k for k in required if not os.getenv(k)]
    return (len(missing) == 0, missing)


def sanitise_ticker_input(raw: str) -> Optional[str]:
    """
    Validates and sanitises a user-provided ticker string.
    Returns the clean canonical symbol or None if invalid.

    Valid: 1–20 uppercase alphanumeric characters, hyphens, ampersands.
    """
    cleaned = canonical_symbol(raw)
    pattern = r'^[A-Z0-9&\-]{1,20}$'
    if re.match(pattern, cleaned):
        return cleaned
    logger.warning(f"Invalid ticker input rejected: '{raw}'")
    return None


# ─────────────────────────────────────────────
#  QUICK SELF-TEST
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=== BharatAlpha Utils Self-Test ===\n")

    # Timestamp
    print(f"IST Now:        {ist_display()}")
    print(f"Market Status:  {market_status_label()}\n")

    # INR formatting
    for val in [1500, 150000, 1500000, 15000000, 1500000000]:
        print(f"  {val:>15,}  →  {format_inr(val)}")

    # Symbol resolution
    print()
    for sym, target in [("M&M", "screener"), ("LT", "nse"), ("RELIANCE", "angel")]:
        print(f"  resolve_symbol({sym!r}, {target!r}) → {resolve_symbol(sym, target)}")

    # Sector normalisation
    print()
    for raw in ["IT", "pharma", "fmcg", "banking", "auto"]:
        print(f"  normalise_sector({raw!r}) → {normalise_sector(raw)}")

    # Composite score
    print()
    for f, t, s, r in [(0.8, 0.7, 0.6, 0.2), (0.5, 0.5, 0.5, 0.5), (0.3, 0.2, 0.3, 0.8)]:
        score = composite_score(f, t, s, r)
        rec, colour = score_to_recommendation(score)
        print(f"  composite({f},{t},{s},{r}) → {score:.3f}  [{rec}]")

    # Data quality tracker
    print()
    dq = DataQualityTracker()
    dq.add_info("test", "All systems nominal")
    dq.add_warning("screener", "Rate limited, using cache")
    print(f"  DataQuality summary: {dq.summary()}")

    # Env validation
    ok, missing = validate_env()
    print(f"\n  Env valid: {ok}" + (f" — Missing: {missing}" if not ok else ""))

    print("\n=== Self-Test Complete ===")