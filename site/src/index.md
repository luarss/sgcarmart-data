---
title: SGCM Value Watchlist
toc: false
---

```js
import * as Plot from "npm:@observablehq/plot";

const watchlist = await FileAttachment("data/watchlist.json").json();
const market = await FileAttachment("data/latest.json").json();

const top100 = watchlist.top_listings;
const weights = watchlist.scoring_weights;
const coe = watchlist.coe_premiums_used;
const metricNames = Object.keys(weights);

const brands = new Set(top100.map(l => l.brand)).size;
const avgScore = top100.reduce((s, l) => s + l.composite_score, 0) / top100.length;
```

<div class="hero">
  <h1>Best-Value Used Cars in Singapore</h1>
  <p>Daily analysis of ${watchlist.total_source_listings.toLocaleString()} listings scored across 7 COE-adjusted metrics</p>
</div>

<div class="stat-grid">
  <div class="stat-card"><div class="stat-value">${top100.length}</div><div class="stat-label">Top Value Picks</div></div>
  <div class="stat-card"><div class="stat-value">${brands}</div><div class="stat-label">Brands in Top 100</div></div>
  <div class="stat-card"><div class="stat-value">${watchlist.scored_listings.toLocaleString()}</div><div class="stat-label">Listings Scored</div></div>
  <div class="stat-card"><div class="stat-value">${avgScore.toFixed(3)}</div><div class="stat-label">Avg Composite Score</div></div>
</div>

<div class="coe-banner">
  <div class="coe-item"><div class="coe-cat">COE Cat A</div><div class="coe-val">$${coe.category_a_latest.premium.toLocaleString()}</div></div>
  <div class="coe-item"><div class="coe-cat">COE Cat B</div><div class="coe-val">$${coe.category_b_latest.premium.toLocaleString()}</div></div>
  <div class="coe-item"><div class="coe-cat">Reference Date</div><div class="coe-val">${watchlist.reference_date}</div></div>
</div>

<div class="content">

## Score Distribution

```js
const scoreMean = avgScore;
display(htl.html`<div class="chart-container">${Plot.plot({
  marginLeft: 50,
  marginBottom: 40,
  height: 220,
  style: { fontSize: "13px" },
  x: { label: "Composite Score", tickFormat: ".2f" },
  y: { label: "Count", grid: true },
  marks: [
    Plot.rectY(top100, Plot.binX({ y: "count" }, { x: "composite_score", thresholds: 20, fill: "#22c55e", fillOpacity: 0.7 })),
    Plot.ruleX([scoreMean], { stroke: "#ef4444", strokeWidth: 2, strokeDasharray: "4 2" }),
    Plot.text([{x: scoreMean, y: 10, text: `avg ${scoreMean.toFixed(3)}`}], { x: "x", y: "y", text: "text", textAnchor: "start", dx: 6, fill: "#ef4444", fontSize: 11 })
  ]
})}</div>`);
```

## Price vs. Value Score

```js
display(htl.html`<div class="chart-container">${Plot.plot({
  marginLeft: 60,
  marginBottom: 40,
  height: 420,
  style: { fontSize: "13px" },
  color: { legend: true, scheme: "tableau10" },
  x: { label: "Price (SGD)", tickFormat: "$,d" },
  y: { label: "Composite Score", tickFormat: ".2f" },
  marks: [
    Plot.dot(top100, {
      x: "price",
      y: "composite_score",
      stroke: "brand",
      fill: "brand",
      fillOpacity: 0.6,
      r: 6,
      tip: true,
      title: (d) => `${d.title}\nPrice: $${d.price.toLocaleString()}\nDepr/yr: $${d.depreciation.toLocaleString()}\nScore: ${d.composite_score.toFixed(3)}`,
    })
  ]
})}</div>`);
```

<div class="grid-2">

<div>

## Brand Breakdown

```js
const brandCounts = Array.from(
  d3.rollup(top100, v => v.length, d => d.brand),
  ([brand, count]) => ({ brand, count })
).sort((a, b) => b.count - a.count).slice(0, 12);

const brandAvgScore = new Map(
  Array.from(d3.rollup(top100, v => d3.mean(v, d => d.composite_score), d => d.brand))
);

display(htl.html`<div class="chart-container">${Plot.plot({
  marginLeft: 90,
  marginBottom: 30,
  height: 400,
  style: { fontSize: "12px" },
  x: { label: "Count in Top 100", grid: true },
  y: { label: null, domain: brandCounts.map(d => d.brand).reverse() },
  color: { type: "linear", scheme: "RdYlGn", domain: [0.85, 0.95], label: "Avg Score" },
  marks: [
    Plot.barX(brandCounts, {
      x: "count",
      y: "brand",
      fill: d => brandAvgScore.get(d.brand),
      sort: { y: "x", reverse: true },
      tip: true,
      title: d => `${d.brand}: ${d.count} cars, avg score ${brandAvgScore.get(d.brand).toFixed(3)}`
    })
  ]
})}</div>`);
```

</div>

<div>

## Metric Weights

```js
const weightData = Object.entries(weights).map(([key, w]) => ({
  metric: key.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase()),
  weight: w
})).sort((a, b) => b.weight - a.weight);

display(htl.html`<div class="chart-container">${Plot.plot({
  marginLeft: 170,
  marginBottom: 30,
  height: 400,
  style: { fontSize: "12px" },
  x: { label: "Weight", tickFormat: ".0%", grid: true },
  y: { label: null, domain: weightData.map(d => d.metric).reverse() },
  marks: [
    Plot.barX(weightData, {
      x: "weight",
      y: "metric",
      fill: "#16a34a",
      fillOpacity: 0.8,
      sort: { y: "x", reverse: true },
      tip: true,
      title: d => `${d.metric}: ${(d.weight * 100).toFixed(0)}%`
    })
  ]
})}</div>`);
```

</div>
</div>

## Top 20 Value Picks

```js
const sorted = [...top100].sort((a, b) => b.composite_score - a.composite_score);
const top20 = sorted.slice(0, 20);

display(htl.html`<div class="chart-container" style="overflow-x: auto;">
<table class="data-table">
<thead><tr>
  <th class="rank-col">#</th>
  <th>Car</th>
  <th>Brand</th>
  <th>Price</th>
  <th>Depr/yr</th>
  <th>Body Depr</th>
  <th>RdTax</th>
  <th>Value Ret.</th>
  <th>Body$/COE yr</th>
  <th>Score</th>
</tr></thead>
<tbody>
${top20.map(l => {
  const sc = l.composite_score;
  const cls = sc >= 0.9 ? "high" : sc >= 0.8 ? "mid" : "low";
  return htl.html`<tr>
  <td class="rank-col">${l.rank}</td>
  <td><a href="/detail#${l.id}">${l.title}</a></td>
  <td>${l.brand}</td>
  <td class="price-col">$${l.price.toLocaleString()}</td>
  <td>$${l.depreciation.toLocaleString()}</td>
  <td>${(l.body_depreciation_rate * 100).toFixed(1)}%</td>
  <td>${l.road_tax != null ? "$" + l.road_tax.toLocaleString() : "N/A"}</td>
  <td>${(l.value_retention * 100).toFixed(1)}%</td>
  <td>$${Math.round(l.body_price_per_coe_year).toLocaleString()}</td>
  <td class="score-col"><span class="score-badge ${cls}">${sc.toFixed(4)}</span></td>
</tr>`;
})}
</tbody></table></div>`);
```

<div style="text-align:center; margin-top: 16px; font-size: 0.85rem; color: var(--slate-500);">
  Showing top 20 of 100. <a href="/">Back to top</a>
</div>

</div>

```js
display(htl.html`<footer>
  Data refreshed daily via automated CI pipeline. Scores use winsorized min-max normalization across 7 metrics weighted by importance. Higher composite score = better value.
</footer>`);
```
