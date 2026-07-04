"""
Certified Pre-Owned (CPO) car scraper for multiple Singapore dealers.

Sites scraped:
  Listing pages  : ic_preowned, eurokars, das_weltauto, toyota, dickson,
                   carchoice, sim_mee_motors
  Programme pages: cycle_carriage, skoda

Excluded (robots.txt non-compliant or unverifiable):
  tesla - robots.txt returns HTTP 403; cannot verify access permission
"""
import contextlib
import json
import os
import re
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime

from playwright.sync_api import Page, sync_playwright
from playwright_stealth import Stealth

from sgcarmart.constants import CPO_DEFAULT_MAX_WORKERS, CPO_OUTPUT_DIR, USER_AGENTS

# ─── Data model ───────────────────────────────────────────────────────────────


@dataclass
class CPOListing:
    source: str
    title: str
    url: str
    price: int | None = None
    mileage: str | None = None
    reg_date: str | None = None
    warranty: str | None = None
    brand: str | None = None
    model: str | None = None
    scraped_date: str = field(default_factory=lambda: date.today().isoformat())
    listing_type: str = "listing"
    raw: dict = field(default_factory=dict)


# ─── Shared helpers ───────────────────────────────────────────────────────────


def _parse_price(text: str | None) -> int | None:
    if not text:
        return None
    m = re.search(r"[\d,]+", text.replace("S$", "").replace("$", ""))
    return int(m.group().replace(",", "")) if m else None


def _parse_stock_item(card, source_id: str, base_url: str) -> "CPOListing | None":
    """Parse a .stock-item card (shared by Eurokars and Sime Darby scrapers)."""
    title_el = card.locator("a.si-title")
    title = title_el.get_attribute("title") or title_el.inner_text().strip()
    if not title:
        return None

    href = title_el.get_attribute("href")
    url = f"{base_url}{href}" if href and href.startswith("/") else href or base_url

    price_text = card.locator(".price-value").first.inner_text()

    reg_date_el = card.locator(".v_reg_date span")
    reg_date = reg_date_el.inner_text().strip() if reg_date_el.count() else None

    mileage = None
    for div in card.locator("a.si-myfeatures > div").all():
        text = div.inner_text()
        if "Mileage" in text or "km" in text.lower():
            span = div.locator("span")
            if span.count():
                mileage = span.inner_text().strip()
            break

    try:
        make = card.locator("a.si-title .make").inner_text().strip() or None
        model_text = card.locator("a.si-title .model").inner_text().strip() or None
    except Exception:
        make, model_text = None, None

    return CPOListing(
        source=source_id,
        title=title,
        url=url,
        price=_parse_price(price_text),
        mileage=mileage,
        reg_date=reg_date,
        brand=make,
        model=model_text,
    )


# ─── Base classes ─────────────────────────────────────────────────────────────


class CPOScraper(ABC):
    SOURCE_ID: str
    BASE_URL: str

    def __init__(self, headless: bool = True, timeout: int = 30000):
        self.headless = headless
        self.timeout = timeout
        self.page: Page | None = None
        self._playwright = None
        self._browser = None
        self._context = None

    def __enter__(self) -> "CPOScraper":
        self._start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self._close()

    def _start(self) -> None:
        import random

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=self.headless,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        self._context = self._browser.new_context(
            user_agent=random.choice(USER_AGENTS),
        )
        Stealth().apply_stealth_sync(self._context)
        self.page = self._context.new_page()
        self.page.set_default_timeout(self.timeout)

    def _close(self) -> None:
        for obj in [self.page, self._context, self._browser]:
            if obj:
                with contextlib.suppress(Exception):
                    obj.close()
        if self._playwright:
            self._playwright.stop()

    @abstractmethod
    def get_listings(self) -> list[CPOListing]: ...

    def scrape(self) -> list[CPOListing]:
        with self:
            return self.get_listings()


class ProgrammePageCPOScraper(CPOScraper):
    """For CPO programme description pages that have no inventory grid."""

    PROGRAMME_TITLE: str

    def get_listings(self) -> list[CPOListing]:
        self.page.goto(self.BASE_URL, wait_until="domcontentloaded", timeout=self.timeout)
        return [
            CPOListing(
                source=self.SOURCE_ID,
                title=self.PROGRAMME_TITLE,
                url=self.page.url,
                listing_type="programme_page",
            )
        ]


# ─── Listing scrapers ─────────────────────────────────────────────────────────


class ICPreownedScraper(CPOScraper):
    SOURCE_ID = "ic_preowned"
    BASE_URL = "https://www.icpreowned.com.sg/used-car-listing"
    _BASE = "https://www.icpreowned.com.sg"

    def get_listings(self) -> list[CPOListing]:
        self.page.goto(self.BASE_URL, wait_until="domcontentloaded")
        with contextlib.suppress(Exception):
            self.page.wait_for_selector(".search-model", timeout=10000)

        results = []
        for card in self.page.locator(".search-model").all():
            try:
                listing = self._parse_card(card)
                if listing:
                    results.append(listing)
            except Exception:
                continue
        return results

    def _parse_card(self, card) -> CPOListing | None:
        title = card.locator("h2.model-header").inner_text().strip()
        if not title:
            return None

        price_text = card.locator(".price p").first.inner_text()

        mileage_spans = card.locator(".mileage span").all()
        mileage = mileage_spans[-1].inner_text().strip() if len(mileage_spans) > 1 else None

        reg_spans = card.locator(".reg-date span").all()
        reg_date = reg_spans[-1].inner_text().strip() if len(reg_spans) > 1 else None

        href = card.locator("a.btn").first.get_attribute("href")
        url = f"{self._BASE}{href}" if href and href.startswith("/") else href or self.BASE_URL

        return CPOListing(
            source=self.SOURCE_ID,
            title=title,
            url=url,
            price=_parse_price(price_text),
            mileage=mileage,
            reg_date=reg_date,
        )


class EurokarsScraper(CPOScraper):
    SOURCE_ID = "eurokars"
    BASE_URL = "https://www.eurokarspreowned.com.sg/stock"
    _BASE = "https://www.eurokarspreowned.com.sg"

    def get_listings(self) -> list[CPOListing]:
        self.page.goto(self.BASE_URL, wait_until="domcontentloaded")
        with contextlib.suppress(Exception):
            self.page.wait_for_selector(".stock-item", timeout=10000)

        results = []
        for card in self.page.locator(".stock-item").all():
            try:
                listing = _parse_stock_item(card, self.SOURCE_ID, self._BASE)
                if listing:
                    results.append(listing)
            except Exception:
                continue
        return results


class SimeMeeMotorsScraper(CPOScraper):
    SOURCE_ID = "sim_mee_motors"
    # /stock/list-all loads all inventory without pagination
    BASE_URL = "https://autoselection.simemotors.com.sg/stock/list-all"
    _BASE = "https://autoselection.simemotors.com.sg"

    def __init__(self, headless: bool = True, timeout: int = 60000):
        super().__init__(headless=headless, timeout=timeout)

    def get_listings(self) -> list[CPOListing]:
        self.page.goto(self.BASE_URL, wait_until="domcontentloaded")
        with contextlib.suppress(Exception):
            self.page.wait_for_selector(".stock-item", timeout=15000)

        results = []
        for card in self.page.locator(".stock-item").all():
            try:
                listing = _parse_stock_item(card, self.SOURCE_ID, self._BASE)
                if listing:
                    results.append(listing)
            except Exception:
                continue
        return results


class DasWeltAutoScraper(CPOScraper):
    SOURCE_ID = "das_weltauto"
    BASE_URL = "https://dasweltauto.com.sg/certified-used-car"
    _BASE = "https://dasweltauto.com.sg"
    _CARD_SEL = '[data-id="search-result"] .item'

    def get_listings(self) -> list[CPOListing]:
        self.page.goto(self.BASE_URL, wait_until="domcontentloaded")
        with contextlib.suppress(Exception):
            self.page.wait_for_selector(self._CARD_SEL, timeout=10000)

        results = self._parse_current_page()

        # JS-driven pagination: click each data-pg link
        page_nums = [
            el.get_attribute("data-pg")
            for el in self.page.locator("a.page-link[data-pg]").all()
            if el.get_attribute("data-pg") != "1"
        ]
        for pg in page_nums:
            try:
                self.page.locator(f'a.page-link[data-pg="{pg}"]').click()
                # Wait for the active state to update
                self.page.wait_for_selector(
                    f'.page-item.active a[data-pg="{pg}"]', timeout=5000
                )
                results.extend(self._parse_current_page())
            except Exception:
                continue

        return results

    def _parse_current_page(self) -> list[CPOListing]:
        results = []
        for card in self.page.locator(self._CARD_SEL).all():
            try:
                listing = self._parse_card(card)
                if listing:
                    results.append(listing)
            except Exception:
                continue
        return results

    def _parse_card(self, card) -> CPOListing | None:
        title = card.locator(".item-title").inner_text().strip()
        subtitle = card.locator(".item-subtitle").inner_text().strip()
        full_title = f"{title} {subtitle}".strip() if subtitle else title
        if not full_title:
            return None

        price_text = card.locator(".item-price span").first.inner_text()
        href = card.locator("a.btn").get_attribute("href")
        url = f"{self._BASE}{href}" if href and href.startswith("/") else href or self.BASE_URL

        return CPOListing(
            source=self.SOURCE_ID,
            title=full_title,
            url=url,
            price=_parse_price(price_text),
        )


class ToyotaScraper(CPOScraper):
    SOURCE_ID = "toyota"
    BASE_URL = "https://www.toyota.com.sg/showroom/pre-owned-models"
    _BASE = "https://www.toyota.com.sg"

    def get_listings(self) -> list[CPOListing]:
        self.page.goto(self.BASE_URL, wait_until="domcontentloaded")
        with contextlib.suppress(Exception):
            self.page.wait_for_selector("article.model-card", timeout=10000)

        results = []
        for card in self.page.locator("article.model-card").all():
            try:
                listing = self._parse_card(card)
                if listing:
                    results.append(listing)
            except Exception:
                continue
        return results

    def _parse_card(self, card) -> CPOListing | None:
        title = card.locator("h3.model-card__name").inner_text().strip()
        if not title:
            return None

        price_val = card.locator(".model-card__price-value").inner_text().strip()
        mileage_val = card.locator(".model-card__mileage").inner_text().strip()
        reg_date = card.locator(".model-card__registration").inner_text().strip() or None

        href = card.locator("a.model-card__link").get_attribute("href")
        url = f"{self._BASE}{href}" if href and href.startswith("/") else href or self.BASE_URL

        return CPOListing(
            source=self.SOURCE_ID,
            title=title,
            url=url,
            price=_parse_price(f"${price_val}"),
            mileage=f"{mileage_val} km" if mileage_val else None,
            reg_date=reg_date,
        )


class DicksonScraper(CPOScraper):
    SOURCE_ID = "dickson"
    BASE_URL = "https://dicksongroup.com.sg/buy-sell/pre-owned-cars/"

    def get_listings(self) -> list[CPOListing]:
        self.page.goto(self.BASE_URL, wait_until="domcontentloaded")
        with contextlib.suppress(Exception):
            self.page.wait_for_selector(".item-template", timeout=10000)

        results = []
        for card in self.page.locator(".item-template").all():
            try:
                listing = self._parse_card(card)
                if listing:
                    results.append(listing)
            except Exception:
                continue
        return results

    def _parse_card(self, card) -> CPOListing | None:
        title = card.locator("h4.cartitle").inner_text().strip()
        if not title:
            return None

        data_raw = card.get_attribute("data-item")
        data: dict = json.loads(data_raw) if data_raw else {}

        href = card.locator("a.js_list_link").get_attribute("href")

        car_paras = card.locator(".col-7 p.car").all()
        mileage = car_paras[1].inner_text().strip() if len(car_paras) > 1 else None
        reg_date = (
            car_paras[2].inner_text().strip()
            if len(car_paras) > 2
            else data.get("date")
        )

        return CPOListing(
            source=self.SOURCE_ID,
            title=title,
            url=href or self.BASE_URL,
            price=data.get("price"),
            mileage=mileage,
            reg_date=reg_date,
            raw={k: v for k, v in data.items() if k not in ("model", "price", "date")},
        )


class CarChoiceScraper(CPOScraper):
    SOURCE_ID = "carchoice"
    BASE_URL = "https://carchoice.com.sg/certified-pre-owned-cars"

    def get_listings(self) -> list[CPOListing]:
        self.page.goto(self.BASE_URL, wait_until="domcontentloaded")
        with contextlib.suppress(Exception):
            self.page.wait_for_selector(".card", timeout=10000)

        results = []
        for card in self.page.locator(".card").all():
            try:
                listing = self._parse_card(card)
                if listing:
                    results.append(listing)
            except Exception:
                continue
        return results

    def _parse_card(self, card) -> CPOListing | None:
        title_el = card.locator(".h5.font-weight-bold")
        if not title_el.count():
            return None
        title = title_el.inner_text().strip()
        if not title:
            return None

        price_text = card.locator(".color-dark2.h4.font-weight-bold").inner_text()
        reg_text = card.locator(".text-muted").inner_text().strip()
        reg_date = re.sub(r"^Reg\.\s*", "", reg_text).strip() or None

        # The .card is wrapped in an <a> tag
        url = card.evaluate("el => el.closest('a')?.href || ''")

        return CPOListing(
            source=self.SOURCE_ID,
            title=title,
            url=url or self.BASE_URL,
            price=_parse_price(price_text),
            reg_date=reg_date,
        )


# ─── Programme pages ──────────────────────────────────────────────────────────


class CycleCarriageScraper(ProgrammePageCPOScraper):
    SOURCE_ID = "cycle_carriage"
    BASE_URL = "https://www.cyclecarriage.com/sg/republic-auto/certified-badge-of-trust"
    PROGRAMME_TITLE = "Cycle & Carriage Republic Auto Certified Badge of Trust"


class SkodaScraper(ProgrammePageCPOScraper):
    SOURCE_ID = "skoda"
    BASE_URL = "https://www.skoda.com.sg/dasweltauto/certified-pre-owned-skoda-cars"
    PROGRAMME_TITLE = "Skoda Das WeltAuto Certified Pre-Owned Programme"


# ─── Registry & runner ────────────────────────────────────────────────────────


ALL_SCRAPERS: dict[str, type[CPOScraper]] = {
    "ic_preowned": ICPreownedScraper,
    "eurokars": EurokarsScraper,
    "das_weltauto": DasWeltAutoScraper,
    "toyota": ToyotaScraper,
    "dickson": DicksonScraper,
    "carchoice": CarChoiceScraper,
    "sim_mee_motors": SimeMeeMotorsScraper,
    "cycle_carriage": CycleCarriageScraper,
    "skoda": SkodaScraper,
}

_TEST_SITES = ["ic_preowned", "toyota", "das_weltauto"]


def run_all(
    sites: list[str] | None = None,
    headless: bool = True,
    max_workers: int = CPO_DEFAULT_MAX_WORKERS,
    retries: int = 1,
) -> tuple[list[CPOListing], dict[str, dict]]:
    targets = {k: v for k, v in ALL_SCRAPERS.items() if sites is None or k in sites}
    all_listings: list[CPOListing] = []
    site_results: dict[str, dict] = {}

    def _scrape(name: str, cls: type[CPOScraper]) -> tuple[str, list[CPOListing], str | None]:
        last_error: str | None = None
        for attempt in range(1 + retries):
            try:
                listings = cls(headless=headless).scrape()
                return name, listings, None
            except Exception as e:
                last_error = str(e)
                if attempt < retries:
                    print(f"↺ {name}: attempt {attempt + 1} failed, retrying… ({e})")
        return name, [], last_error

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_scrape, name, cls): name for name, cls in targets.items()}
        for future in as_completed(futures):
            name, listings, error = future.result()
            all_listings.extend(listings)
            site_results[name] = {
                "status": "error" if error else "ok",
                "count": len(listings),
                **({"error": error} if error else {}),
            }
            status = "✗" if error else "✓"
            msg = f" ({error})" if error else ""
            print(f"{status} {name}: {len(listings)} listings{msg}")

    return all_listings, site_results


def save_results(
    listings: list[CPOListing],
    site_results: dict[str, dict],
    output_dir: str = CPO_OUTPUT_DIR,
) -> str:
    os.makedirs(output_dir, exist_ok=True)
    today = date.today().isoformat()
    filepath = os.path.join(output_dir, f"{today}.json")
    latest_path = os.path.join(output_dir, "latest.json")

    # Load previous latest.json for idempotency guard
    previous = {}
    if os.path.exists(latest_path):
        with open(latest_path) as f:
            previous = json.load(f)

    payload = {
        "date": today,
        "scraped_at": datetime.now(UTC).isoformat(),
        "site_results": site_results,
        "total_listings": len(listings),
        "listings": [asdict(lst) for lst in listings],
    }

    # Write the dated snapshot always
    with open(filepath, "w") as f:
        json.dump(payload, f, indent=2)

    # Idempotency: if 0 listings but we had data before, don't overwrite latest.json.
    # A zero-result scrape is almost certainly a failure (blocked, site changed, etc.).
    if not listings and previous.get("total_listings"):
        print(
            f"WARNING: 0 listings fetched but previous snapshot has "
            f"{previous['total_listings']} listings. "
            "Skipping latest.json overwrite to preserve previous data."
        )
    else:
        with open(latest_path, "w") as f:
            json.dump(payload, f, indent=2)

    return filepath
