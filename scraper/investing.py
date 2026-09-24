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
    Playwright scraper using persistent browser tabs to continuously stream live Investing.com market data.
    """

    def __init__(self, config: Config):
        self.config = config
        self.profile_dir = os.path.abspath("playwright_profile")
        os.makedirs(self.profile_dir, exist_ok=True)
        self.playwright: Optional[Playwright] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.instrument_pages: Dict[str, Page] = {}

    def start(self):
        """Launches the persistent Playwright browser context and initializes streaming tabs."""
        logger.info(f"Starting Playwright Chromium browser (Profile: {self.profile_dir}, Headless: {self.config.headless})...")
        self.playwright = sync_playwright().start()
        
        args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-infobars"
        ]

        try:
            self.context = self.playwright.chromium.launch_persistent_context(
                user_data_dir=self.profile_dir,
                channel="chrome",
                headless=self.config.headless,
                viewport={"width": 1280, "height": 900},
                args=args,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
            )
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
        logger.info("Browser context initialized successfully.")

    def navigate_to_watchlist(self) -> bool:
        """Navigates main watchlist page and initializes persistent streaming tabs for 2-second extraction."""
        if not self.page:
            return False

        url = self.config.investing_url
        logger.info(f"Navigating main watchlist page: {url}")
        
        try:
            res = self.page.goto(url, wait_until="commit", timeout=12000)
            status = res.status if res else 'Unknown'
            logger.info(f"Watchlist page loaded. HTTP Status: {status}")
            self._handle_popups(self.page)
        except Exception as e:
            logger.warning(f"Main watchlist navigation notice: {e}")

        # Initialize persistent streaming tabs for target instruments
        self._init_instrument_tabs()
        return True

    def _init_instrument_tabs(self):
        """Opens persistent streaming tabs for target instruments if not already open."""
        if not self.context:
            return

        for name, url in TARGET_INSTRUMENT_URLS.items():
            if name not in self.instrument_pages or self.instrument_pages[name].is_closed():
                try:
                    logger.info(f"Opening persistent streaming tab for '{name}'...")
                    pg = self.context.new_page()
                    pg.goto(url, wait_until="commit", timeout=12000)
                    self.instrument_pages[name] = pg
                except Exception as exc:
                    logger.warning(f"Notice initializing tab for '{name}': {exc}")

    def _handle_popups(self, target_page: Page):
        """Attempts to accept cookie consent banners or close popups if present."""
        if not target_page or target_page.is_closed():
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
                elem = target_page.query_selector(selector)
                if elem and elem.is_visible():
                    elem.click(timeout=2000)
                    time.sleep(0.3)
            except Exception:
                pass

    def _extract_direct_instruments(self) -> List[Dict[str, Any]]:
        """Instantaneous streaming extractor: evaluates DOM state on open persistent tabs in <10ms."""
        rows = []
        self._init_instrument_tabs()

        for name, pg in self.instrument_pages.items():
            if not pg or pg.is_closed():
                continue
            try:
                # Ensure price node is present
                try:
                    pg.wait_for_selector('[data-test="instrument-price-last"], [class*="instrument-price_last"], #last_last, [class*="price-last"], [class*="price_last"], span[class*="text-2xl"]', timeout=3000)
                except Exception:
                    pass

                data = pg.evaluate("""
                    () => {
                        const lastElem = document.querySelector('[data-test="instrument-price-last"], [class*="instrument-price_last"], #last_last, [class*="price-last"], [class*="price_last"], span[class*="text-2xl"], div[class*="text-2xl"]');
                        const changeElem = document.querySelector('[data-test="instrument-price-change"], [class*="instrument-price_change"], #data_change, [class*="price-change"]');
                        const changePctElem = document.querySelector('[data-test="instrument-price-change-percent"], [class*="instrument-price_change-percent"], #data_change_perc, [class*="price-change-percent"]');
                        
                        const highElem = document.querySelector('[data-test="high-value"], #high_val, [class*="high-value"]');
                        const lowElem = document.querySelector('[data-test="low-value"], #low_val, [class*="low-value"]');
                        const openElem = document.querySelector('[data-test="open-value"], #open_val, [class*="open-value"]');
                        const timeElem = document.querySelector('[data-test="instrument-time"], #quotes_summary_secondary_data_last_time, [class*="instrument-time"]');

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
                logger.warning(f"Error evaluating tab '{name}': {e}")

        cleaned = [clean_watchlist_row(r, self.config.timezone) for r in rows]
        return cleaned

    def extract_watchlist_rows(self) -> List[Dict[str, Any]]:
        """
        Dynamically extracts visible rows from the Investing.com watchlist table or persistent streaming tabs.
        """
        if not self.page:
            return self._extract_direct_instruments()

        try:
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

                    return [];
                }
            """)

            if extracted_raw_rows:
                cleaned_rows = [clean_watchlist_row(row, self.config.timezone) for row in extracted_raw_rows]
                logger.info(f"Extracted {len(cleaned_rows)} instruments from watchlist table.")
                return cleaned_rows
            else:
                return self._extract_direct_instruments()

        except Exception as exc:
            logger.error(f"Error during watchlist extraction: {exc}")
            return self._extract_direct_instruments()

    def close(self):
        """Closes all streaming tabs and stops Playwright context."""
        logger.info("Closing Playwright browser and streaming tabs...")
        try:
            for pg in self.instrument_pages.values():
                if pg and not pg.is_closed():
                    pg.close()
            if self.context:
                self.context.close()
            if self.playwright:
                self.playwright.stop()
        except Exception as exc:
            logger.warning(f"Error during Playwright shutdown: {exc}")
        logger.info("Playwright shutdown complete.")
