export const METRICS = {
  body_depreciation_rate: {label: "Body depreciation rate", short: "Body depr.", unit: "pct"},
  body_price_per_coe_year: {label: "Body price per COE year", short: "Body $/COE yr", unit: "money"},
  depreciation_per_cc: {label: "Depreciation per cc", short: "Depr./cc", unit: "money2"},
  annual_mileage: {label: "Annual mileage", short: "km/yr", unit: "km"},
  days_on_market: {label: "Days on market", short: "Days listed", unit: "days"},
  num_owners: {label: "Previous owners", short: "Owners", unit: "count"},
  depreciation_rate: {label: "Depreciation rate", short: "Depr. rate", unit: "pct"}
};

export function activeMetrics(weights) {
  return Object.keys(weights)
    .filter((metric) => weights[metric] > 0)
    .sort((a, b) => weights[b] - weights[a]);
}

const integerFormat = new Intl.NumberFormat("en-SG", {maximumFractionDigits: 0});
const dateFormat = new Intl.DateTimeFormat("en-GB", {day: "numeric", month: "short", year: "numeric"});
const shortDateFormat = new Intl.DateTimeFormat("en-GB", {day: "numeric", month: "short"});

export function money(value) {
  return value == null ? "—" : `S$${integerFormat.format(value)}`;
}

export function compactMoney(value) {
  if (value == null) return "—";
  if (value < 1000) return money(value);
  const thousands = value / 1000;
  return `S$${Number.isInteger(thousands) || thousands >= 100 ? Math.round(thousands) : thousands.toFixed(1)}k`;
}

export function integer(value) {
  return value == null ? "—" : integerFormat.format(value);
}

export function years(value) {
  return value == null ? "—" : `${value.toFixed(1)} yr`;
}

export function percent(value, digits = 1) {
  return value == null ? "—" : `${(value * 100).toFixed(digits)}%`;
}

export function parseDate(isoDate) {
  const [year, month, day] = isoDate.split("-").map(Number);
  return new Date(year, month - 1, day);
}

export function longDate(isoDate) {
  return isoDate ? dateFormat.format(parseDate(isoDate)) : "—";
}

export function shortDate(date) {
  return shortDateFormat.format(date);
}

export function metricValue(metric, value) {
  switch (METRICS[metric]?.unit) {
    case "pct":
      return percent(value);
    case "money":
      return money(value);
    case "money2":
      return value == null ? "—" : `S$${value.toFixed(2)}`;
    case "km":
      return value == null ? "—" : `${integer(value)} km`;
    case "count":
      return value == null ? "—" : integer(value);
    case "days":
      return value == null ? "—" : `${value} d`;
    default:
      return String(value);
  }
}

export function topShare(listing) {
  const share = 1 - listing.percentile;
  if (share < 0.001) return "Top 0.1%";
  if (share < 0.01) return `Top ${(share * 100).toFixed(1)}%`;
  return `Top ${Math.ceil(share * 100)}%`;
}

export function priceDrop(listing) {
  return Math.max(0, listing.peak_price - listing.price);
}

export function modelKey(title) {
  return title.split(/\s+/).slice(0, 2).join(" ").toLowerCase();
}

export function coeShort(category) {
  return category?.replace("Category ", "Cat ") ?? "—";
}
