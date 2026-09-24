import re
import logging
from datetime import datetime
import pytz

logger = logging.getLogger("investing_sync.parser")

def parse_number(value_str):
    """
    Parses string numeric representation into a float or int.
    Handles:
      - Commas (e.g., '23,329.00' -> 23329.0)
      - Percentages (e.g., '-0.36%' -> -0.36)
      - Suffixed amounts: K, M, B, T (e.g., '244.15M' -> 244150000.0)
      - Currency symbols: $, €, ₹, £, etc.
      - Missing values: '-', 'N/A', '', '--' -> None
      - Preserves raw string if unexpected format occurs.
    """
    if value_str is None:
        return None
    
    if isinstance(value_str, (int, float)):
        return float(value_str)

    raw_val = str(value_str).strip()

    if not raw_val or raw_val in ("-", "--", "N/A", "nan", "null", "None", "0"):
        if raw_val in ("-", "--", "N/A", "nan", "null", "None"):
            return None
        if raw_val == "0":
            return 0.0

    # Clean whitespace and common currency symbols
    cleaned = re.sub(r"[\$\€\₹\£\¥\s]", "", raw_val)

    # Check for percentage
    is_percent = False
    if cleaned.endswith("%"):
        is_percent = True
        cleaned = cleaned[:-1].strip()

    # Remove commas
    cleaned = cleaned.replace(",", "")

    # Multipliers suffix check
    multiplier = 1.0
    if cleaned and cleaned[-1].upper() in ("K", "M", "B", "T"):
        unit = cleaned[-1].upper()
        cleaned = cleaned[:-1].strip()
        if unit == "K":
            multiplier = 1_000.0
        elif unit == "M":
            multiplier = 1_000_000.0
        elif unit == "B":
            multiplier = 1_000_000_000.0
        elif unit == "T":
            multiplier = 1_000_000_000_000.0

    try:
        val_float = float(cleaned) * multiplier
        return val_float
    except Exception as exc:
        logger.warning(f"Could not parse numeric value from raw string '{value_str}': {exc}. Preserving raw value.")
        return raw_val

def get_current_timestamp(tz_name: str = "Asia/Kolkata") -> str:
    """
    Generates a localized extraction timestamp string in YYYY-MM-DD HH:MM:SS Timezone format.
    """
    try:
        tz = pytz.timezone(tz_name)
        now = datetime.now(tz)
    except Exception:
        now = datetime.now()
        tz_name = "UTC"
    return f"{now.strftime('%Y-%m-%d %H:%M:%S')} {tz_name}"

def clean_watchlist_row(raw_row: dict, tz_name: str = "Asia/Kolkata") -> dict:
    """
    Cleans a single row dictionary from Investing.com watchlist scraper.
    Expected raw_row keys:
      - Name
      - Symbol
      - Last
      - Open
      - High
      - Low
      - Change (or Chg.)
      - Change % (or Chg. %)
      - Volume (or Vol.)
      - Market Time (or Time)
    """
    name = str(raw_row.get("Name", "")).strip()
    symbol = str(raw_row.get("Symbol", "")).strip() or name

    cleaned = {
        "Name": name,
        "Symbol": symbol,
        "Last": parse_number(raw_row.get("Last")),
        "Open": parse_number(raw_row.get("Open")),
        "High": parse_number(raw_row.get("High")),
        "Low": parse_number(raw_row.get("Low")),
        "Change": parse_number(raw_row.get("Change") or raw_row.get("Chg.")),
        "Change %": parse_number(raw_row.get("Change %") or raw_row.get("Chg. %")),
        "Volume": parse_number(raw_row.get("Volume") or raw_row.get("Vol.")),
        "Market Time": str(raw_row.get("Market Time") or raw_row.get("Time") or "").strip(),
        "Extraction Timestamp": get_current_timestamp(tz_name)
    }
    return cleaned
