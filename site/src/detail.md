---
title: Listing
---

```js
import {METRICS, activeMetrics, money, compactMoney, integer, years, percent, longDate, shortDate, parseDate, metricValue, topShare, priceDrop, modelKey, coeShort} from "./components/format.js";
import {plotDefaults, figure, dataTable, tokens} from "./components/plot.js";

const pool = await FileAttachment("data/pool.json").json();
const listings = pool.listings;
const weights = pool.weights;
const metrics = activeMetrics(weights);
const byId = new Map(listings.map((listing) => [listing.id, listing]));
const medianScore = Object.fromEntries(metrics.map((metric) => [metric, d3.median(listings, (listing) => listing.metric_scores[metric])]));
const sortedRaw = Object.fromEntries(metrics.map((metric) => [metric, listings.map((listing) => listing[metric]).sort(d3.ascending)]));
```

```js
const listingId = Generators.observe((notify) => {
  const update = () => notify(decodeURIComponent(location.hash.replace(/^#/, "")) || null);
  update();
  addEventListener("hashchange", update);
  return () => removeEventListener("hashchange", update);
});
```

```js
const listing = byId.get(listingId) ?? null;
```

```js
if (!listing) {
  display(html`<h1>Listing not found</h1>
    <p class="dek">${listingId ? html`Listing <span class="mono">${listingId}</span> isn't in today's scored pool. It may have sold, been excluded, or the link may be out of date.` : "No listing was selected."}</p>
    <p><a href="/">← Back to today's picks</a></p>`);
}
```

```js
if (listing) {
  const drop = priceDrop(listing);
  const shareBeaten = (metric) => {
    const values = sortedRaw[metric];
    return (values.length - d3.bisectRight(values, listing[metric])) / values.length;
  };

  const breakdown = metrics.map((metric) => ({
    metric,
    label: METRICS[metric].label,
    weight: weights[metric],
    score: listing.metric_scores[metric],
    median: medianScore[metric],
    contribution: listing.metric_scores[metric] * weights[metric],
    raw: listing[metric],
    betterThan: shareBeaten(metric)
  }));

  const history = listing.price_history.map(([date, price]) => ({date: parseDate(date), price}));
  const lastSeen = parseDate(pool.reference_date);
  const historyWithToday = history.length ? [...history, {date: lastSeen, price: history.at(-1).price}] : [];

  const comparables = listings
    .filter((other) => other.id !== listing.id && modelKey(other.title) === modelKey(listing.title))
    .slice(0, 8);

  const previous = byId.get(listings[listing.rank - 2]?.id);
  const next = byId.get(listings[listing.rank]?.id);

  display(html`<a class="breadcrumb" href="/">← Today's picks</a>
  <h1>${listing.title}</h1>
  <p class="dek">${listing.brand} · ${listing.dealer ?? "Dealer not listed"} · registered ${listing.reg_date ?? "—"}</p>

  <div class="headline-figures">
    <div><span>Price</span><b>${money(listing.price)}</b></div>
    <div><span>Value score</span><b>${listing.composite_score.toFixed(2)}</b></div>
    <div><span>Rank</span><b>#${integer(listing.rank)} <small class="muted" style="font-size: var(--t-sm)">of ${integer(listings.length)} · ${topShare(listing)}</small></b></div>
    ${drop ? html`<div><span>Below peak</span><b style="color: var(--good)">▼ ${money(drop)}</b></div>` : ""}
  </div>

  <p><a href="${listing.url}" target="_blank" rel="noopener noreferrer">View listing on SGCarMart<span class="sr-only"> (opens in a new tab)</span> ↗</a></p>`);

  const spec = [
    ["Depreciation", `${money(listing.depreciation)}/yr`],
    ["Body price (net of COE)", money(listing.body_price)],
    ["Age", years(listing.age_years)],
    ["COE left", years(listing.coe_years_left)],
    ["COE category", coeShort(listing.coe_category)],
    ["Engine", listing.eng_cap ?? "—"],
    ["Mileage", `${integer(listing.mileage_km)} km`],
    ["Owners", listing.num_owners ?? "—"],
    ["Direct owner", listing.is_direct_owner ? "Yes" : "No"],
    ["Road tax", listing.road_tax != null ? `${money(listing.road_tax)}/yr` : "—"],
    ["Instalment", listing.instalment ?? "—"],
    ["First seen", longDate(listing.first_seen)],
    ["Days in snapshots", integer(listing.days_seen)]
  ];

  const breakdownChart = figure({
    title: "What drives the score",
    caption: "Bars show this car's score on each metric (1 = best in today's pool). The tick marks the median listing. Metrics are ordered by weight, shown in brackets.",
    chart: resize((width) => Plot.plot(plotDefaults({
      ariaLabel: "Bar chart of this listing's score on each metric against the pool median",
      ariaDescription: breakdown.map((row) => `${row.label}: ${row.score.toFixed(2)}, median ${row.median.toFixed(2)}`).join("; "),
      width,
      height: 40 + breakdown.length * 34,
      marginLeft: Math.min(200, width * 0.42),
      x: {domain: [0, 1], label: "Metric score →", grid: true},
      y: {domain: breakdown.map((row) => row.label), label: null, tickFormat: (label) => {
        const row = breakdown.find((entry) => entry.label === label);
        return `${label} (${Math.round(row.weight * 100)}%)`;
      }},
      marks: [
        Plot.barX(breakdown, {x: "score", y: "label", fill: tokens.good, insetTop: 8, insetBottom: 8, ariaHidden: true}),
        Plot.tickX(breakdown, {x: "median", y: "label", stroke: tokens.ink, strokeWidth: 2, ariaHidden: true}),
        Plot.text(breakdown, {x: "score", y: "label", text: (row) => row.score.toFixed(2), dx: 4, textAnchor: "start", fill: tokens.ink, ariaHidden: true})
      ]
    }))),
    table: dataTable({
      caption: "Score breakdown by metric",
      columns: [
        {key: "label", label: "Metric"},
        {key: "raw", label: "This car", numeric: true, format: (value, row) => metricValue(row.metric, value)},
        {key: "betterThan", label: "Better than", numeric: true, format: (value) => `${percent(value, 0)} of pool`},
        {key: "score", label: "Score", numeric: true, format: (value) => value.toFixed(2)},
        {key: "weight", label: "Weight", numeric: true, format: (value) => percent(value, 0)},
        {key: "contribution", label: "Points", numeric: true, format: (value) => value.toFixed(3)}
      ],
      rows: breakdown
    })
  });
  breakdownChart.querySelector("details").open = true;

  display(html`<div class="split">
    <section aria-labelledby="spec-heading">
      <h2 id="spec-heading">Spec sheet</h2>
      <dl class="spec">${spec.map(([label, value]) => html.fragment`<dt>${label}</dt><dd>${value}</dd>`)}</dl>
    </section>
    <section aria-labelledby="score-heading">
      <h2 id="score-heading">Score breakdown</h2>
      ${breakdownChart}
    </section>
  </div>`);

  display(html`<h2>Asking price over time</h2>`);
  display(history.length > 1
    ? figure({
        title: `${history.length - 1} price change${history.length > 2 ? "s" : ""} since ${longDate(listing.first_seen)}`,
        caption: `Step line of the asking price on each daily snapshot. Peak ${money(listing.peak_price)}, now ${money(listing.price)}.`,
        chart: resize((width) => Plot.plot(plotDefaults({
          ariaLabel: "Step chart of asking price over time",
          ariaDescription: history.map((point) => `${shortDate(point.date)}: ${money(point.price)}`).join("; "),
          width,
          height: 220,
          marginLeft: 56,
          marginTop: 28,
          x: {label: null, tickFormat: shortDate, ticks: 5},
          y: {label: "↑ Price", tickFormat: compactMoney, grid: true, nice: true},
          marks: [
            Plot.lineY(historyWithToday, {x: "date", y: "price", curve: "step-after", stroke: tokens.good, strokeWidth: 2, ariaHidden: true}),
            Plot.dot(history, {x: "date", y: "price", fill: tokens.good, r: 3, ariaHidden: true})
          ]
        }))),
        table: dataTable({
          caption: "Price changes",
          columns: [
            {key: "date", label: "Date", format: (value) => shortDate(value)},
            {key: "price", label: "Price", numeric: true, format: money}
          ],
          rows: history
        })
      })
    : html`<p class="muted">No price change since this listing was first seen on ${longDate(listing.first_seen)}.</p>`);

  display(html`<h2>Same model in today's pool</h2>`);
  display(comparables.length
    ? html`<div class="table-scroll"><table class="data">
        <caption>${comparables.length} other ${modelKey(listing.title).replace(/\b\w/g, (letter) => letter.toUpperCase())} listing${comparables.length > 1 ? "s" : ""}, best value first</caption>
        <thead><tr>
          <th scope="col" class="num">Rank</th><th scope="col">Car</th><th scope="col" class="num">Price</th>
          <th scope="col" class="num">Age</th><th scope="col" class="num">COE left</th><th scope="col" class="num">km</th><th scope="col" class="num">Score</th>
        </tr></thead>
        <tbody>${comparables.map((other) => html`<tr>
          <td class="num">${integer(other.rank)}</td>
          <td><a href="/detail#${other.id}">${other.title}</a></td>
          <td class="num">${money(other.price)}</td>
          <td class="num">${years(other.age_years)}</td>
          <td class="num">${years(other.coe_years_left)}</td>
          <td class="num">${integer(other.mileage_km)}</td>
          <td class="num">${other.composite_score.toFixed(2)}</td>
        </tr>`)}</tbody>
      </table></div>`
    : html`<p class="muted">No other listings of this model in today's pool.</p>`);

  if (listing.description) {
    display(html`<h2>Seller's description</h2><p class="prose">${listing.description}</p>`);
  }

  display(html`<nav class="pager-links" aria-label="Adjacent listings">
    ${previous ? html`<a href="/detail#${previous.id}">← #${previous.rank} ${previous.title}</a>` : html`<span></span>`}
    ${next ? html`<a href="/detail#${next.id}">#${next.rank} ${next.title} →</a>` : ""}
  </nav>`);
}
```
