"""
Simplified year navigation using direct PDF URL construction.
Based on the pattern: https://www.sgcarmart.com/new_cars/pricelist/{dealer_id}/{YYYY-MM-DD}.pdf
"""
from playwright.sync_api import sync_playwright
from typing import List, Dict
from datetime import datetime
import time
import re


class SimpleYearNavigator:
    """
    Simplified navigator that extracts date options and constructs PDF URLs directly.
    """

    def __init__(self, headless: bool = True, timeout: int = 15000):
        self.headless = headless
        self.timeout = timeout
        self.browser = None
        self.context = None
        self.page = None
        self.playwright = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def start(self):
        """Initialize browser context."""
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=self.headless)
        self.context = self.browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        self.page = self.context.new_page()
        self.page.set_default_timeout(self.timeout)

    def close(self):
        """Close browser context."""
        if self.page:
            self.page.close()
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()

    def parse_date_to_url_format(self, date_text: str) -> str:
        """
        Convert date text like '14 October 2024' to '2024-10-14'.

        Args:
            date_text: Date in format 'DD Month YYYY'

        Returns:
            Date in format 'YYYY-MM-DD'
        """
        try:
            dt = datetime.strptime(date_text, '%d %B %Y')
            return dt.strftime('%Y-%m-%d')
        except:
            return None

    def get_available_years(self, dealer_id: str, brand_name: str) -> List[str]:
        """Get all available years by parsing the year dropdown."""
        url = f"https://www.sgcarmart.com/new-cars/pricelists/{dealer_id}/{brand_name}"

        try:
            self.page.goto(url, wait_until="networkidle")
            time.sleep(2)

            year_selector = self.page.locator('[role="button"]:has-text("Select A Year")').first
            year_selector.click()
            time.sleep(1)

            all_divs = self.page.locator('div').all()
            years = []

            for div in all_divs:
                try:
                    text = div.inner_text(timeout=500).strip()
                    if text.isdigit() and len(text) == 4 and text.startswith('20'):
                        years.append(text)
                except:
                    continue

            self.page.keyboard.press("Escape")
            time.sleep(0.5)

            return sorted(set(years), reverse=True)

        except Exception as e:
            print(f"Error getting years: {e}")
            return []

    def get_pdfs_for_year(self, dealer_id: str, brand_name: str, year: str) -> List[Dict[str, str]]:
        """
        Get all PDFs for a specific year by extracting dates from dropdown.

        Returns:
            List of dicts with 'url', 'date', 'filename', 'year'
        """
        url = f"https://www.sgcarmart.com/new-cars/pricelists/{dealer_id}/{brand_name}"

        try:
            self.page.goto(url, wait_until="networkidle")
            time.sleep(2)

            year_selector = self.page.locator('[role="button"]:has-text("Select A Year")').first
            year_selector.click()
            time.sleep(1)

            all_divs = self.page.locator('div').all()
            year_elem = None
            for div in all_divs:
                try:
                    text = div.inner_text(timeout=500).strip()
                    if text == year:
                        year_elem = div
                        break
                except:
                    continue

            if not year_elem:
                print(f"Year {year} not found")
                return []

            year_elem.click()
            time.sleep(1.5)

            date_selector = self.page.locator('[role="button"]:has-text("Select Date of Pricelist")').first
            date_selector.click()
            time.sleep(1)

            all_text_elements = self.page.locator('div').all()
            date_texts = []

            for elem in all_text_elements:
                try:
                    text = elem.inner_text(timeout=500).strip()
                    if text and len(text) > 5 and len(text) < 50:
                        if re.match(r'^\d{2}\s+\w+\s+\d{4}$', text):
                            date_texts.append(text)
                except:
                    continue

            self.page.keyboard.press("Escape")
            time.sleep(0.5)

            pdfs = []
            for date_text in set(date_texts):
                url_date = self.parse_date_to_url_format(date_text)
                if url_date:
                    pdf_url = f"https://www.sgcarmart.com/new_cars/pricelist/{dealer_id}/{url_date}.pdf"
                    pdfs.append({
                        'url': pdf_url,
                        'date': url_date,
                        'filename': f"dealer_{dealer_id}_{url_date}.pdf",
                        'year': year,
                        'date_text': date_text
                    })

            return pdfs

        except Exception as e:
            print(f"Error getting PDFs for year {year}: {e}")
            return []

    def discover_all_pdfs(self, dealer_id: str, brand_name: str) -> Dict[str, List[Dict[str, str]]]:
        """
        Discover all available PDFs across all years for a dealer.

        Returns:
            Dict mapping years to lists of PDF info dicts
        """
        years = self.get_available_years(dealer_id, brand_name)

        if not years:
            print(f"No years found for dealer {dealer_id}")
            return {}

        print(f"Found {len(years)} years: {years}")

        all_pdfs = {}
        for year in years:
            print(f"\nProcessing year {year}...")
            pdfs = self.get_pdfs_for_year(dealer_id, brand_name, year)

            if pdfs:
                all_pdfs[year] = pdfs
                print(f"  Found {len(pdfs)} PDFs for {year}")
                for pdf in pdfs:
                    print(f"    - {pdf['date_text']} → {pdf['url']}")
            else:
                print(f"  No PDFs found for {year}")

            time.sleep(1)

        return all_pdfs


def discover_historical_pdfs(dealer_id: str, brand_name: str, headless: bool = True) -> Dict[str, List[Dict[str, str]]]:
    """
    Convenience function to discover all historical PDFs for a dealer.

    Args:
        dealer_id: Dealer ID
        brand_name: Brand name (URL-encoded, e.g., 'aston%20martin')
        headless: Run browser in headless mode

    Returns:
        Dict mapping years to lists of PDF info dicts
    """
    with SimpleYearNavigator(headless=headless) as navigator:
        return navigator.discover_all_pdfs(dealer_id, brand_name)
