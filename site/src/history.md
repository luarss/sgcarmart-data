---
title: Price History — SGCM Value Watchlist
toc: false
---

```js
import * as Plot from "npm:@observablehq/plot";

const watchlist = await FileAttachment("data/watchlist.json").json();
const snapshots = await FileAttachment("data/snapshots.json").json();

const top100 = watchlist.top_listings;
const dates = snapshots.dates;
// Parse date strings to Date objects so Plot auto-detects the scale
const dailyStats = snapshots.daily_stats.map(d => ({ ...d, date: new Date(d.date) }));
const tracked = snapshots.tracked_listings.map(l => ({
  ...l,
  history: l.history.map(h => ({ ...h, date: new Date(h.date) }))
}));

// Sort by days tracked, keep all with price changes + top 50 most-tracked
const trackedByDays = [...tracked].sort((a, b) => b.history.length - a.history.length);
const withChanges = trackedByDays.filter(l => new Set(l.history.map(h => h.price)).size > 1);
const withoutChanges = trackedByDays.filter(l => new Set(l.history.map(h => h.price)).size === 1);
const topTracked = [...withChanges, ...withoutChanges.slice(0, 50)];

const totalPriceMoves = tracked.filter(l => {
  const prices = l.history.map(h => h.price);
  return new Set(prices).size > 1;
}).length;
```

<div class="hero">
  <h1>Market Trends</h1>
  <p>Tracking ${dailyStats.length} daily snapshots across ${snapshots.total_listings_tracked.toLocaleString()} unique listings</p>
</div>

<div class="stat-grid">
  <div class="stat-card"><div class="stat-value">${snapshots.date_count}</div><div class="stat-label">Snapshot Days</div></div>
  <div class="stat-card"><div class="stat-value">${tracked.length.toLocaleString()}</div><div class="stat-label">Multi-Day Listings</div></div>
  <div class="stat-card"><div class="stat-value">${totalPriceMoves.toLocaleString()}</div><div class="stat-label">With Price Changes</div></div>
</div>

<div class="coe-banner">
  <div class="coe-item"><div class="coe-cat">COE Cat A</div><div class="coe-val">$${watchlist.coe_premiums_used.category_a_latest.premium.toLocaleString()}</div></div>
  <div class="coe-item"><div class="coe-cat">COE Cat B</div><div class="coe-val">$${watchlist.coe_premiums_used.category_b_latest.premium.toLocaleString()}</div></div>
  <div class="coe-item"><div class="coe-cat">Reference Date</div><div class="coe-val">${watchlist.reference_date}</div></div>
</div>

<div class="content">

## Daily Listing Volume

```js
display(htl.html`<div class="chart-container">${Plot.plot({
  marginLeft: 60,
  marginBottom: 40,
  height: 220,
  style: { fontSize: "13px" },
  x: { label: "Date", tickRotate: -30, tickFormat: d => d.toLocaleDateString("en", {month:"short",day:"numeric"}) },
  y: { label: "Listings", grid: true },
  marks: [
    Plot.barY(dailyStats, { x: "date", y: "count", fill: "#16a34a", fillOpacity: 0.7 }),
    Plot.lineY(dailyStats, { x: "date", y: "count", stroke: "#166534", strokeWidth: 2 }),
    Plot.dot(dailyStats, { x: "date", y: "count", fill: "#166534", r: 3, title: d => `${d.date}: ${d.count.toLocaleString()} listings` }),
  ]
})}</div>`);
```

## Average Price Trend

```js
const avgVals = dailyStats.map(d => d.avg_price);
const yMin = Math.min(...avgVals) - 200;
const yMax = Math.max(...avgVals) + 200;

display(htl.html`<div class="chart-container">${Plot.plot({
  marginLeft: 60,
  marginBottom: 40,
  height: 250,
  style: { fontSize: "13px" },
  x: { label: "Date", tickRotate: -30, tickFormat: d => d.toLocaleDateString("en", {month:"short",day:"numeric"}) },
  y: { label: "Average Price (SGD)", tickFormat: "$,d", grid: true, domain: [yMin, yMax] },
  marks: [
    Plot.lineY(dailyStats, { x: "date", y: "avg_price", stroke: "#2563eb", strokeWidth: 2.5 }),
    Plot.dot(dailyStats, { x: "date", y: "avg_price", fill: "#2563eb", r: 4, title: d => `${d.date}: $${d.avg_price.toLocaleString()}` }),
  ]
})}</div>`);
```

## Snapshot Statistics

```js
display(htl.html`<div class="chart-container">
<table class="data-table">
<thead><tr>
  <th>Date</th>
  <th>Listings</th>
  <th>Avg Price</th>
  <th>Min Price</th>
  <th>Max Price</th>
</tr></thead>
<tbody>
${[...dailyStats].reverse().map(d => htl.html`<tr>
  <td style="font-weight:600;">${d.date}</td>
  <td>${d.count.toLocaleString()}</td>
  <td>$${d.avg_price.toLocaleString()}</td>
  <td>$${d.min_price.toLocaleString()}</td>
  <td>$${d.max_price.toLocaleString()}</td>
</tr>`)}
</tbody></table></div>`);
```

## Price Movements — Tracked Listings

```js
// Show tracked listings: price-changed first, all sorted alphabetically
const withChange = topTracked.filter(l => new Set(l.history.map(h => h.price)).size > 1);
const stable = topTracked.filter(l => new Set(l.history.map(h => h.price)).size === 1);
const sortAlpha = (a, b) => a.title.localeCompare(b.title);
withChange.sort(sortAlpha);
stable.sort(sortAlpha);
const showTracked = [...withChange, ...stable];

const listingLabels = showTracked.map((l, i) => {
  const hasChange = new Set(l.history.map(h => h.price)).size > 1;
  const prefix = hasChange ? "△ " : "  ";
  const short = l.title.length > 46 ? l.title.substring(0, 46) + "…" : l.title;
  return prefix + short;
});
const picker = view(Inputs.select(listingLabels, {label: "Select listing", value: listingLabels[0]}));
```

```js
const fmtDate = (d) => d.toLocaleDateString("en", {month:"short",day:"numeric"});
const idx = listingLabels.findIndex(l => l === picker);
const listing = showTracked[Math.max(0, idx)];
const hist = listing.history;
const firstPrice = hist[0].price;
const lastPrice = hist[hist.length - 1].price;
const delta = lastPrice - firstPrice;
const changeStr = delta === 0 ? "no change" : (delta > 0 ? "↑ +$" : "↓ -$") + Math.abs(delta).toLocaleString();

const vals = hist.map(h => h.price);
const pMin = Math.min(...vals);
const pMax = Math.max(...vals);
const padding = Math.max((pMax - pMin) * 0.5, 500);

const chart = Plot.plot({
  marginLeft: 60,
  marginRight: 30,
  marginBottom: 50,
  height: 360,
  style: { fontSize: "13px" },
  x: { label: null, tickRotate: -30, tickFormat: fmtDate },
  y: { label: "Price (SGD)", tickFormat: "$,d", grid: true, domain: [pMin - padding, pMax + padding] },
  marks: [
    Plot.lineY(hist, { x: "date", y: "price", stroke: delta > 0 ? "#ef4444" : delta < 0 ? "#16a34a" : "#2563eb", strokeWidth: 3, marker: "circle", title: d => `${fmtDate(d.date)}: $${d.price.toLocaleString()}` }),
  ]
});

display(htl.html`<div class="chart-container">
  <div style="text-align:center; margin-bottom:12px;">
    <div style="font-weight:700; font-size:1.05rem; color:var(--slate-900); margin-bottom:4px;">
      ${listing.url ? htl.html`<a href="${listing.url}" target="_blank" style="color:var(--slate-900); text-decoration:none;">${listing.title} ↗</a>` : listing.title}
    </div>
    <div style="font-size:0.8rem; color:var(--slate-500);">
      ${hist.length} days tracked · $${firstPrice.toLocaleString()} → $${lastPrice.toLocaleString()} (${changeStr})
    </div>
  </div>
  ${chart}
  <div style="text-align:center; margin-top: 16px; font-size: 0.85rem; color: var(--slate-500);">
    ${withChange.length} listings with price changes · ${stable.length} stable · ${showTracked.length} total tracked
  </div>
</div>`);
```

</div>

```js
display(htl.html`<footer>
  Historical data from daily snapshot files. Listings are matched by listing ID across dates. Only the current top-100 watchlist have full scoring data — historical snapshots are raw listings without value scores.
</footer>`);
```
