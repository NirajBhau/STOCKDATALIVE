# Real-Time Investing.com → Google Sheets Automation System

A Python automation system that continuously extracts dynamically updating watchlist data from **Investing.com** using **Playwright** and syncs it live to **Google Sheets**.

---

## System Overview & Architecture

```
Investing.com Watchlist
         ↓
  Python + Playwright (Persistent Chromium Profile)
         ↓
  Data Extraction & Cleaning / Parser
         ↓
  Google Sheets API (gspread + google-auth)
         ↓
  Google Sheet (LIVE_DATA | HISTORY | ANALYSIS)
         ↓
  Shared Users / Mobile / Web Viewers
```

---

## Features

- **Dynamic Instrument Detection**: Automatically extracts all visible rows (`Name`, `Symbol`, `Last`, `Open`, `High`, `Low`, `Change`, `Change %`, `Volume`, `Market Time`). Detects instruments added or removed in real time.
- **Persistent Authenticated Session**: Uses a persistent browser profile (`playwright_profile/`). Log in manually once, and session cookies are preserved for future runs.
- **Robust Data Cleaning & Parser**:
  - Removes commas (`23,329.00` → `23329.0`).
  - Formats percentages (`-0.36%` → `-0.36`).
  - Converts compact suffixes (`244.15M` → `244150000.0`, `1.2K` → `1200.0`, `3.5B` → `3500000000.0`).
  - Handles currency symbols, hyphens (`-`), whitespace, and missing values safely without corrupting data or crashing.
- **Three Automated Worksheets**:
  1. **`LIVE_DATA`**: Shows only current prices. Rows are updated in place without duplicate accumulation.
  2. **`HISTORY`**: Appends every observation snapshot with extraction timestamp (`YYYY-MM-DD HH:MM:SS Timezone`). Built-in deduplication prevents retry duplicate records.
  3. **`ANALYSIS`**: Dynamic Google Sheets formulas calculating `Latest Price`, `Previous Price`, `Price Difference`, `Price Change %`, `Intraday High`, `Intraday Low`, `Distance From High %`, `Distance From Low %`, `Volume`, `Latest Change %`, and `Observation Count`.
- **Automated Sheet Formatting**:
  - Header freeze row.
  - Bold headers with Navy blue background and white text.
  - Auto-filters on all header columns.
  - Conditional formatting (soft green for positive price changes, soft red for negative).
- **Resilience & Rate Limit Protection**: Exponential backoff retries for Google API quota limits (`429` / `503`) and Playwright page navigation timeouts.
- **Clean Shutdown**: Catches `CTRL+C` (`SIGINT`/`SIGTERM`) to cleanly close browser context and save pending data.

---

## Prerequisites & Installation

### 1. Requirements
- **Python**: Version 3.8 or higher.
- **Google Cloud Account**: Free tier with Google Sheets API enabled.

### 2. Virtual Environment Setup
Open a terminal in the project directory:

```bash
python -m venv .venv
```

Activate the environment:
- **Windows (PowerShell)**: `.venv\Scripts\Activate.ps1`
- **Windows (CMD)**: `.venv\Scripts\activate.bat`
- **Linux/macOS**: `source .venv/bin/activate`

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Install Playwright Browsers
```bash
playwright install chromium
```

---

## Google Cloud & Google Sheets Setup

### 1. Create Google Cloud Project & Enable Google Sheets API
1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project (e.g., `Investing-Watchlist-Sync`).
3. In the search bar, search for **Google Sheets API** and click **Enable**.

### 2. Create Service Account & Download Credentials
1. In Google Cloud Console, navigate to **IAM & Admin** > **Service Accounts**.
2. Click **Create Service Account**.
3. Name it `sheets-writer` and click **Create and Continue**.
4. Skip optional role assignments and click **Done**.
5. Click on the newly created service account email.
6. Go to the **Keys** tab > **Add Key** > **Create new key**.
7. Select **JSON** format and click **Create**.
8. Save the downloaded JSON file as `credentials/service_account.json` inside the project folder.

### 3. Create Google Sheet & Share Access
1. Open [Google Sheets](https://sheets.google.com) and create a new blank spreadsheet.
2. Title it (e.g., `Investing.com Live Watchlist`).
3. Copy the **Spreadsheet ID** from the browser URL:
   `https://docs.google.com/spreadsheets/d/`**`1ABC123xyz_YOUR_SHEET_ID_HERE`**`/edit`
4. Click the **Share** button in top right of the Google Sheet.
5. Copy your **Service Account Email** (found in `credentials/service_account.json` under `"client_email"`).
6. Paste the email into the Share dialog, select **Editor** permissions, uncheck *Notify people*, and click **Share**.

---

## Environment Configuration

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Edit `.env` with your settings:

```env
INVESTING_URL=https://www.investing.com/watchlist/
SCRAPE_INTERVAL_SECONDS=10
GOOGLE_SHEET_ID=1ABC123xyz_YOUR_ACTUAL_SHEET_ID
GOOGLE_CREDENTIALS_FILE=credentials/service_account.json
TIMEZONE=Asia/Kolkata
HEADLESS=false
```

---

## How to Run & Use

### 1. First-Time Launch & Manual Login
On the first run, `HEADLESS=false` will launch the browser window:

```bash
python main.py
```

1. If Investing.com requires login, log into your Investing.com account directly in the opened browser window.
2. Open your desired watchlist page.
3. The session cookies and login state will automatically save in the `playwright_profile/` directory.
4. Future runs will reuse this authenticated session without asking for login again.

### 2. Continuous Real-Time Monitoring
The application will continuously run in a loop:
- Scrapes the visible watchlist.
- Cleans and converts raw table cells to numeric formats.
- Upserts current values to **`LIVE_DATA`**.
- Appends new records to **`HISTORY`**.
- Updates formulas on **`ANALYSIS`**.
- Sleeps for `SCRAPE_INTERVAL_SECONDS` (default: 10 seconds).

### 3. Stopping the Application
Press `CTRL+C` in your terminal. The application will log the signal, cleanly close the browser session, and terminate gracefully.

---

## Sharing the Google Sheet

To allow another person to view the live market data from another computer or mobile device:

1. Open your Google Sheet in a browser.
2. Click **Share**.
3. Add the email address of the viewer (or set link sharing to "Anyone with the link can view").
4. Choose **Viewer** or **Editor** permission as desired.
5. Send them the Google Sheet link.

> **Note**: The recipient **does NOT need** Python, Playwright, Chrome, Google Cloud credentials, or an Investing.com account. They only need access to the Google Sheet link.

---

## Project Structure

```
STOCKDATALIVE/
│
├── main.py                     # Main application entrypoint & continuous loop
│
├── scraper/
│   ├── __init__.py             # Exports scraper & parser module
│   ├── investing.py            # Playwright browser driver & DOM watchlist extractor
│   └── parser.py               # Clean numeric parser, multipliers & timestamps
│
├── google_sheets/
│   ├── __init__.py             # Exports Google Sheets client & formatting
│   ├── sheets_client.py        # gspread API integration & upsert/append logic
│   └── formatting.py           # Centralized Google Sheets batchUpdate formatting
│
├── analysis/
│   ├── __init__.py             # Exports formula builder
│   └── calculations.py         # Dynamic Google Sheets formulas for ANALYSIS tab
│
├── utils/
│   ├── __init__.py             # Exports logger & config loaders
│   ├── logger.py               # Dual console + file logger
│   └── config.py               # Environment configuration loader & validator
│
├── credentials/
│   └── service_account.json    # Google Cloud service account key (Git ignored)
│
├── logs/
│   └── app.log                 # Continuous execution & error log (Git ignored)
│
├── .env                        # Local environment secrets (Git ignored)
├── .env.example                # Configuration template
├── .gitignore                  # Security & artifact exclusions
├── requirements.txt            # Dependencies list
└── README.md                   # System documentation & setup guide
```

---

## Troubleshooting & FAQ

- **"Spreadsheet ID was not found or has not been shared"**: Verify that `GOOGLE_SHEET_ID` in `.env` is exact and that you clicked **Share** in Google Sheets to give `Editor` permissions to the service account email.
- **Investing.com Watchlist Table Not Found**: Ensure you are logged into Investing.com and your browser is on the watchlist URL. If the page layout changes, Playwright will automatically fallback to inspecting generic data grids.
- **Google API Rate Limit (429)**: The system includes exponential backoff retries. If scraping frequently (e.g., 5 seconds), increase `SCRAPE_INTERVAL_SECONDS` to `10` or `30` in `.env`.
