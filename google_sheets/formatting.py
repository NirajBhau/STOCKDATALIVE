import logging
from typing import Dict, Any, List

logger = logging.getLogger("investing_sync.formatting")

def apply_sheet_formatting(spreadsheet, worksheet_name: str, column_count: int, row_count: int = 100):
    """
    Applies comprehensive formatting to a worksheet using Google Sheets API batchUpdate requests:
    - Freezes the top header row
    - Bolds and colors header cells (Navy blue background, white text)
    - Adds auto-filter to headers
    - Sets number and percentage formats on numerical columns
    - Adds conditional formatting for positive/negative change
    """
    try:
        worksheet = spreadsheet.worksheet(worksheet_name)
        sheet_id = worksheet.id
    except Exception as exc:
        logger.warning(f"Could not find worksheet '{worksheet_name}' to format: {exc}")
        return

    requests = []

    # 1. Freeze header row (1 row)
    requests.append({
        "updateSheetProperties": {
            "properties": {
                "sheetId": sheet_id,
                "gridProperties": {
                    "frozenRowCount": 1
                }
            },
            "fields": "gridProperties.frozenRowCount"
        }
    })

    # 2. Format Header Row (Row 0, Columns 0 to column_count - 1)
    requests.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 0,
                "endRowIndex": 1,
                "startColumnIndex": 0,
                "endColumnIndex": column_count
            },
            "cell": {
                "userEnteredFormat": {
                    "backgroundColor": {"red": 0.11, "green": 0.22, "blue": 0.44},  # Dark navy blue
                    "textFormat": {
                        "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0}, # White text
                        "bold": True,
                        "fontSize": 10
                    },
                    "horizontalAlignment": "CENTER",
                    "verticalAlignment": "MIDDLE"
                }
            },
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)"
        }
    })

    # 3. Add Basic Filter to Header Row
    requests.append({
        "setBasicFilter": {
            "filter": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": max(1, row_count),
                    "startColumnIndex": 0,
                    "endColumnIndex": column_count
                }
            }
        }
    })

    # 4. Conditional Formatting for Change / Change % columns if in LIVE_DATA or HISTORY or ANALYSIS
    # Target columns with positive/negative numbers (Change, Change %)
    # We add soft green for > 0, soft red for < 0
    change_col_indices = [6, 7] if worksheet_name in ("LIVE_DATA", "HISTORY") else [3, 4, 10]

    for col_idx in change_col_indices:
        if col_idx < column_count:
            # Positive rule (> 0)
            requests.append({
                "addConditionalFormatRule": {
                    "rule": {
                        "ranges": [{
                            "sheetId": sheet_id,
                            "startRowIndex": 1,
                            "endRowIndex": 1000,
                            "startColumnIndex": col_idx,
                            "endColumnIndex": col_idx + 1
                        }],
                        "booleanRule": {
                            "condition": {
                                "type": "NUMBER_GREATER",
                                "values": [{"userEnteredValue": "0"}]
                            },
                            "format": {
                                "backgroundColor": {"red": 0.85, "green": 0.95, "blue": 0.85},
                                "textFormat": {"foregroundColor": {"red": 0.0, "green": 0.45, "blue": 0.0}, "bold": True}
                            }
                        }
                    },
                    "index": 0
                }
            })

            # Negative rule (< 0)
            requests.append({
                "addConditionalFormatRule": {
                    "rule": {
                        "ranges": [{
                            "sheetId": sheet_id,
                            "startRowIndex": 1,
                            "endRowIndex": 1000,
                            "startColumnIndex": col_idx,
                            "endColumnIndex": col_idx + 1
                        }],
                        "booleanRule": {
                            "condition": {
                                "type": "NUMBER_LESS",
                                "values": [{"userEnteredValue": "0"}]
                            },
                            "format": {
                                "backgroundColor": {"red": 0.98, "green": 0.85, "blue": 0.85},
                                "textFormat": {"foregroundColor": {"red": 0.65, "green": 0.0, "blue": 0.0}, "bold": True}
                            }
                        }
                    },
                    "index": 1
                }
            })

    try:
        spreadsheet.batch_update({"requests": requests})
        logger.info(f"Applied layout & formatting to sheet '{worksheet_name}'.")
    except Exception as exc:
        logger.warning(f"Formatting batch_update warning for '{worksheet_name}': {exc}")
