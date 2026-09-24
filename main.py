import sys
import time
import signal
import logging

from utils import setup_logger, load_config, validate_config
from scraper import InvestingScraper
from google_sheets import GoogleSheetsClient

logger = setup_logger("investing_sync")

class RealTimeInvestingSyncApp:
    def __init__(self):
        self.config = load_config()
        self.scraper: InvestingScraper = None
        self.sheets_client: GoogleSheetsClient = None
        self.running = True

    def setup_signal_handlers(self):
        """Registers signal handlers for graceful shutdown on SIGINT and SIGTERM."""
        signal.signal(signal.SIGINT, self.handle_shutdown)
        signal.signal(signal.SIGTERM, self.handle_shutdown)

    def handle_shutdown(self, signum, frame):
        """Graceful shutdown logic."""
        logger.info("\n[SHUTDOWN] Shutdown signal received. Stopping application loop...")
        self.running = False

    def run(self):
        logger.info("==================================================")
        logger.info("Starting Investing.com -> Google Sheets Sync App")
        logger.info("==================================================")

        # 1. Validate Configuration
        errors = validate_config(self.config)
        if errors:
            logger.warning("Configuration Notice:")
            for err in errors:
                logger.warning(f"  - {err}")
            logger.info("Please set up your .env and credentials/service_account.json before proceeding with Google Sheets sync.")
            logger.info("The application will proceed to launch the browser to inspect Investing.com...")

        self.setup_signal_handlers()

        # 2. Google Sheets Client Setup
        self.sheets_client = GoogleSheetsClient(self.config)
        sheets_connected = False
        if not errors:
            sheets_connected = self.sheets_client.connect()
            if sheets_connected:
                self.sheets_client.setup_worksheets_and_formatting()
            else:
                logger.warning("Google Sheets connection could not be established. Scraped data will be logged locally.")

        # 3. Playwright Scraper Setup
        self.scraper = InvestingScraper(self.config)
        try:
            self.scraper.start()
        except Exception as exc:
            logger.critical(f"Failed to start Playwright browser: {exc}")
            sys.exit(1)

        # 4. Navigate to Watchlist
        nav_success = self.scraper.navigate_to_watchlist()
        if not nav_success:
            logger.warning("Initial navigation encountered an issue. Will retry in continuous monitoring loop.")

        logger.info(f"Starting continuous monitoring loop (Interval: {self.config.scrape_interval_seconds}s). Press CTRL+C to stop.")

        iteration = 0
        while self.running:
            iteration += 1
            loop_start = time.time()
            logger.info(f"--- [Pass #{iteration}] Extracting watchlist data ---")

            try:
                cleaned_rows = self.scraper.extract_watchlist_rows()

                if cleaned_rows:
                    logger.info(f"Successfully extracted {len(cleaned_rows)} instruments.")
                    
                    if sheets_connected:
                        sync_ok = self.sheets_client.sync_data(cleaned_rows)
                        if sync_ok:
                            logger.info("Google Sheets sync completed successfully.")
                        else:
                            logger.warning("Google Sheets sync encountered errors.")
                    else:
                        logger.info(f"Sample scraped row: {cleaned_rows[0]}")
                else:
                    logger.warning("No watchlist rows detected. Verifying page load state...")
                    # If watchlist page was lost or disconnected, attempt soft refresh
                    self.scraper.navigate_to_watchlist()

            except Exception as exc:
                logger.error(f"Unexpected error in scrape loop pass #{iteration}: {exc}")

            # Sleep for remainder of refresh interval
            elapsed = time.time() - loop_start
            sleep_needed = max(0.1, self.config.scrape_interval_seconds - elapsed)

            # Sleep in 0.5s chunks so shutdown is responsive
            sleep_end = time.time() + sleep_needed
            while self.running and time.time() < sleep_end:
                time.sleep(0.5)

        # Cleanup & Shutdown
        logger.info("Application loop stopped. Performing cleanup...")
        if self.scraper:
            self.scraper.close()
        logger.info("Clean shutdown completed. Goodbye.")

def main():
    app = RealTimeInvestingSyncApp()
    app.run()

if __name__ == "__main__":
    main()
