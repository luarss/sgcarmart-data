---
title: Market
---

```js
import {money, compactMoney, integer, longDate, shortDate, parseDate} from "./components/format.js";
import {plotDefaults, figure, dataTable, tokens} from "./components/plot.js";

const market = await FileAttachment("data/market.json").json();
const pool = await FileAttachment("data/pool.json").json();

const days = market.days.map((day) => ({...day, day: parseDate(day.date)}));
const healthy = days.filter((day) => !day.partial);
const partial = days.filter((day) => day.partial);
const recent = healthy.slice(-30);

const coe = market.coe.map((point) => ({
  ...point,
  date: parseDate(`${point.month}-${point.round === 1 ? "01" : "15"}`),
  label: point.category.replace("Category ", "Cat ")
}));
const latestCoe = d3.rollup(coe, (points) => points.at(-1), (point) => point.label);
const yearAgoCoe = d3.rollup(coe.filter((point) => point.date <= d3.timeYear.offset(coe.at(-1).date, -1)), (points) => points.at(-1), (point) => point.label);

const coeChange = (label) => {
  const now = latestCoe.get(label)?.premium;
  const before = yearAgoCoe.get(label)?.premium;
  if (!now || !before) return "";
  const change = (now - before) / before;
  return `${change >= 0 ? "▲ +" : "▼ −"}${Math.abs(change * 100).toFixed(1)}% vs a year ago`;
};
```

# The market behind the picks

<p class="dek">COE premiums set the floor under every used-car price in Singapore. Below that, the daily snapshots show how much stock is on the market and how often sellers cut prices.</p>

<dl class="kpis">
  <div><dt>COE Cat A</dt><dd>${money(latestCoe.get("Cat A").premium)}<small>${coeChange("Cat A")}</small></dd></div>
  <div><dt>COE Cat B</dt><dd>${money(latestCoe.get("Cat B").premium)}<small>${coeChange("Cat B")}</small></dd></div>
  <div><dt>Median ask</dt><dd>${money(healthy.at(-1).median_price)}<small>${longDate(healthy.at(-1).date)}</small></dd></div>
  <div><dt>Price cuts / day</dt><dd>${integer(d3.median(recent, (day) => day.price_drops))}<small>median, last 30 complete days</small></dd></div>
</dl>

## COE premiums

```js
const coeLabels = Array.from(latestCoe.values());

display(figure({
  title: `Quota premium per bidding round since ${coe[0].month.slice(0, 4)}`,
  caption: "COE premiums are the main reason prices move. A car's body price, which the value score uses, is its asking price minus the remaining value of its COE.",
  chart: resize((width) => Plot.plot(plotDefaults({
    ariaLabel: "Line chart of COE premiums for Category A and Category B over time",
    ariaDescription: coeLabels.map((point) => `${point.label} latest ${money(point.premium)} in ${point.month}`).join("; "),
    width,
    height: 300,
    marginLeft: 56,
    marginRight: Math.min(80, width * 0.15),
    x: {label: null},
    y: {label: "↑ Premium", tickFormat: compactMoney, grid: true, domain: [0, d3.max(coe, (point) => point.premium) * 1.05]},
    marks: [
      Plot.ruleY([0], {stroke: tokens.ink, ariaHidden: true}),
      Plot.lineY(coe, {x: "date", y: "premium", z: "label", stroke: (point) => point.label === "Cat A" ? "var(--good)" : "var(--link)", strokeWidth: 1.75, ariaHidden: true}),
      Plot.text(coeLabels, {x: "date", y: "premium", text: (point) => `${point.label} ${compactMoney(point.premium)}`, dx: 6, textAnchor: "start", fill: (point) => point.label === "Cat A" ? "var(--good)" : "var(--link)", fontWeight: 600, ariaHidden: true}),
      Plot.tip(coe, Plot.pointerX({x: "date", y: "premium", title: (point) => `${point.label} · ${point.month} round ${point.round}\n${money(point.premium)}`, fontFamily: "var(--font-mono)", ariaHidden: true}))
    ]
  }))),
  table: dataTable({
    caption: "COE premiums, most recent 24 rounds",
    columns: [
      {key: "month", label: "Month"},
      {key: "round", label: "Round", numeric: true},
      {key: "label", label: "Category"},
      {key: "premium", label: "Premium", numeric: true, format: money}
    ],
    rows: coe.slice(-48).reverse()
  })
}));
```

## Daily snapshots

<div class="charts">

```js
display(figure({
  title: "Listings captured per day",
  caption: `Bars are complete daily scrapes. Hollow bars are the ${partial.length} partial or failed scrapes, which are left out of every other chart and of price-change counts.`,
  chart: resize((width) => Plot.plot(plotDefaults({
    ariaLabel: "Bar chart of listings captured per daily snapshot",
    ariaDescription: `${healthy.length} complete days and ${partial.length} partial days. Latest complete day: ${integer(healthy.at(-1).count)} listings.`,
    width,
    height: 240,
    marginLeft: 48,
    x: {label: null, type: "utc", interval: null},
    y: {label: "↑ Listings", grid: true},
    marks: [
      Plot.rectY(healthy, {x1: "day", x2: (day) => d3.timeDay.offset(day.day, 1), y: "count", fill: tokens.good, inset: 0.5, ariaHidden: true}),
      Plot.rectY(partial, {x1: "day", x2: (day) => d3.timeDay.offset(day.day, 1), y: (day) => Math.max(day.count, 1), fill: "none", stroke: "var(--warn)", ariaHidden: true}),
      Plot.ruleY([0], {stroke: tokens.ink, ariaHidden: true}),
      Plot.tip(days, Plot.pointerX({x: "day", y: "count", title: (day) => `${longDate(day.date)}\n${integer(day.count)} listings${day.partial ? " · partial scrape" : ""}`, fontFamily: "var(--font-mono)", ariaHidden: true}))
    ]
  }))),
  table: dataTable({
    caption: "Partial or failed scrapes",
    columns: [
      {key: "date", label: "Date", format: longDate},
      {key: "count", label: "Listings", numeric: true, format: integer}
    ],
    rows: [...partial].reverse()
  })
}));
```

```js
display(figure({
  title: "Price cuts per day",
  caption: "Listings whose asking price fell since the previous complete snapshot. Spikes often follow a COE result.",
  chart: resize((width) => Plot.plot(plotDefaults({
    ariaLabel: "Bar chart of listings with a price cut per day",
    ariaDescription: `Median ${integer(d3.median(recent, (day) => day.price_drops))} price cuts a day over the last 30 complete days.`,
    width,
    height: 240,
    marginLeft: 48,
    x: {label: null},
    y: {label: "↑ Listings cut", grid: true},
    marks: [
      Plot.rectY(healthy.filter((day) => day.price_drops != null), {x1: "day", x2: (day) => d3.timeDay.offset(day.day, 1), y: "price_drops", fill: tokens.good, inset: 0.5, ariaHidden: true}),
      Plot.ruleY([0], {stroke: tokens.ink, ariaHidden: true}),
      Plot.tip(healthy, Plot.pointerX({x: "day", y: "price_drops", title: (day) => `${longDate(day.date)}\n${integer(day.price_drops)} cuts${day.median_drop ? ` · median ${money(day.median_drop)}` : ""}`, fontFamily: "var(--font-mono)", ariaHidden: true}))
    ]
  }))),
  table: dataTable({
    caption: "Price cuts, last 30 complete days",
    columns: [
      {key: "date", label: "Date", format: longDate},
      {key: "price_drops", label: "Cuts", numeric: true, format: integer},
      {key: "median_drop", label: "Median cut", numeric: true, format: money},
      {key: "new_listings", label: "New listings", numeric: true, format: integer}
    ],
    rows: [...recent].reverse()
  })
}));
```

</div>

```js
display(figure({
  title: "Median asking price",
  caption: `The vertical axis spans the full ${compactMoney(pool.filters.min_price)}–${compactMoney(pool.filters.max_price)} search band, so a flat line means prices are stable. Shifts mostly reflect which cars are listed that day, not a change in what any one car is worth.`,
  chart: resize((width) => Plot.plot(plotDefaults({
    ariaLabel: "Line chart of the median asking price per day",
    ariaDescription: `Median asking price moved from ${money(healthy[0].median_price)} to ${money(healthy.at(-1).median_price)}.`,
    width,
    height: 220,
    marginLeft: 56,
    marginTop: 28,
    x: {label: null, ticks: 6},
    y: {label: "↑ Median price", tickFormat: compactMoney, grid: true, domain: [pool.filters.min_price, pool.filters.max_price]},
    marks: [
      Plot.lineY(healthy, {x: "day", y: "median_price", stroke: tokens.ink, strokeWidth: 1.5, ariaHidden: true}),
      Plot.tip(healthy, Plot.pointerX({x: "day", y: "median_price", title: (day) => `${longDate(day.date)}\n${money(day.median_price)}`, fontFamily: "var(--font-mono)", ariaHidden: true}))
    ]
  })))
}));
```
