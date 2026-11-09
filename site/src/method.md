---
title: Method
---

```js
import {METRICS, activeMetrics, money, integer, percent, years} from "./components/format.js";
import {plotDefaults, figure, dataTable, tokens} from "./components/plot.js";

const pool = await FileAttachment("data/pool.json").json();
const listings = pool.listings;
const weights = pool.weights;
const metrics = activeMetrics(weights);
const excludedTotal = d3.sum(Object.values(pool.excluded));
const exclusionLabels = {
  parse_errors: "Fields could not be parsed",
  brands: "Niche brands",
  retro_models: "Classic / retro models",
  opc: "Off-peak (OPC) cars",
  diesel: "Diesels",
  suspicious_metrics: "Implausible values",
  low_body_price: "Body price ≤ S$5,000",
  missing_fields: "Missing a scoring field"
};
```

# How the value score works

<div class="prose">

The score asks one question: **how much car are you buying once the COE is set aside?** In Singapore a large share of a used car's price is the remaining value of its Certificate of Entitlement, which expires on a fixed date regardless of the car. Netting it out gives the *body price*, the part that actually reflects the car.

Each listing is measured on the ${metrics.length} metrics below. Lower is better on all of them. Each metric is clipped at the 2nd and 98th percentile of today's pool, so one outlier can't squash everyone else, then rescaled to 0–1. The value score is the weighted sum.

</div>

## Weights

```js
display(figure({
  title: "Share of the score per metric",
  caption: `Depreciation rate also exists in the data but carries zero weight: it tracks body depreciation rate almost exactly (r = 0.99) and would count the same thing twice.`,
  chart: resize((width) => Plot.plot(plotDefaults({
    ariaLabel: "Bar chart of metric weights",
    ariaDescription: metrics.map((metric) => `${METRICS[metric].label} ${percent(weights[metric], 0)}`).join("; "),
    width,
    height: 40 + metrics.length * 30,
    marginLeft: Math.min(190, width * 0.45),
    marginRight: 40,
    x: {label: null, axis: null, domain: [0, d3.max(metrics, (metric) => weights[metric])]},
    y: {label: null, domain: metrics.map((metric) => METRICS[metric].label)},
    marks: [
      Plot.barX(metrics, {x: (metric) => weights[metric], y: (metric) => METRICS[metric].label, fill: tokens.good, insetTop: 6, insetBottom: 6, ariaHidden: true}),
      Plot.text(metrics, {x: (metric) => weights[metric], y: (metric) => METRICS[metric].label, text: (metric) => percent(weights[metric], 0), dx: 4, textAnchor: "start", fill: tokens.ink, ariaHidden: true})
    ]
  })))
}));
```

## Read the score with care

<div class="prose">

- **It is relative, not absolute.** 1.0 means best on every metric *within today's pool*. A 0.90 today and a 0.90 last month are not directly comparable, and if a scrape comes back partial the whole scale shifts.
- **Exact ranks are soft; the top tier is not.** Randomly nudging every weight by ±25% keeps about 90 of the top 100 in place, but individual positions move by several places. Treat #3 and #9 as roughly equal.
- **Small cars dominate.** Category A cars (≤1,600 cc) carry a lower COE and a cheaper body, so they fill almost all of the top 100. Filter by COE category to compare like with like.
- **"Days on market" is noisy.** Dealers often repost listings, which resets the posted date. The *days in snapshots* figure on each listing page is the more reliable count.
- **Two metrics can reward odd things.** *Price per owner* gets better as the owner count rises, and *depreciation per km* gets better with high mileage, which partly offsets *annual mileage*. Check the spec sheet before trusting a high score on either.

</div>

## Excluded from scoring

```js
const exclusionRows = Object.entries(pool.excluded)
  .filter(([, count]) => count > 0)
  .map(([key, count]) => ({reason: exclusionLabels[key] ?? key, count}))
  .sort((a, b) => b.count - a.count);

display(dataTable({
  caption: `${integer(excludedTotal)} of ${integer(pool.total_source_listings)} scraped listings were left out because they can't be compared fairly on these metrics.`,
  columns: [
    {key: "reason", label: "Reason"},
    {key: "count", label: "Listings", numeric: true, format: integer}
  ],
  rows: exclusionRows
}));
```

## Try your own weights

<p class="prose">Move the sliders to re-rank today's pool. Weights are rescaled to add up to 100%. Metric scores stay as computed, so this shows how sensitive the ranking is to what you care about.</p>

<div class="weights-form">

```js
function weightSlider(metric) {
  const slider = Inputs.range([0, 0.5], {label: METRICS[metric].label, step: 0.01, value: weights[metric]});
  slider.querySelector("input[type=range]").setAttribute("aria-label", `${METRICS[metric].label} weight`);
  return slider;
}

const customWeights = view(Inputs.form(Object.fromEntries(metrics.map((metric) => [metric, weightSlider(metric)]))));
```

</div>

```js
const weightTotal = d3.sum(Object.values(customWeights)) || 1;
const reranked = listings
  .map((listing) => ({
    ...listing,
    customScore: d3.sum(metrics, (metric) => listing.metric_scores[metric] * customWeights[metric]) / weightTotal
  }))
  .sort((a, b) => b.customScore - a.customScore)
  .slice(0, 20)
  .map((listing, index) => ({...listing, customRank: index + 1, shift: listing.rank - (index + 1)}));
const keptInTop20 = reranked.filter((listing) => listing.rank <= 20).length;

display(html`<p class="muted" role="status">${keptInTop20} of the default top 20 stay in your top 20.</p>`);
display(html`<div class="table-scroll"><table class="data">
  <caption>Top 20 under your weights</caption>
  <thead><tr>
    <th scope="col" class="num">#</th><th scope="col">Car</th><th scope="col" class="num">Default rank</th>
    <th scope="col" class="num">Price</th><th scope="col" class="num">COE left</th><th scope="col" class="num">Your score</th>
  </tr></thead>
  <tbody>${reranked.map((listing) => html`<tr>
    <td class="num">${listing.customRank}</td>
    <td><a href="/detail#${listing.id}">${listing.title}</a></td>
    <td class="num">${integer(listing.rank)} <span class="muted">${listing.shift > 0 ? `▲ ${listing.shift}` : listing.shift < 0 ? `▼ ${-listing.shift}` : "="}</span></td>
    <td class="num">${money(listing.price)}</td>
    <td class="num">${years(listing.coe_years_left)}</td>
    <td class="num">${listing.customScore.toFixed(2)}</td>
  </tr>`)}</tbody>
</table></div>`);
```
