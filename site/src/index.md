---
title: Picks
---

```js
import {METRICS, activeMetrics, money, compactMoney, integer, years, longDate, topShare, priceDrop, coeShort} from "./components/format.js";
import {plotDefaults, figure, dataTable, tokens} from "./components/plot.js";

const pool = await FileAttachment("data/pool.json").json();
const market = await FileAttachment("data/market.json").json();

const listings = pool.listings;
const weights = pool.weights;
const metrics = activeMetrics(weights);
const latestDay = market.days.at(-1);
const recentPartials = market.days.slice(-14).filter((day) => day.partial);
const categoryCounts = d3.rollup(listings, (group) => group.length, (listing) => listing.coe_category);
const top100CatA = listings.slice(0, 100).filter((listing) => listing.coe_category === "Category A").length;
```

# Best-value used cars, today

<p class="dek">${integer(pool.scored_listings)} listings priced ${compactMoney(pool.filters.min_price)}–${compactMoney(pool.filters.max_price)}, registered ${pool.filters.year_from} or later, ranked by what you pay for the car itself once the COE is netted out.</p>

<dl class="kpis">
  <div><dt>Scored</dt><dd>${integer(pool.scored_listings)}<small>of ${integer(pool.total_source_listings)} scraped</small></dd></div>
  <div><dt>COE Cat A</dt><dd>${money(pool.coe.category_a_latest.premium)}<small>${pool.coe.category_a_latest.month}</small></dd></div>
  <div><dt>COE Cat B</dt><dd>${money(pool.coe.category_b_latest.premium)}<small>${pool.coe.category_b_latest.month}</small></dd></div>
  <div><dt>As of</dt><dd>${longDate(pool.reference_date)}<small>refreshed daily</small></dd></div>
</dl>

```js
if (latestDay.partial) {
  display(html`<p class="notice" role="status"><strong>Partial scrape.</strong> Today's snapshot has only ${integer(latestDay.count)} listings, so scores are ranked against a much smaller pool than usual. Treat the ranking with caution.</p>`);
} else if (recentPartials.length) {
  display(html`<p class="notice" role="status"><strong>Note:</strong> ${recentPartials.length} of the last 14 daily scrapes were partial (${recentPartials.map((day) => longDate(day.date)).join(", ")}). Today's run is complete.</p>`);
}
```

## Filter the list

<div class="filters">

```js
const search = view(Inputs.search(listings, {label: "Search", placeholder: "Make, model or dealer", columns: ["title", "dealer"]}));
```

```js
const category = view(Inputs.radio(["All", "Cat A", "Cat B"], {label: "COE category", value: "All"}));
```

```js
const maxPriceInput = Inputs.range([pool.filters.min_price, pool.filters.max_price], {label: "Max price (S$)", step: 1000, value: pool.filters.max_price});
maxPriceInput.querySelector("input[type=range]").setAttribute("aria-label", "Max price (S$)");
const maxPrice = view(maxPriceInput);
```

```js
const minCoeInput = Inputs.range([0, 10], {label: "Min COE left (years)", step: 0.5, value: 0});
minCoeInput.querySelector("input[type=range]").setAttribute("aria-label", "Min COE left (years)");
const minCoe = view(minCoeInput);
```

```js
const options = view(Inputs.checkbox(["Price dropped", "Direct owner"], {label: "Only show"}));
```

</div>

```js
const filtered = search.filter((listing) =>
  (category === "All" || coeShort(listing.coe_category) === category) &&
  listing.price <= maxPrice &&
  listing.coe_years_left >= minCoe &&
  (!options.includes("Price dropped") || priceDrop(listing) > 0) &&
  (!options.includes("Direct owner") || listing.is_direct_owner)
);
const filteredIds = new Set(filtered.map((listing) => listing.id));
```

```js
const pageSize = 25;
const shownCount = Mutable(pageSize);
const showMore = () => (shownCount.value += pageSize);
const resetShown = () => (shownCount.value = pageSize);
```

```js
filtered, resetShown();
```

## Ranked list

```js
function contributionBar(listing) {
  const bar = html`<span class="stack" aria-hidden="true">${metrics.map((metric) => {
    const contribution = listing.metric_scores[metric] * weights[metric];
    return html`<span style="width:${(contribution * 100).toFixed(2)}%" title="${METRICS[metric].label}: ${contribution.toFixed(3)} of ${weights[metric].toFixed(2)}"></span>`;
  })}</span>`;
  return bar;
}

function row(listing) {
  const drop = priceDrop(listing);
  return html`<tr class=${listing.rank <= 10 ? "top10" : ""}>
    <td class="rank">${listing.rank}</td>
    <td class="car">
      <a class="car-title" href="/detail#${listing.id}">${listing.title}</a>
      <span class="car-sub">${listing.brand} · ${years(listing.age_years)} old · ${years(listing.coe_years_left)} COE left · ${coeShort(listing.coe_category)} · ${integer(listing.mileage_km)} km</span>
    </td>
    <td class="num" data-label="Price">${money(listing.price)}${drop ? html`<br><span class="tag">▼ ${money(drop)} off peak</span>` : ""}</td>
    <td class="num" data-label="Depr./yr">${money(listing.depreciation)}</td>
    <td class="score">
      <div class="score-cell">
        ${contributionBar(listing)}
        <div class="score-figure"><b>${listing.composite_score.toFixed(2)}</b><small>${topShare(listing)}</small></div>
      </div>
    </td>
  </tr>`;
}

const visible = filtered.slice(0, shownCount);

display(filtered.length
  ? html`<div class="table-scroll"><table class="ranked">
      <caption>Showing ${integer(visible.length)} of ${integer(filtered.length)} matching listings, ranked by value score across all ${integer(listings.length)} scored cars. The bar shows how much each of the ${metrics.length} weighted metrics contributes to the score.</caption>
      <thead><tr>
        <th scope="col" class="num">#</th>
        <th scope="col">Car</th>
        <th scope="col" class="num">Price</th>
        <th scope="col" class="num">Depr./yr</th>
        <th scope="col" class="num">Value score</th>
      </tr></thead>
      <tbody>${visible.map(row)}</tbody>
    </table></div>`
  : html`<p class="muted">No listings match these filters.</p>`);

if (visible.length < filtered.length) {
  display(html`<div class="more"><button class="button" onclick=${showMore}>Show ${Math.min(pageSize, filtered.length - visible.length)} more</button><span>${integer(filtered.length - visible.length)} more match</span></div>`);
}
```

## How the picks sit in the market

<div class="charts">

```js
const topThreshold = listings[Math.min(99, listings.length - 1)].composite_score;
const scoreBins = d3.bin().domain([0, 1]).thresholds(d3.range(0, 1.0001, 0.025)).value((listing) => listing.composite_score)(listings);
const scoreRows = scoreBins.filter((bin) => bin.length).map((bin) => ({
  range: `${bin.x0.toFixed(3)}–${bin.x1.toFixed(3)}`,
  all: bin.length,
  matching: bin.filter((listing) => filteredIds.has(listing.id)).length
}));

display(figure({
  title: "Score distribution",
  caption: `Each bar counts listings in a score band; green is the part that matches your filters. The dashed line marks the top-100 cut-off (${topThreshold.toFixed(2)}). Scores are relative: 1.0 is the best on each metric within today's pool, not an absolute grade.`,
  chart: resize((width) => Plot.plot(plotDefaults({
    ariaLabel: "Histogram of value scores for all scored listings",
    ariaDescription: `Most listings score between ${d3.quantile(listings, 0.05, (listing) => listing.composite_score).toFixed(2)} and ${d3.quantile(listings, 0.95, (listing) => listing.composite_score).toFixed(2)}. The top-100 cut-off is ${topThreshold.toFixed(2)}.`,
    width,
    height: 240,
    x: {label: "Value score →", domain: [0, 1], grid: false},
    y: {label: "↑ Listings", grid: true},
    marks: [
      Plot.rectY(listings, Plot.binX({y: "count"}, {x: "composite_score", interval: 0.025, fill: tokens.faint, fillOpacity: 0.35, inset: 0.5, ariaHidden: true})),
      Plot.rectY(filtered, Plot.binX({y: "count"}, {x: "composite_score", interval: 0.025, fill: tokens.good, inset: 0.5, ariaHidden: true})),
      Plot.ruleX([topThreshold], {stroke: tokens.ink, strokeDasharray: "3 3", ariaHidden: true}),
      Plot.text([topThreshold], {x: (value) => value, frameAnchor: "top", dx: -4, dy: 2, textAnchor: "end", text: () => "top 100", fill: tokens.ink, ariaHidden: true}),
      Plot.ruleY([0], {stroke: tokens.ink, ariaHidden: true})
    ]
  }))),
  table: dataTable({
    caption: "Listings per score band",
    columns: [
      {key: "range", label: "Score band"},
      {key: "all", label: "All listings", numeric: true, format: integer},
      {key: "matching", label: "Matching filters", numeric: true, format: integer}
    ],
    rows: scoreRows
  })
}));
```

```js
display(figure({
  title: "Price vs. body price per COE year",
  caption: "Each dot is a listing. Lower is better on the vertical axis: it is what the car itself costs, net of COE, per year of COE left. Green dots match your filters; hover or tap a dot for details. The ranked list above is the accessible version of this chart.",
  chart: resize((width) => Plot.plot(plotDefaults({
    ariaLabel: "Scatter plot of asking price against body price per COE year",
    ariaDescription: `Shows ${integer(listings.length)} listings, ${integer(filtered.length)} of them highlighted.`,
    width,
    height: 300,
    marginLeft: 52,
    x: {label: "Price →", tickFormat: (value) => compactMoney(value), ticks: 5},
    y: {label: "↑ Body S$ / COE year", tickFormat: (value) => compactMoney(value), grid: true, type: "log"},
    marks: [
      Plot.dot(listings.filter((listing) => !filteredIds.has(listing.id)), {x: "price", y: "body_price_per_coe_year", r: 2, fill: tokens.faint, fillOpacity: 0.3, ariaHidden: true}),
      Plot.dot(filtered, {x: "price", y: "body_price_per_coe_year", r: 3, fill: tokens.good, fillOpacity: 0.8, ariaHidden: true}),
      Plot.tip(listings, Plot.pointer({x: "price", y: "body_price_per_coe_year", title: (listing) => `#${listing.rank} ${listing.title}\n${money(listing.price)} · score ${listing.composite_score.toFixed(2)}\n${money(listing.body_price_per_coe_year)} body / COE yr`, fontFamily: "var(--font-mono)", ariaHidden: true}))
    ]
  })))
}));
```

</div>

<p class="muted" style="margin-top: var(--s5); font-size: var(--t-sm);">Today ${integer(top100CatA)} of the top 100 are Category A (≤1,600 cc), against ${integer(categoryCounts.get("Category A") ?? 0)} Cat A and ${integer(categoryCounts.get("Category B") ?? 0)} Cat B in the scored pool. Use the COE category filter to compare like with like. <a href="/method">How the score works →</a></p>
