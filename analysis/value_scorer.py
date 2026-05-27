"""
Value scoring engine for used car listings.

Extracted from analysis/used-car-value-study.ipynb — computes a composite
value score for each listing using 7 COE-adjusted metrics, weighted to
identify the best-value used cars.

Pure Python stdlib — no pandas/numpy needed.
"""

import glob
import json
import math
import re
from datetime import date, datetime
from pathlib import Path

# ── Scoring weights (must sum to 1.0) ────────────────────────────────────
# `value_retention` was removed: it is derived from the same (price,
# depreciation, age) inputs as `depreciation_rate`, so including both
# double-counted depreciation at ~30% effective weight.  Its 0.20 share
# is redistributed across the four strongest independent signals.

DEFAULT_WEIGHTS = {
    "body_depreciation_rate": 0.30,   # was 0.25
    "body_price_per_coe_year": 0.20,  # was 0.15
    "depreciation_rate": 0.15,        # was 0.10
    "annual_mileage": 0.10,
    "depreciation_per_km": 0.15,      # was 0.10
    "price_per_owner": 0.05,
    "days_on_market": 0.05,
}

ANNUAL_MILEAGE_CAP = 50000

# Niche/retro/classic brands that don't reflect mainstream used-car value.
# Their pricing is driven by rarity/collectibility, not fundamentals.
EXCLUDED_BRANDS = {"Mitsuoka", "Pontiac"}

# Classic/retro models from otherwise-mainstream brands.
# These are vintage cars (e.g. 1970s-1990s Rolls-Royce) re-registered
# under modern COEs — their age-based metrics are meaningless.
_RETRO_MODEL_RE = re.compile(
    r"Silver\s+(Spirit|Shadow|Cloud|Dawn|Seraph|Wraith\s*II)|"
    r"Corniche|Camargue",
    re.IGNORECASE,
)

# OPC (Off-Peak Car) — restricted to evenings/weekends, priced ~$5-10K
# below equivalent normal-plate cars. Exclude from value comparison.
_OPC_RE = re.compile(r"\bOPC\b", re.IGNORECASE)


# ── Parsing helpers ──────────────────────────────────────────────────────


def _parse_coe_left(text: str | None) -> float | None:
    if not text:
        return None
    years = 0.0
    y_match = re.search(r"(\d+)\s*y", text)
    m_match = re.search(r"(\d+)\s*m", text)
    if y_match:
        years += int(y_match.group(1))
    if m_match:
        years += int(m_match.group(1)) / 12
    return years if years > 0 else None


def _parse_mileage(text: str | None) -> float | None:
    if not text:
        return None
    m = re.search(r"([\d,]+)", text)
    return float(m.group(1).replace(",", "")) if m else None


def _parse_eng_cap(text: str | None) -> float | None:
    if not text:
        return None
    m = re.search(r"([\d,]+)", text)
    return float(m.group(1).replace(",", "")) if m else None


def _parse_owners(text: str | None) -> int | None:
    if not text:
        return None
    if "more than" in text.lower():
        m = re.search(r"\d+", text)
        return int(m.group()) + 1 if m else None
    m = re.search(r"(\d+)\s*Owner", text)
    return int(m.group(1)) if m else None


def _parse_reg_date(text: str | None) -> date | None:
    if not text:
        return None
    try:
        return datetime.strptime(text, "%d-%b-%Y").date()
    except (ValueError, TypeError):
        return None


def _parse_posted_date(text: str | None) -> date | None:
    if not text:
        return None
    try:
        return datetime.strptime(text, "%d-%b-%Y").date()
    except (ValueError, TypeError):
        return None


def _extract_brand(title: str) -> str:
    return title.split()[0] if title else ""


# ── COE premium lookup ───────────────────────────────────────────────────


def load_coe_lookup(project_root: Path) -> dict[tuple[str, str], int]:
    """Return dict: {(year_month, category): premium} from COE data files."""
    coe_dir = project_root / "data" / "coe"
    lookup: dict[tuple[str, str], int] = {}
    records: list[dict] = []
    for f in sorted(glob.glob(str(coe_dir / "coe_results_*.json"))):
        with open(f) as fh:
            records.extend(json.load(fh))
    for r in records:
        premium = r["premium"]
        if isinstance(premium, str):
            premium = int(premium.replace(",", ""))
        key = (r["month"], r["vehicle_class"])
        lookup[key] = premium
    return lookup


def _get_latest_premiums(lookup: dict[tuple[str, str], int]) -> dict[str, int]:
    """Return {category: latest_premium} for each COE category."""
    latest: dict[str, tuple[str, int]] = {}
    for (ym, cat), prem in lookup.items():
        if cat not in latest or ym > latest[cat][0]:
            latest[cat] = (ym, prem)
    return {cat: prem for cat, (ym, prem) in latest.items()}


def _assign_coe_category(eng_cap_cc: float | None) -> str:
    """Assign COE category by engine capacity. Defaults to Cat A."""
    if eng_cap_cc is None or eng_cap_cc <= 1600:
        return "Category A"
    return "Category B"


# ── Normalization helpers ────────────────────────────────────────────────


def _winsorized_bounds(
    vals: list[float],
    lower_pct: float = 0.02,
    upper_pct: float = 0.98,
) -> tuple[float, float]:
    """Return (lower, upper) bounds after winsorizing at given percentiles.

    Clamping to the 2nd/98th percentile prevents a single outlier from
    compressing all other scores toward the same value under min-max normalization.
    """
    s = sorted(vals)
    n = len(s)
    lo = s[max(0, int(lower_pct * n))]
    hi = s[min(n - 1, int(upper_pct * n))]
    return lo, hi


# ── Main scoring pipeline ────────────────────────────────────────────────


def score_listings(
    listings: list[dict],
    coe_lookup: dict[tuple[str, str], int],
    reference_date: date,
) -> tuple[list[dict], dict]:
    """Score a set of used car listings by composite value.

    Returns (scored_list, stats) where scored_list is sorted by
    composite_score descending and stats contains exclusion counts.
    """
    latest_premiums = _get_latest_premiums(lookup=coe_lookup)

    # ── Stage 1: Parse and enrich each listing ────────────────────────
    enriched: list[dict] = []
    parse_errors = 0
    excluded_brands = 0
    excluded_retro = 0
    excluded_opc = 0

    for car in listings:
        title = car.get("title", "")
        brand = _extract_brand(title)
        if brand in EXCLUDED_BRANDS:
            excluded_brands += 1
            continue
        if _RETRO_MODEL_RE.search(title):
            excluded_retro += 1
            continue
        if _OPC_RE.search(title):
            excluded_opc += 1
            continue

        price = car.get("price")
        depreciation = car.get("depreciation")
        reg_date = _parse_reg_date(car.get("reg_date"))
        posted_date = _parse_posted_date(car.get("posted_date"))
        mileage_km = _parse_mileage(car.get("mileage"))
        eng_cap_cc = _parse_eng_cap(car.get("eng_cap"))
        num_owners = _parse_owners(car.get("owners"))
        coe_years_left = _parse_coe_left(car.get("coe_left"))

        if price is None or depreciation is None or reg_date is None or posted_date is None:
            parse_errors += 1
            continue

        age_years = (reference_date - reg_date).days / 365.25
        annual_mileage_km = (mileage_km / age_years) if (age_years > 0 and mileage_km is not None) else None

        coe_category = _assign_coe_category(eng_cap_cc)
        days_on_market = (reference_date - posted_date).days

        enriched.append({
            **car,
            "brand": brand,
            "reg_date_parsed": reg_date,
            "posted_date_parsed": posted_date,
            "age_years": age_years,
            "coe_years_left": coe_years_left,
            "mileage_km": mileage_km,
            "eng_cap_cc": eng_cap_cc,
            "num_owners": num_owners,
            "annual_mileage_km_raw": annual_mileage_km,
            "coe_category": coe_category,
            "days_on_market": days_on_market,
            "depreciation_rate": depreciation / price,
            "est_original_price": price + (depreciation * age_years),
        })

    # ── Stage 2: Derived per-car metrics ──────────────────────────────
    for row in enriched:
        p = row["price"]
        d = row["depreciation"]
        age = row["age_years"]
        coe_left = row["coe_years_left"]
        coe_cat = row["coe_category"]
        reg_d = row["reg_date_parsed"]
        owners = row["num_owners"]
        am_raw = row["annual_mileage_km_raw"]
        dom = row["days_on_market"]

        row["value_retention"] = p / row["est_original_price"] if row["est_original_price"] > 0 else 0.0
        row["price_per_coe_year"] = (p / coe_left) if coe_left and coe_left > 0 else None
        row["depreciation_per_cc"] = (d / row["eng_cap_cc"]) if row["eng_cap_cc"] and row["eng_cap_cc"] > 0 else None
        row["price_per_owner"] = (p / owners) if (owners is not None and owners > 0) else None
        annual_mileage = min(am_raw, ANNUAL_MILEAGE_CAP) if am_raw is not None else None
        row["annual_mileage"] = annual_mileage
        row["depreciation_per_km"] = (d / am_raw) if (am_raw is not None and am_raw > 0) else None

        # COE premium lookup
        ym_key = reg_d.strftime("%Y-%m")
        reg_coe_premium = coe_lookup.get((ym_key, coe_cat))
        if reg_coe_premium is None:
            reg_coe_premium = latest_premiums.get(coe_cat)
        row["reg_coe_premium"] = reg_coe_premium
        row["current_coe_premium"] = latest_premiums.get(coe_cat)

        # Body-value computation
        if reg_coe_premium is not None and coe_left is not None and coe_left > 0:
            est_coe_value = reg_coe_premium * coe_left / 10.0
            coe_annual_depr = reg_coe_premium / 10.0
            row["est_coe_value"] = est_coe_value
            row["body_price"] = p - est_coe_value
            row["body_price_per_coe_year"] = row["body_price"] / coe_left
            row["coe_annual_depreciation"] = coe_annual_depr
            row["body_depreciation"] = d - coe_annual_depr
            if row["body_price"] > 0:
                row["body_depreciation_rate"] = row["body_depreciation"] / row["body_price"]
            else:
                row["body_depreciation_rate"] = None
        else:
            row["est_coe_value"] = None
            row["body_price"] = None
            row["body_price_per_coe_year"] = None
            row["coe_annual_depreciation"] = None
            row["body_depreciation"] = None
            row["body_depreciation_rate"] = None

    # ── Stage 3: Filter suspicious / invalid listings ─────────────────
    suspicious_count = 0
    low_body_price_count = 0
    missing_fields_count = 0
    clean: list[dict] = []

    scoring_fields = [
        "depreciation_rate", "body_depreciation_rate",
        "body_price_per_coe_year", "annual_mileage", "depreciation_per_km",
        "price_per_owner", "days_on_market",
    ]

    for row in enriched:
        # Suspicious metrics
        vr = row.get("value_retention", 0) or 0
        dr = row.get("depreciation_rate", 0) or 0
        age = row.get("age_years", 0)
        dom = row.get("days_on_market", 0)
        bdr = row.get("body_depreciation_rate")
        # dom < 0: listing posted_date is in the future (bad scrape data)
        # bdr <= 0: COE depreciation exceeds total depreciation — nonsensical body value
        if vr > 1.5 or vr < 0.1 or dr > 1.0 or age < 0 or dom < 0 or (bdr is not None and bdr <= 0):
            suspicious_count += 1
            continue

        # Low body price
        bp = row.get("body_price")
        if bp is None or bp <= 5000:
            low_body_price_count += 1
            continue

        # Missing scoring fields
        if any(row.get(f) is None for f in scoring_fields):
            missing_fields_count += 1
            continue

        clean.append(row)

    if not clean:
        return [], {
            "total_source_listings": len(listings),
            "scored_listings": 0,
            "excluded_parse_errors": parse_errors,
            "excluded_brands": excluded_brands,
            "excluded_retro_models": excluded_retro,
            "excluded_opc": excluded_opc,
            "excluded_suspicious_metrics": suspicious_count,
            "excluded_low_body_price": low_body_price_count,
            "excluded_missing_fields": missing_fields_count,
        }

    # ── Stage 4: Winsorized normalization & composite scoring ─────────
    # Use 2nd/98th percentile bounds so a single outlier doesn't collapse
    # all other scores toward the same value.
    metric_ranges: dict[str, tuple[float, float]] = {}
    for metric in scoring_fields:
        vals = [row[metric] for row in clean]
        metric_ranges[metric] = _winsorized_bounds(vals)

    # All scoring metrics are lower-is-better (value_retention removed).
    # score = 1 - (clamped_v - lo) / (hi - lo)
    for row in clean:
        scores: dict[str, float] = {}
        for metric in scoring_fields:
            lo, hi = metric_ranges[metric]
            if hi == lo:
                scores[metric] = 0.5  # single-value dataset → neutral
                continue
            clamped = max(lo, min(hi, row[metric]))
            scores[metric] = 1.0 - (clamped - lo) / (hi - lo)

        composite = sum(scores[m] * DEFAULT_WEIGHTS[m] for m in scoring_fields)
        row["composite_score"] = composite
        row["metric_scores"] = scores

    clean.sort(key=lambda r: r["composite_score"], reverse=True)

    stats = {
        "total_source_listings": len(listings),
        "scored_listings": len(clean),
        "excluded_parse_errors": parse_errors,
        "excluded_brands": excluded_brands,
        "excluded_retro_models": excluded_retro,
        "excluded_opc": excluded_opc,
        "excluded_suspicious_metrics": suspicious_count,
        "excluded_low_body_price": low_body_price_count,
        "excluded_missing_fields": missing_fields_count,
    }
    return clean, stats


# ── Convenience: load from file ──────────────────────────────────────────


def load_and_score(
    project_root: Path,
    watch_name: str = "sgd-passenger",
    reference_date: date | None = None,
) -> tuple[list[dict], dict]:
    """Load latest.json for a watch, score it, return (scored_list, stats)."""
    data_file = project_root / "data" / "used_cars" / watch_name / "latest.json"
    with open(data_file) as f:
        raw = json.load(f)

    listings = list(raw.values()) if isinstance(raw, dict) else raw
    if reference_date is None:
        reference_date = date.today()

    coe_lookup = load_coe_lookup(project_root)
    return score_listings(listings, coe_lookup, reference_date)
