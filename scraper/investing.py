import os
import time
import logging
from typing import List, Dict, Any, Optional
from playwright.sync_api import sync_playwright, Playwright, BrowserContext, Page, TimeoutError as PlaywrightTimeoutError

from utils.config import Config
from scraper.parser import clean_watchlist_row

logger = logging.getLogger("investing_sync.scraper")

TARGET_INSTRUMENT_URLS = {
    "EUR/USD": "https://www.investing.com/currencies/eur-usd",
    "XAU/EUR": "https://www.investing.com/currencies/xau-eur",
    "XAU/USD": "https://www.investing.com/currencies/xau-usd",
    "Nifty 50": "https://www.investing.com/indices/s-p-cnx-nifty"
}

class InvestingScraper:
    """
    Playwright scraper using a persistent browser profile to extract live Investing.com watchlist data.
    Supports dynamic watchlist table extraction and direct instrument fallback.
    """

    def __init__(self, config: Config):
        self.config = config
        self.profile_dir = os.path.abspath("playwright_profile")
        os.makedirs(self.profile_dir, exist_ok=True)
        self.playwright: Optional[Playwright] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

    def start(self):
        """Launches the persistent Playwright browser context."""
        logger.info(f"Starting Playwright Chromium browser (Profile: {self.profile_dir}, Headless: {self.config.headless})...")
        self.playwright = sync_playwright().start()
        
        args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-infobars"
        ]

        try:
            logger.info("Attempting to launch browser with channel='chrome'...")
            self.context = self.playwright.chromium.launch_persistent_context(
                user_data_dir=self.profile_dir,
                channel="chrome",
                headless=self.config.headless,
                viewport={"width": 1280, "height": 900},
                args=args,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
            )
            logger.info("Launched successfully with channel='chrome'.")
        except Exception as exc:
            logger.warning(f"Could not launch with channel='chrome': {exc}. Falling back to default Chromium...")
            self.context = self.playwright.chromium.launch_persistent_context(
                user_data_dir=self.profile_dir,
                headless=self.config.headless,
                viewport={"width": 1280, "height": 900},
                args=args,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
            )

        self.context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        pages = self.context.pages
        self.page = pages[0] if pages else self.context.new_page()
        logger.info("Browser launched successfully.")

    def navigate_to_watchlist(self) -> bool:
        """Navigates to the configured Investing.com watchlist URL with retries."""
        if not self.page:
            logger.error("Browser page is not initialized.")
            return False

        url = self.config.investing_url
        logger.info(f"Navigating to Investing.com watchlist: {url}")
        
        try:
            res = self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
            status = res.status if res else 'Unknown'
            logger.info(f"Watchlist page loaded. HTTP Status: {status}")
            self._handle_popups()
            return True
        except PlaywrightTimeoutError:
            logger.warning("Timeout navigating to Investing.com. Retrying reload...")
            try:
                res = self.page.reload(wait_until="domcontentloaded", timeout=30000)
                self._handle_popups()
                return True
            except Exception as e:
                logger.error(f"Failed to load watchlist page: {e}")
                return False
        except Exception as e:
            logger.error(f"Error navigating to watchlist: {e}")
            return False

    def _handle_popups(self):
        """Attempts to accept cookie consent banners or close popups if present."""
        if not self.page:
            return
        
        consent_selectors = [
            "button#onetrust-accept-btn-handler",
            "button:has-text('Accept')",
            "button:has-text('I Agree')",
            "button:has-text('Allow all')",
            "div.banner-actions-container button",
            "svg[data-test='popup-close-icon']"
        ]

        for selector in consent_selectors:
            try:
                elem = self.page.query_selector(selector)
                if elem and elem.is_visible():
                    logger.info(f"Dismissing banner/popup with selector: {selector}")
                    elem.click(timeout=3000)
                    time.sleep(0.5)
            except Exception:
                pass

    def _extract_direct_instruments(self) -> List[Dict[str, Any]]:
        """Fallback extractor: fetches live market data directly from public instrument pages."""
        logger.info("Running direct public instrument fallback extractor...")
        rows = []

        for name, url in TARGET_INSTRUMENT_URLS.items():
            try:
                res = self.page.goto(url, wait_until="domcontentloaded", timeout=15000)
                if res and res.status == 200:
                    data = self.page.evaluate("""
                        () => {
                            const lastElem = document.querySelector('[data-test="instrument-price-last"], .instrument-price_last__KQA2y, #last_last');
                            const changeElem = document.querySelector('[data-test="instrument-price-change"], #data_change');
                            const changePctElem = document.querySelector('[data-test="instrument-price-change-percent"], #data_change_perc');
                            
                            // High / Low bounds
                            const highElem = document.querySelector('[data-test="high-value"], #high_val');
                            const lowElem = document.querySelector('[data-test="low-value"], #low_val');
                            const openElem = document.querySelector('[data-test="open-value"], #open_val');
                            const timeElem = document.querySelector('[data-test="instrument-time"], #quotes_summary_secondary_data_last_time');

                            return {
                                last: lastElem ? lastElem.innerText.trim() : null,
                                change: changeElem ? changeElem.innerText.trim() : null,
                                changePct: changePctElem ? changePctElem.innerText.trim() : null,
                                high: highElem ? highElem.innerText.trim() : null,
                                low: lowElem ? lowElem.innerText.trim() : null,
                                open: openElem ? openElem.innerText.trim() : null,
                                time: timeElem ? timeElem.innerText.trim() : null
                            };
                        }
                    """)

                    if data and data.get("last"):
                        rows.append({
                            "Name": name,
                            "Symbol": name if "EUR" in name or "USD" in name else "NSEI",
                            "Last": data.get("last"),
                            "Open": data.get("open") or data.get("last"),
                            "High": data.get("high") or data.get("last"),
                            "Low": data.get("low") or data.get("last"),
                            "Change": data.get("change"),
                            "Change %": data.get("changePct"),
                            "Volume": None,
                            "Market Time": data.get("time") or time.strftime("%H:%M:%S")
                        })
            except Exception as e:
                logger.warning(f"Direct fetch for '{name}' notice: {e}")

        cleaned = [clean_watchlist_row(r, self.config.timezone) for r in rows]
        return cleaned

    def extract_watchlist_rows(self) -> List[Dict[str, Any]]:
        """
        Dynamically extracts visible rows from the Investing.com watchlist table.
        Falls back to direct instrument scraping if watchlist page is restricted.
        """
        if not self.page:
            logger.error("Page is not initialized.")
            return []

        try:
            self._handle_popups()

            extracted_raw_rows = self.page.evaluate("""
                () => {
                    const tables = Array.from(document.querySelectorAll('table'));
                    let targetTable = null;

                    for (const table of tables) {
                        const text = table.innerText || '';
                        if (text.includes('Last') || text.includes('Chg') || text.includes('High') || text.includes('Price')) {
                            targetTable = table;
                            break;
                        }
                    }

                    if (targetTable) {
                        const headerCells = Array.from(targetTable.querySelectorAll('th, tr:first-child td'));
                        const headers = headerCells.map(c => c.innerText.trim());

                        const bodyRows = Array.from(targetTable.querySelectorAll('tbody tr, tr')).filter(r => r.querySelectorAll('td').length > 0);

                        return bodyRows.map(row => {
                            const cells = Array.from(row.querySelectorAll('td'));
                            const rowData = {};

                            cells.forEach((cell, idx) => {
                                const headerName = headers[idx] || `col_${idx}`;
                                rowData[headerName] = cell.innerText.trim();
                            });

                            const symbolAttr = row.getAttribute('data-symbol') || 
                                             row.getAttribute('data-pair-symbol') || 
                                             (row.querySelector('[data-symbol]') ? row.querySelector('[data-symbol]').getAttribute('data-symbol') : null);

                            if (symbolAttr) {
                                rowData['Symbol'] = symbolAttr;
                            } else if (!rowData['Symbol']) {
                                const nameCell = row.querySelector('td a') || row.querySelector('td');
                                if (nameCell) {
                                    const link = row.querySelector('a');
                                    if (link && link.getAttribute('title')) {
                                        rowData['Symbol'] = link.getAttribute('title').trim();
                                    } else {
                                        rowData['Symbol'] = (rowData['Name'] || rowData[headers[0]] || '').trim();
                                    }
                                }
                            }

                            headers.forEach((h, idx) => {
                                const val = cells[idx] ? cells[idx].innerText.trim() : '';
                                const hLower = h.toLowerCase();
                                if (hLower.includes('name') || hLower.includes('pair') || hLower.includes('instrument')) rowData['Name'] = val;
                                else if (hLower.includes('symbol') || hLower.includes('ticker')) rowData['Symbol'] = val;
                                else if (hLower.includes('last') || hLower.includes('price')) rowData['Last'] = val;
                                else if (hLower.includes('open')) rowData['Open'] = val;
                                else if (hLower.includes('high')) rowData['High'] = val;
                                else if (hLower.includes('low')) rowData['Low'] = val;
                                else if (hLower.includes('chg.%') || hLower.includes('chg %') || hLower.includes('change %')) rowData['Change %'] = val;
                                else if (hLower.includes('change') || hLower.includes('chg')) rowData['Change'] = val;
                                else if (hLower.includes('vol')) rowData['Volume'] = val;
                                else if (hLower.includes('time') || hLower.includes('date')) rowData['Market Time'] = val;
                            });

                            return rowData;
                        }).filter(r => (r.Name || r.Symbol) && (r.Last !== undefined));
                    }

                    const items = Array.from(document.querySelectorAll('[data-test="watchlist-table-row"], [class*="table-row"], [data-test="watchlist-row"]'));
                    return items.map(item => {
                        const text = item.innerText.split('\\n').map(s => s.trim()).filter(Boolean);
                        if (text.length >= 3) {
                            return {
                                'Name': text[0],
                                'Symbol': text[1] || text[0],
                                'Last': text[2] || '',
                                'Change': text[3] || '',
                                'Change %': text[4] || '',
                                'High': text[5] || '',
                                'Low': text[6] || '',
                                'Volume': text[7] || '',
                                'Market Time': text[8] || ''
                            };
                        }
                        return null;
                    }).filter(Boolean);
                }
            """)

            if extracted_raw_rows:
                cleaned_rows = [clean_watchlist_row(row, self.config.timezone) for row in extracted_raw_rows]
                logger.info(f"Extracted {len(cleaned_rows)} instruments from watchlist table.")
                return cleaned_rows
            else:
                # If watchlist table returned 0 rows (e.g. 403 on cloud server), run direct public fallback
                return self._extract_direct_instruments()

        except Exception as exc:
            logger.error(f"Error during watchlist data extraction: {exc}")
            return self._extract_direct_instruments()

    def close(self):
        """Closes the browser context and stops Playwright."""
        logger.info("Closing Playwright browser...")
        try:
            if self.context:
                self.context.close()
            if self.playwright:
                self.playwright.stop()
        except Exception as exc:
            logger.warning(f"Error during Playwright browser shutdown: {exc}")
        logger.info("Playwright shutdown complete.")
