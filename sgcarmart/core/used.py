"""
Playwright helper for browsing and extracting SGCarMart used car listings.
"""

import os
import re
import time
from dataclasses import dataclass, field
from urllib.parse import urlencode, urljoin

from playwright.sync_api import Page, sync_playwright
from playwright_stealth import Stealth

from constants import BASE_URL

LISTING_URL = f"{BASE_URL}/used-cars/listing"
DETAIL_URL = f"{BASE_URL}/used-cars/info"

_PROXY_SERVER = os.environ.get("PROXY_SERVER")

# Comma-separated fallback proxies to rotate through on failure
_PROXY_FALLBACKS = [
    p.strip() for p in os.environ.get("PROXY_FALLBACKS", "").split(",") if p.strip()
]

_BADGE_FLAGS = {"PREMIUM AD", "DIRECT OWNER", "IMPORT USED"}

# filter key → SGCarMart URL parameter name
SEARCH_PARAMS: dict[str, str] = {
    "min_price": "pr1",
    "max_price": "pr2",
    "year_from": "fr",
    "year_to": "to",
    "sort": "ord",
    "sortby": "sortby",
    "make": "MAK",
    "model": "MDL",
    "category": "CAT",
    "owners": "OWN",
    "coe_left": "COE",
    "avl": "avl",
    "limit": "limit",
    "vts": "vts[]",
}


@dataclass
class UsedCarListing:
    title: str
    url: str
    price: int | None = None
    instalment: str | None = None
    depreciation: int | None = None
    reg_date: str | None = None
    coe_left: str | None = None
    mileage: str | None = None
    eng_cap: str | None = None
    owners: str | None = None
    is_direct_owner: bool = False
    is_premium_ad: bool = False
    is_import_used: bool = False
    dealer: str | None = None
    posted_date: str | None = None
    description: str = ""


@dataclass
class UsedCarDetail:
    title: str
    url: str
    price: int | None = None
    reg_date: str | None = None
    mileage: str | None = None
    eng_cap: str | None = None
    coe: str | None = None
    omv: str | None = None
    arf: str | None = None
    dereg_value: str | None = None
    road_tax: str | None = None
    no_of_owners: str | None = None
    description: str = ""
    features: list[str] = field(default_factory=list)


class UsedCarSearch:
    """Search used car listings with filters and extract structured results."""

    def __init__(self, headless: bool = True, timeout: int = 30000):
        self.headless = headless
        self.timeout = timeout
        self.browser = None
        self.context = None
        self.page: Page | None = None
        self.playwright = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def _make_proxy(self, server: str | None = None) -> dict | None:
        s = server or _PROXY_SERVER
        return {"server": s} if s else None

    def start(self, proxy_server: str | None = None):
        self.playwright = sync_playwright().start()
        proxy = self._make_proxy(proxy_server)
        self.browser = self.playwright.chromium.launch(
            headless=self.headless,
            proxy=proxy,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        self.context = self.browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            )
        )
        Stealth().apply_stealth_sync(self.context)
        self.page = self.context.new_page()
        self.page.set_default_timeout(self.timeout)

    def _restart_with_proxy(self, proxy_server: str) -> None:
        self.close()
        self.start(proxy_server=proxy_server)

    def close(self):
        if self.page:
            self.page.close()
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()

    # -- search / navigation --

    def search(self, **filters) -> str:
        """Build and navigate to the listing URL with filters.

        Supported filters:
            min_price / max_price: int — maps to pr1 / pr2
            year_from / year_to: int — maps to fr / to
            sort: str — 'PRC_ASC', 'PRC_DSC', 'REG_DSC'
            make: str — brand name
            model: str — model name
            category: str — vehicle type
            owners: str — owner count filter
            coe_left: str — COE remaining filter

        Returns the navigated URL.
        """
        params = self._build_params(filters)
        url = f"{LISTING_URL}?{urlencode(params, doseq=True)}" if params else LISTING_URL
        return self._navigate(url)

    def _navigate(self, url: str) -> str:
        proxies = [p for p in [_PROXY_SERVER, *_PROXY_FALLBACKS] if p]
        last_error = None
        for i, proxy in enumerate(proxies or [None]):
            try:
                if i > 0:
                    print(f"Retrying with proxy: {proxy}")
                    self._restart_with_proxy(proxy)
                self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
                try:
                    self.page.wait_for_selector(
                        '[class*="listing_box"]',
                        timeout=15000,
                    )
                except Exception:
                    pass
                # Verify listings actually rendered (not geo-blocked)
                if self.get_listings():
                    return self.page.url
                if i < len(proxies) - 1:
                    print(f"Proxy loaded page but 0 listings, trying next...")
                    continue
                return self.page.url
            except Exception as e:
                last_error = e
                if i < len(proxies) - 1:
                    print(f"Proxy failed ({e}), trying next...")
                    continue
        if last_error and proxies:
            raise last_error
        return self.page.url

    def _build_params(self, filters: dict) -> dict:
        params = {}
        for key, value in filters.items():
            if key in SEARCH_PARAMS and value is not None:
                param_name = SEARCH_PARAMS[key]
                if isinstance(value, list):
                    params[param_name] = [str(v) for v in value]
                else:
                    params[param_name] = str(value)
        return params

    # -- listing parsing --

    def get_listings(self) -> list[UsedCarListing]:
        """Parse all listing cards on the current page."""
        cards = self.page.locator(
            '[class*="listing_box"][class*="flex_content"]'
        ).all()

        results = []
        for card in cards:
            try:
                listing = self._parse_card(card)
                if listing and listing.title:
                    results.append(listing)
            except Exception:
                continue

        return results

    def _parse_card(self, card) -> UsedCarListing | None:
        text = card.inner_text()
        lines = [l.strip() for l in text.split("\n") if l.strip()]

        # Extract detail URL from the title link
        url = ""
        link = card.locator('a[href*="/info/"]').first
        try:
            href = link.get_attribute("href", timeout=500)
            url = urljoin(BASE_URL, href) if href else ""
        except Exception:
            pass

        # Parse line-by-line
        title = ""
        price = None
        instalment = None
        depreciation = None
        reg_date = None
        coe_left = None
        mileage = None
        eng_cap = None
        owners = None
        dealer = None
        posted_date = None
        is_premium = False
        is_direct = False
        is_import = False
        desc_parts = []
        in_description = False

        for line in lines:
            if line == "Compare":
                continue

            if line in _BADGE_FLAGS:
                if line == "PREMIUM AD":
                    is_premium = True
                elif line == "DIRECT OWNER":
                    is_direct = True
                elif line == "IMPORT USED":
                    is_import = True
                continue

            # Title: first non-badge line that isn't a price/number
            if not title:
                title = line
                continue

            # Instalment line
            if line.startswith("Instl."):
                instalment = line.replace("Instl. ", "")
                continue

            # Depreciation (ends with /yr)
            if line.endswith("/yr") and line.startswith("$"):
                depreciation = self._parse_int(line)
                continue

            # Price (starts with $, not /yr)
            if line.startswith("$") and not instalment and price is None:
                price = self._parse_int(line)
                continue

            # Registration date
            if re.match(r"^\d{1,2}-[A-Z][a-z]{2}-\d{4}$", line) and not reg_date:
                reg_date = line
                continue

            # COE left
            if "COE left" in line:
                coe_left = line.strip("()")
                continue

            # Mileage
            if re.match(r"^[\d,]+ km$", line) or line == "N.A":
                if not mileage:
                    mileage = None if line == "N.A" else line
                continue

            # Engine capacity
            if re.match(r"^[\d,]+ cc$", line):
                eng_cap = line
                continue

            # Owners
            if re.match(r"^\d+ Owner", line) or re.match(r"^More than \d+", line):
                owners = line
                continue

            # Posted date
            if line.startswith("Posted "):
                posted_date = line.replace("Posted ", "")
                in_description = False
                continue

            # Dealer name (line with "|" is dealer indicator, or line with "Pte Ltd")
            if "|" in line and len(line) < 40:
                dealer = line.replace("|", "").strip()
                continue

            if "Pte Ltd" in line or "Ltd" in line:
                dealer = line
                continue

            # Everything else after title and before posted date is description
            if title and line != title:
                desc_parts.append(line)

        # Re-derive price from depreciation as fallback (since actual price
        # appears _before_ instalment line in the card text order)
        if price is None:
            for line in lines:
                if line.startswith("$") and "/yr" not in line and "Instl." not in line:
                    price = self._parse_int(line)
                    break

        return UsedCarListing(
            title=title,
            url=url,
            price=price,
            instalment=instalment,
            depreciation=depreciation,
            reg_date=reg_date,
            coe_left=coe_left,
            mileage=mileage,
            eng_cap=eng_cap,
            owners=owners,
            is_direct_owner=is_direct,
            is_premium_ad=is_premium,
            is_import_used=is_import,
            dealer=dealer,
            posted_date=posted_date,
            description=" ".join(desc_parts),
        )

    @staticmethod
    def _parse_int(text: str) -> int | None:
        m = re.search(r"\$?([\d,]+)", text)
        return int(m.group(1).replace(",", "")) if m else None

    # -- pagination --

    def next_page(self) -> bool:
        """Navigate to next page. Returns False if no more pages."""
        if not self.has_next_page():
            return False

        current = self._current_page_number()
        next_num = current + 1

        # Build the next-page URL directly and navigate via _navigate() so
        # proxy retry logic applies (clicking triggers a navigation that the
        # proxy may stall on, causing a 30 s timeout).
        current_url = self.page.url
        if re.search(r"[?&]page=\d+", current_url):
            next_url = re.sub(r"(page=)\d+", f"\\g<1>{next_num}", current_url)
        elif "?" in current_url:
            next_url = f"{current_url}&page={next_num}"
        else:
            next_url = f"{current_url}?page={next_num}"

        self._navigate(next_url)
        return True

    def _current_page_number(self) -> int:
        # Parse from URL query parameter
        m = re.search(r"[?&]page=(\d+)", self.page.url)
        if m:
            return int(m.group(1))
        return 1

    def has_next_page(self) -> bool:
        next_btn = self.page.locator("a:has-text('Next'), button:has-text('Next')").first
        if next_btn.is_visible() and next_btn.is_enabled():
            return True
        current = self._current_page_number()
        page_items = self.page.locator(".page-item a, [class*='page-item'] a").all()
        for link in page_items:
            try:
                n = int(link.inner_text().strip())
                if n == current + 1:
                    return True
            except Exception:
                continue
        return False

    # -- detail page --

    def get_detail(self, url_or_id: str) -> UsedCarDetail | None:
        """Fetch a car detail page and extract structured data."""
        if url_or_id.startswith("http"):
            url = url_or_id
        else:
            url = f"{DETAIL_URL}/car-{url_or_id}"

        self.page.goto(url, wait_until="domcontentloaded")
        time.sleep(1)

        try:
            return self._parse_detail()
        except Exception as e:
            print(f"Error parsing detail: {e}")
            return None

    def _parse_detail(self) -> UsedCarDetail:
        page = self.page
        title = (
            page.locator("h1, [class*='title']").first.inner_text().strip()
        )
        url = page.url
        text = page.inner_text("body")

        # Deregistration value from the API
        dereg_value = None
        try:
            aid_match = re.search(r"(\d{6,})", url)
            if aid_match:
                aid = aid_match.group(1)
                api_url = (
                    f"{BASE_URL}/used-cars/api/info/deregistration-value"
                    f"?aid={aid}&date=2026-05-23"
                )
                resp = page.evaluate(
                    f"fetch('{api_url}').then(r => r.json())"
                )
                dereg_value = (
                    resp.get("data", {}).get("data", {}).get("deregValue_today")
                )
        except Exception:
            pass

        return UsedCarDetail(
            title=title,
            url=url,
            price=self._parse_int(text),
            reg_date=self._extract_re(text, r"(\d{1,2}-[A-Z][a-z]{2}-\d{4})"),
            mileage=self._extract_re(text, r"([\d,]+ km)"),
            eng_cap=self._extract_re(text, r"([\d,]+ cc)"),
            coe=self._extract_field(text, r"COE\b[:\s]*\$?([\d,]+)"),
            omv=self._extract_field(text, r"OMV\b[:\s]*\$?([\d,]+)"),
            arf=self._extract_field(text, r"ARF\b[:\s]*\$?([\d,]+)"),
            dereg_value=dereg_value,
            road_tax=self._extract_field(text, r"Road Tax\b[:\s]*\$?([\d,]+)"),
            no_of_owners=self._extract_re(text, r"(\d+ Owner)"),
            description=self._extract_description(page),
            features=self._extract_features(page),
        )

    def _extract_re(self, text: str, pattern: str) -> str | None:
        m = re.search(pattern, text)
        return m.group(1) if m else None

    def _extract_field(self, text: str, pattern: str) -> str | None:
        m = re.search(pattern, text)
        return f"${m.group(1)}" if m else None

    def _extract_description(self, page: Page) -> str:
        try:
            el = page.locator(
                "[class*='description'], [class*='sellerComment']"
            ).first
            return el.inner_text().strip()
        except Exception:
            return ""

    def _extract_features(self, page: Page) -> list[str]:
        try:
            els = page.locator(
                "[class*='feature'] li, [class*='accessory'] li"
            ).all()
            return [e.inner_text().strip() for e in els if e.inner_text().strip()]
        except Exception:
            return []


# -- convenience functions --


def search_listings(**filters) -> list[UsedCarListing]:
    """One-shot: open browser, fetch one page of listings, close.

    Example:
        cars = search_listings(min_price=20000, max_price=40000, year_from=2020)
    """
    with UsedCarSearch(headless=True) as s:
        s.search(**filters)
        return s.get_listings()


def search_all_pages(max_pages: int = 20, **filters) -> list[UsedCarListing]:
    """Search across multiple pages."""
    results = []
    with UsedCarSearch(headless=True) as s:
        s.search(**filters)
        for _ in range(max_pages):
            listings = s.get_listings()
            if not listings:
                break
            results.extend(listings)
            if not s.next_page():
                break
    return results


def get_car_detail(url_or_id: str) -> UsedCarDetail | None:
    """Fetch detail for a single car listing."""
    with UsedCarSearch(headless=True) as s:
        return s.get_detail(url_or_id)
