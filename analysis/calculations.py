from typing import List, Dict, Any

ANALYSIS_HEADERS = [
    "Instrument",
    "Latest Price",
    "Previous Price",
    "Price Difference",
    "Price Change %",
    "Intraday High",
    "Intraday Low",
    "Distance From High %",
    "Distance From Low %",
    "Volume",
    "Latest Change %",
    "Observation Count"
]

def build_analysis_rows(live_data_rows: List[Dict[str, Any]]) -> List[List[Any]]:
    """
    Builds dynamic formula rows for the ANALYSIS worksheet based on current LIVE_DATA rows.
    Row 1 in Google Sheets is Header, so instrument rows start at row 2.
    """
    analysis_rows = []

    for idx, row in enumerate(live_data_rows):
        row_num = idx + 2  # 1-indexed header is row 1, data starts at row 2

        # Referencing LIVE_DATA columns:
        # Col A = Name
        # Col B = Symbol
        # Col C = Last
        # Col D = Open
        # Col E = High
        # Col F = Low
        # Col G = Change
        # Col H = Change %
        # Col I = Volume
        # Col J = Market Time
        # Col K = Updated At

        # ANALYSIS columns formulas (referencing row_num in LIVE_DATA and current row in ANALYSIS):
        # A: Instrument = LIVE_DATA!A{row_num} & " (" & LIVE_DATA!B{row_num} & ")"
        # B: Latest Price = LIVE_DATA!C{row_num}
        # C: Previous Price = LIVE_DATA!C{row_num} - LIVE_DATA!G{row_num}
        # D: Price Difference = LIVE_DATA!G{row_num}
        # E: Price Change % = LIVE_DATA!H{row_num}
        # F: Intraday High = LIVE_DATA!E{row_num}
        # G: Intraday Low = LIVE_DATA!F{row_num}
        # H: Distance From High % = IF(F{row_num}>0, (B{row_num}-F{row_num})/F{row_num}, 0)
        # I: Distance From Low % = IF(G{row_num}>0, (B{row_num}-G{row_num})/G{row_num}, 0)
        # J: Volume = LIVE_DATA!I{row_num}
        # K: Latest Change % = LIVE_DATA!H{row_num}
        # L: Observation Count = COUNTIF(HISTORY!C:C, LIVE_DATA!B{row_num})

        formula_row = [
            f'=LIVE_DATA!A{row_num} & IF(LEN(LIVE_DATA!B{row_num})>0, " (" & LIVE_DATA!B{row_num} & ")", "")',
            f'=LIVE_DATA!C{row_num}',
            f'=IF(ISNUMBER(LIVE_DATA!G{row_num}), LIVE_DATA!C{row_num} - LIVE_DATA!G{row_num}, LIVE_DATA!C{row_num})',
            f'=LIVE_DATA!G{row_num}',
            f'=LIVE_DATA!H{row_num}',
            f'=LIVE_DATA!E{row_num}',
            f'=LIVE_DATA!F{row_num}',
            f'=IF(AND(ISNUMBER(F{row_num}), F{row_num}>0), (B{row_num} - F{row_num}) / F{row_num}, 0)',
            f'=IF(AND(ISNUMBER(G{row_num}), G{row_num}>0), (B{row_num} - G{row_num}) / G{row_num}, 0)',
            f'=LIVE_DATA!I{row_num}',
            f'=LIVE_DATA!H{row_num}',
            f'=COUNTIF(HISTORY!C:C, LIVE_DATA!B{row_num})'
        ]
        analysis_rows.append(formula_row)

    return analysis_rows
