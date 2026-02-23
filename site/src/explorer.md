---
title: Price Explorer
---

# Price Explorer

```js
import {priceChart} from "./components/priceChart.js";
```

```js
const data = await FileAttachment("data/prices.json").json();
const snapshots = data.snapshots;
```

```js
// Read ?brand= URL param to pre-select on load
const params = new URLSearchParams(location.search);
const initialBrand = params.get("brand") ?? null;
```

```js
// Brand selector
const brands = [...new Set(snapshots.map(d => d.brand))].sort();
const brandSelect = Inputs.select(
  brands,
  {label: "Brand", value: initialBrand ?? brands[0],
   format: b => snapshots.find(d => d.brand === b)?.brand_display ?? b}
);
const selectedBrand = Generators.input(brandSelect);
display(brandSelect);
```

```js
// Model selector (filtered by brand)
const modelsForBrand = [...new Set(
  snapshots.filter(d => d.brand === selectedBrand).map(d => d.model)
)].sort();

const modelSelect = Inputs.select(modelsForBrand, {label: "Model", value: modelsForBrand[0]});
const selectedModel = Generators.input(modelSelect);
display(modelSelect);
```

```js
// Variant selector (multi-select, filtered by brand+model)
const variantsForModel = [...new Set(
  snapshots
    .filter(d => d.brand === selectedBrand && d.model === selectedModel)
    .map(d => d.variant)
)].sort();

const variantSelect = Inputs.checkbox(variantsForModel, {
  label: "Variants",
  value: variantsForModel.slice(0, Math.min(5, variantsForModel.length)),
});
const selectedVariants = Generators.input(variantSelect);
display(variantSelect);
```

```js
// Vehicle type filter
const typesAvailable = [...new Set(
  snapshots
    .filter(d => d.brand === selectedBrand && d.model === selectedModel)
    .map(d => d.vehicle_type)
    .filter(Boolean)
)].sort();

const typeFilter = Inputs.checkbox(typesAvailable, {
  label: "Vehicle type",
  value: typesAvailable,
});
const selectedTypes = Generators.input(typeFilter);
display(typeFilter);
```

```js
// Filtered data for chart
const chartData = snapshots.filter(d =>
  d.brand === selectedBrand &&
  d.model === selectedModel &&
  selectedVariants.includes(d.variant) &&
  selectedTypes.includes(d.vehicle_type)
);
```

```js
if (chartData.length === 0) {
  display(htl.html`<p style="color:var(--theme-foreground-muted)">No data for selected filters.</p>`);
} else {
  display(priceChart(chartData, {width}));
}
```

```js
// Raw data table
if (chartData.length > 0) {
  display(Inputs.table(
    [...chartData].sort((a, b) => b.date.localeCompare(a.date)),
    {
      columns: ["date", "variant", "vehicle_type", "list_price", "final_price"],
      header: {
        date: "Date", variant: "Variant", vehicle_type: "Type",
        list_price: "List Price", final_price: "Final Price",
      },
      format: {
        list_price: d => d != null ? `$${d.toLocaleString()}` : "—",
        final_price: d => d != null ? `$${d.toLocaleString()}` : "—",
      },
    }
  ));
}
```
