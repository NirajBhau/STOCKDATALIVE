import os
import time
import logging
from typing import List, Dict, Any, Optional

import gspread
from google.auth.exceptions import GoogleAuthError
from gspread.exceptions import APIError, SpreadsheetNotFound, WorksheetNotFound

from utils.config import Config
from google_sheets.formatting import apply_sheet_formatting
from analysis.calculations import build_analysis_rows, ANALYSIS_HEADERS

logger = logging.getLogger("investing_sync.sheets")

LIVE_DATA_HEADERS = [
    "Name",
    "Symbol",
    "Last",
    "Open",
    "High",
    "Low",
    "Change",
    "Change %",
    "Volume",
    "Market Time",
    "Updated At"
]

HISTORY_HEADERS = [
    "Extraction Timestamp",
    "Name",
    "Symbol",
    "Last",
    "Open",
    "High",
    "Low",
    "Change",
    "Change %",
    "Volume",
    "Market Time"
]

class GoogleSheetsClient:
    """
    Manages Google Sheets API authentication, worksheet setup, and real-time updates for LIVE_DATA, HISTORY, and ANALYSIS worksheets.
    """

    def __init__(self, config: Config):
        self.config = config
        self.gc: Optional[gspread.Client] = None
        self.spreadsheet: Optional[gspread.Spreadsheet] = None
        self.last_history_keys = set()  # Deduplication cache for (symbol, timestamp)

    def _execute_with_retry(self, func, *args, max_retries: int = 5, backoff_factor: float = 2.0, **kwargs):
        """
        Executes a function with exponential backoff retry for transient network and Google API rate limits.
        """
        for attempt in range(1, max_retries + 1):
            try:
                return func(*args, **kwargs)
            except (APIError, GoogleAuthError, Exception) as exc:
                is_rate_limit = "429" in str(exc) or "Quota exceeded" in str(exc) or "503" in str(exc)
                if attempt == max_retries:
                    logger.error(f"Google Sheets API call failed after {max_retries} attempts: {exc}")
                    raise exc

                sleep_seconds = backoff_factor ** attempt
                if is_rate_limit:
                    sleep_seconds += 2.0
                logger.warning(f"Google API transient error (attempt {attempt}/{max_retries}): {exc}. Retrying in {sleep_seconds:.1f}s...")
                time.sleep(sleep_seconds)

    def connect(self) -> bool:
        """Authenticates with Google Sheets API and opens the target spreadsheet."""
        logger.info("Authenticating with Google Cloud Service Account...")
        try:
            cred_json_str = os.getenv("GOOGLE_CREDENTIALS_JSON", "").strip()
            if cred_json_str:
                import json
                cred_dict = json.loads(cred_json_str)
                if "private_key" in cred_dict and isinstance(cred_dict["private_key"], str):
                    cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
                self.gc = gspread.service_account_from_dict(cred_dict)
            else:
                self.gc = gspread.service_account(filename=self.config.google_credentials_file)
            
            logger.info(f"Opening Google Spreadsheet ID: {self.config.google_sheet_id}")
            self.spreadsheet = self.gc.open_by_key(self.config.google_sheet_id)
            logger.info("Successfully connected to Google Spreadsheet.")
            return True
        except SpreadsheetNotFound:
            logger.error(f"Spreadsheet ID '{self.config.google_sheet_id}' was not found or has not been shared with the service account email.")
            return False
        except Exception as exc:
            logger.error(f"Failed to connect to Google Sheets API: {exc}")
            return False

    def setup_worksheets_and_formatting(self):
        """Ensures LIVE_DATA, HISTORY, and ANALYSIS worksheets exist with headers and proper formatting."""
        if not self.spreadsheet:
            logger.error("Spreadsheet connection not established.")
            return

        def _setup():
            required_sheets = {
                "LIVE_DATA": (LIVE_DATA_HEADERS, 11),
                "HISTORY": (HISTORY_HEADERS, 11),
                "ANALYSIS": (ANALYSIS_HEADERS, 12)
            }

            existing_worksheets = {ws.title: ws for ws in self.spreadsheet.worksheets()}

            for title, (headers, col_count) in required_sheets.items():
                if title not in existing_worksheets:
                    logger.info(f"Creating missing worksheet '{title}'...")
                    ws = self.spreadsheet.add_worksheet(title=title, rows=100, cols=col_count)
                    ws.update("A1", [headers], value_input_option="USER_ENTERED")
                    apply_sheet_formatting(self.spreadsheet, title, col_count)
                else:
                    ws = existing_worksheets[title]
                    first_row = ws.row_values(1)
                    if not first_row:
                        logger.info(f"Initializing empty header row in sheet '{title}'...")
                        ws.update("A1", [headers], value_input_option="USER_ENTERED")
                        apply_sheet_formatting(self.spreadsheet, title, col_count)

        self._execute_with_retry(_setup)

    def sync_data(self, cleaned_rows: List[Dict[str, Any]]) -> bool:
        """
        Main synchronization method:
        1. Updates LIVE_DATA tab.
        2. Appends new observations to HISTORY tab (preventing duplicates).
        3. Updates formulas in ANALYSIS tab.
        """
        if not self.spreadsheet:
            logger.error("Spreadsheet is not connected.")
            return False

        if not cleaned_rows:
            logger.warning("No data rows to sync.")
            return True

        def _sync():
            # 1. Prepare LIVE_DATA matrix
            live_matrix = [LIVE_DATA_HEADERS]
            history_rows = []

            for row in cleaned_rows:
                # Format None values as empty strings for clean sheet presentation
                def fmt(v):
                    return "" if v is None else v

                live_row = [
                    fmt(row.get("Name")),
                    fmt(row.get("Symbol")),
                    fmt(row.get("Last")),
                    fmt(row.get("Open")),
                    fmt(row.get("High")),
                    fmt(row.get("Low")),
                    fmt(row.get("Change")),
                    fmt(row.get("Change %")),
                    fmt(row.get("Volume")),
                    fmt(row.get("Market Time")),
                    fmt(row.get("Extraction Timestamp"))
                ]
                live_matrix.append(live_row)

                # Deduplication check for HISTORY
                symbol_key = str(row.get("Symbol") or row.get("Name"))
                timestamp_key = str(row.get("Extraction Timestamp"))
                dedup_key = (symbol_key, timestamp_key)

                if dedup_key not in self.last_history_keys:
                    history_row = [
                        fmt(row.get("Extraction Timestamp")),
                        fmt(row.get("Name")),
                        fmt(row.get("Symbol")),
                        fmt(row.get("Last")),
                        fmt(row.get("Open")),
                        fmt(row.get("High")),
                        fmt(row.get("Low")),
                        fmt(row.get("Change")),
                        fmt(row.get("Change %")),
                        fmt(row.get("Volume")),
                        fmt(row.get("Market Time"))
                    ]
                    history_rows.append(history_row)
                    self.last_history_keys.add(dedup_key)

            # Keep cache bounded
            if len(self.last_history_keys) > 2000:
                self.last_history_keys.clear()

            # Update LIVE_DATA worksheet
            ws_live = self.spreadsheet.worksheet("LIVE_DATA")
            # Clear old values to handle removals cleanly
            ws_live.clear()
            ws_live.update("A1", live_matrix, value_input_option="USER_ENTERED")
            apply_sheet_formatting(self.spreadsheet, "LIVE_DATA", len(LIVE_DATA_HEADERS), len(live_matrix))
            logger.info(f"LIVE_DATA updated with {len(cleaned_rows)} instruments.")

            # Append to HISTORY worksheet
            if history_rows:
                ws_hist = self.spreadsheet.worksheet("HISTORY")
                ws_hist.append_rows(history_rows, value_input_option="USER_ENTERED")
                apply_sheet_formatting(self.spreadsheet, "HISTORY", len(HISTORY_HEADERS))
                logger.info(f"HISTORY appended with {len(history_rows)} new observation rows.")

            # Update ANALYSIS worksheet
            analysis_matrix = [ANALYSIS_HEADERS] + build_analysis_rows(cleaned_rows)
            ws_analysis = self.spreadsheet.worksheet("ANALYSIS")
            ws_analysis.clear()
            ws_analysis.update("A1", analysis_matrix, value_input_option="USER_ENTERED")
            apply_sheet_formatting(self.spreadsheet, "ANALYSIS", len(ANALYSIS_HEADERS), len(analysis_matrix))
            logger.info("ANALYSIS sheet updated with dynamic formulas.")

        try:
            self._execute_with_retry(_sync)
            return True
        except Exception as exc:
            logger.error(f"Failed to sync data to Google Sheets: {exc}")
            return False
