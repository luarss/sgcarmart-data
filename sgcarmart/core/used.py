"""
SGCarMart used car scraper — HTTP (primary) and Playwright (fallback).

Primary path: fetch the Next.js page HTML and parse the RSC payload that
the server embeds server-side. No browser required, works as long as
Cloudflare serves the cached page.

Playwright path: kept for detail pages and as a fallback if the HTTP path
stops working (e.g. Cloudflare starts JS-challenging all requests).
"""

import os
import re
import time
import json
import urllib.request
from dataclasses import dataclass, field
from urllib.parse import urlencode, urljoin

from playwright.sync_api import Page, sync_playwright
from playwright_stealth import Stealth

from sgcarmart.constants import BASE_URL

LISTING_URL = f"{BASE_URL}/used-cars/listing"
DETAIL_URL = f"{BASE_URL}/used-cars/info"

# ── HTTP scraping (primary) ──────────────────────────────────────────────────

_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}


def _fetch_html(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers=_HTTP_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def _parse_rsc_listings(html: str) -> list[dict]:
    """Extract the listing_data.data array from the Next.js RSC payload."""
    chunks = re.findall(
        r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)',
        html,
        re.DOTALL,
    )
    all_decoded = "\n".join(json.loads('"' + chunk + '"') for chunk in chunks)

    m = re.search(r'"listing_data":\{"data":\[', all_decoded)
    if not m:
        return []

    # Walk forward to find the matching closing bracket.
    start = m.end()
    depth, pos = 1, start
    while pos < len(all_decoded) and depth > 0:
        if all_decoded[pos] == "[":
            depth += 1
        elif all_decoded[pos] == "]":
            depth -= 1
        pos += 1

    try:
        return json.loads("[" + all_decoded[start : pos - 1] + "]")
    except json.JSONDecodeError:
        return []


def _rsc_item_to_dict(item: dict) -> dict:
    """Map one RSC listing object to the canonical snapshot dict."""
    eng_cap_str = item.get("engine_capacity") or ""
    road_tax = None
    m = re.search(r"([\d,]+)", eng_cap_str)
    if m:
        try:
            road_tax = compute_road_tax(int(m.group(1).replace(",", "")))
        except Exception:
            pass

    tag = (item.get("tag") or "").upper()
    instalment_info = item.get("instalment") or {}
    instalment_amt = instalment_info.get("installment")
    instalment = f"${instalment_amt:,} /mth" if instalment_amt else None

    mileage = item.get("mileage") or None
    if mileage in ("N.A", "N.A."):
        mileage = None

    owners = item.get("owners") or None
    if owners in ("N.A", "N.A."):
        owners = None

    dealer_info = item.get("dealer_lead") or {}

    return {
        "id": str(item["id"]),
        "title": item.get("car_model", ""),
        "url": item.get("link", ""),
        "price": item.get("price"),
        "instalment": instalment,
        "depreciation": item.get("depreciation"),
        "reg_date": item.get("registration_date"),
        "coe_left": item.get("coeLeft") or None,
        "mileage": mileage,
        "eng_cap": eng_cap_str or None,
        "road_tax": road_tax,
        "owners": owners,
        "is_direct_owner": "DIRECT" in tag,
        "is_premium_ad": "PREMIUM" in tag or item.get("ad_type") == "p",
        "is_import_used": (item.get("additional_statuses") or {}).get("is_imported_used", False),
        "dealer": dealer_info.get("name"),
        "posted_date": item.get("date"),
        "description": item.get("description", ""),
    }


def fetch_all_listings_http(
    filters: dict,
    max_pages: int = 50,
    rate_limit: float = 0.3,
) -> dict[str, dict]:
    """Fetch listings across pages via HTTP, returning a dict keyed by listing ID.

    Raises on network failure so the caller can decide how to handle it.
    Returns an empty dict (not raises) when the page loads but RSC has no data.
    """
    params = {}
    for key, value in filters.items():
        if key in SEARCH_PARAMS and value is not None:
            param_name = SEARCH_PARAMS[key]
            if isinstance(value, list):
                params[param_name] = [str(v) for v in value]
            else:
                params[param_name] = str(value)

    base_url = f"{LISTING_URL}?{urlencode(params, doseq=True)}"
    results: dict[str, dict] = {}

    for page in range(1, max_pages + 1):
        url = base_url if page == 1 else f"{base_url}&page={page}"
        html = _fetch_html(url)
        items = _parse_rsc_listings(html)
        if not items:
            print(f"HTTP: no RSC listings on page {page}, stopping.")
            break
        for item in items:
            d = _rsc_item_to_dict(item)
            results[d["id"]] = d
        print(f"HTTP: page {page} → {len(items)} listings (total so far: {len(results)})")
        if len(items) < int(filters.get("limit", 100)):
            break
        if page < max_pages:
            time.sleep(rate_limit)

    return results

_PROXY_SERVER = os.environ.get("PROXY_SERVER")

# Comma-separated fallback proxies to rotate through on failure.
# Cap at 10 to bound worst-case wait time (30 s × 10 = 5 min max).
_MAX_PROXY_ATTEMPTS = 10
_PROXY_FALLBACKS = [
    p.strip()
    for p in os.environ.get("PROXY_FALLBACKS", "").split(",")
    if p.strip()
][:_MAX_PROXY_ATTEMPTS]

_BADGE_FLAGS = {"PREMIUM AD", "DIRECT OWNER", "IMPORT USED"}

# LTA road tax formula for petrol cars (6-monthly base, multiply by 2 for annual).
# Source: https://onemotoring.lta.gov.sg/content/onemotoring/home/buying/upfront-vehicle-costs/tax-structure.html
_ROAD_TAX_MULTIPLIER = 0.782


def compute_road_tax(eng_cap_cc: int) -> int | None:
    """Compute annual road tax for a petrol car from engine capacity (cc)."""
    if eng_cap_cc <= 600:
        base = 200
    elif eng_cap_cc <= 1000:
        base = 200 + 0.125 * (eng_cap_cc - 600)
    elif eng_cap_cc <= 1600:
        base = 250 + 0.375 * (eng_cap_cc - 1000)
    elif eng_cap_cc <= 3000:
        base = 475 + 0.75 * (eng_cap_cc - 1600)
    else:
        base = 1525 + 1.0 * (eng_cap_cc - 3000)
    semi_annual = base * _ROAD_TAX_MULTIPLIER
    return round(semi_annual * 2)

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
    road_tax: int | None = None
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
        # Build candidate list: [None (direct), proxy1, proxy2, ...].
        # Always start with a direct attempt; proxies are fallbacks.
        candidates: list[str | None] = [None, *[p for p in [_PROXY_SERVER, *_PROXY_FALLBACKS] if p]]
        last_error = None
        for i, proxy in enumerate(candidates):
            label = proxy or "direct"
            try:
                if self._try_navigate_with_proxy(url, proxy, i):
                    return self.page.url
                if i < len(candidates) - 1:
                    print(f"Navigation via {label} loaded page but 0 listings, trying next...")
                    continue
                return self.page.url
            except Exception as e:
                last_error = e
                if i < len(candidates) - 1:
                    print(f"Navigation via {label} failed ({e}), trying next...")
                    continue
        if last_error:
            raise last_error
        return self.page.url

    def _try_navigate_with_proxy(self, url: str, proxy: str | None, attempt: int) -> bool:
        if attempt > 0:
            print(f"Retrying with proxy: {proxy}")
            self._restart_with_proxy(proxy)
        self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
        try:
            self.page.wait_for_selector('[class*="listing_box"]', timeout=15000)
        except Exception:
            pass
        return bool(self.get_listings())

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
        cards = self.page.locator('[class*="listing_box"][class*="flex_content"]').all()

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

        url = self._extract_card_url(card)
        fields = self._parse_listing_lines(lines)

        eng_cap = fields["eng_cap"]
        road_tax = None
        if eng_cap:
            m = re.search(r"([\d,]+)", eng_cap)
            if m:
                road_tax = compute_road_tax(int(m.group(1).replace(",", "")))

        return UsedCarListing(
            title=fields["title"],
            url=url,
            price=fields["price"],
            instalment=fields["instalment"],
            depreciation=fields["depreciation"],
            reg_date=fields["reg_date"],
            coe_left=fields["coe_left"],
            mileage=fields["mileage"],
            eng_cap=eng_cap,
            road_tax=road_tax,
            owners=fields["owners"],
            is_direct_owner=fields["is_direct"],
            is_premium_ad=fields["is_premium"],
            is_import_used=fields["is_import"],
            dealer=fields["dealer"],
            posted_date=fields["posted_date"],
            description=" ".join(fields["desc_parts"]),
        )

    def _extract_card_url(self, card) -> str:
        link = card.locator('a[href*="/info/"]').first
        try:
            href = link.get_attribute("href", timeout=500)
            return urljoin(BASE_URL, href) if href else ""
        except Exception:
            return ""

    def _parse_listing_lines(self, lines: list[str]) -> dict:
        fields = {
            "title": "",
            "price": None,
            "instalment": None,
            "depreciation": None,
            "reg_date": None,
            "coe_left": None,
            "mileage": None,
            "eng_cap": None,
            "owners": None,
            "dealer": None,
            "posted_date": None,
            "is_premium": False,
            "is_direct": False,
            "is_import": False,
            "desc_parts": [],
        }

        for line in lines:
            if self._try_parse_badge(line, fields):
                continue
            if self._try_parse_title(line, fields):
                continue
            if self._try_parse_financial(line, fields):
                continue
            if self._try_parse_reg_date(line, fields):
                continue
            if self._try_parse_vehicle_attrs(line, fields):
                continue
            if self._try_parse_dealer(line, fields):
                continue
            if self._try_parse_posted_date(line, fields):
                continue
            if fields["title"] and line != fields["title"]:
                fields["desc_parts"].append(line)

        if fields["price"] is None:
            fields["price"] = self._fallback_price(lines)

        return fields

    def _try_parse_badge(self, line: str, fields: dict) -> bool:
        if line == "Compare":
            return True
        if line not in _BADGE_FLAGS:
            return False
        if line == "PREMIUM AD":
            fields["is_premium"] = True
        elif line == "DIRECT OWNER":
            fields["is_direct"] = True
        elif line == "IMPORT USED":
            fields["is_import"] = True
        return True

    def _try_parse_title(self, line: str, fields: dict) -> bool:
        if not fields["title"]:
            fields["title"] = line
            return True
        return False

    def _try_parse_financial(self, line: str, fields: dict) -> bool:
        if line.startswith("Instl."):
            fields["instalment"] = line.replace("Instl. ", "")
            return True
        if line.endswith("/yr") and line.startswith("$"):
            fields["depreciation"] = self._parse_int(line)
            return True
        if line.startswith("$") and not fields["instalment"] and fields["price"] is None:
            fields["price"] = self._parse_int(line)
            return True
        return False

    def _try_parse_reg_date(self, line: str, fields: dict) -> bool:
        if re.match(r"^\d{1,2}-[A-Z][a-z]{2}-\d{4}$", line) and not fields["reg_date"]:
            fields["reg_date"] = line
            return True
        if "COE left" in line:
            fields["coe_left"] = line.strip("()")
            return True
        return False

    def _try_parse_vehicle_attrs(self, line: str, fields: dict) -> bool:
        if re.match(r"^[\d,]+ km$", line) or line == "N.A":
            if not fields["mileage"]:
                fields["mileage"] = None if line == "N.A" else line
            return True
        if re.match(r"^[\d,]+ cc$", line):
            fields["eng_cap"] = line
            return True
        if re.match(r"^\d+ Owner", line) or re.match(r"^More than \d+", line):
            fields["owners"] = line
            return True
        return False

    def _try_parse_posted_date(self, line: str, fields: dict) -> bool:
        if line.startswith("Posted "):
            fields["posted_date"] = line.replace("Posted ", "")
            return True
        return False

    def _try_parse_dealer(self, line: str, fields: dict) -> bool:
        if "|" in line and len(line) < 40:
            fields["dealer"] = line.replace("|", "").strip()
            return True
        if "Pte Ltd" in line or "Ltd" in line:
            fields["dealer"] = line
            return True
        return False

    def _fallback_price(self, lines: list[str]) -> int | None:
        for line in lines:
            if line.startswith("$") and "/yr" not in line and "Instl." not in line:
                return self._parse_int(line)
        return None

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
        title = page.locator("h1, [class*='title']").first.inner_text().strip()
        url = page.url
        text = page.inner_text("body")

        api_data: dict = {}
        try:
            aid_match = re.search(r"(\d{6,})", url)
            if aid_match:
                aid = aid_match.group(1)
                api_url = f"{BASE_URL}/used-cars/api/info/deregistration-value?aid={aid}&date=2026-05-23"
                resp = page.evaluate(f"fetch('{api_url}').then(r => r.json())")
                api_data = resp.get("data", {}).get("data", {})
        except Exception:
            pass

        return UsedCarDetail(
            title=title,
            url=url,
            price=self._parse_int(text),
            reg_date=self._extract_re(text, r"(\d{1,2}-[A-Z][a-z]{2}-\d{4})"),
            mileage=self._extract_re(text, r"([\d,]+ km)"),
            eng_cap=self._extract_re(text, r"([\d,]+ cc)"),
            coe=api_data.get("coe"),
            omv=self._extract_field(text, r"OMV\b[:\s]*\$?([\d,]+)"),
            arf=api_data.get("arf"),
            dereg_value=api_data.get("deregValue_today"),
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
            el = page.locator("[class*='description'], [class*='sellerComment']").first
            return el.inner_text().strip()
        except Exception:
            return ""

    def _extract_features(self, page: Page) -> list[str]:
        try:
            els = page.locator("[class*='feature'] li, [class*='accessory'] li").all()
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
