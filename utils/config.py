import os
from dataclasses import dataclass
from dotenv import load_dotenv

@dataclass
class Config:
    investing_url: str
    scrape_interval_seconds: int
    google_sheet_id: str
    google_credentials_file: str
    timezone: str
    headless: bool

def load_config(env_path: str = ".env") -> Config:
    """
    Loads configuration from environment variables / .env file and validates required fields.
    """
    if os.path.exists(env_path):
        load_dotenv(dotenv_path=env_path)
    else:
        load_dotenv()

    investing_url = os.getenv("INVESTING_URL", "https://www.investing.com/watchlist/").strip()
    
    interval_str = os.getenv("SCRAPE_INTERVAL_SECONDS", "10").strip()
    try:
        scrape_interval_seconds = int(interval_str)
        if scrape_interval_seconds < 1:
            scrape_interval_seconds = 10
    except ValueError:
        scrape_interval_seconds = 10

    google_sheet_id = os.getenv("GOOGLE_SHEET_ID", "").strip()
    google_credentials_file = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials/service_account.json").strip()
    timezone = os.getenv("TIMEZONE", "Asia/Kolkata").strip()
    
    headless_str = os.getenv("HEADLESS", "false").strip().lower()
    headless = headless_str in ("true", "1", "yes")

    return Config(
        investing_url=investing_url,
        scrape_interval_seconds=scrape_interval_seconds,
        google_sheet_id=google_sheet_id,
        google_credentials_file=google_credentials_file,
        timezone=timezone,
        headless=headless
    )

def validate_config(config: Config) -> list:
    """
    Validates config and returns a list of error warning messages if any are missing.
    """
    errors = []
    if not config.google_sheet_id or config.google_sheet_id.startswith("1YourGoogleSheetID"):
        errors.append("GOOGLE_SHEET_ID is not configured in .env.")
    
    if not os.path.exists(config.google_credentials_file):
        errors.append(f"Google service account file not found at: '{config.google_credentials_file}'. Please place your credentials JSON file there.")

    return errors
