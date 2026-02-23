---
title: Brands
---

# All Brands

```js
const data = await FileAttachment("data/prices.json").json();
const snapshots = data.snapshots;
```

```js
const brands = [...new Set(snapshots.map(d => d.brand))].sort();

const brandRows = brands.map(brand => {
  const rows = snapshots.filter(d => d.brand === brand);
  const models = new Set(rows.map(d => d.model_key)).size;
  const types = [...new Set(rows.map(d => d.vehicle_type).filter(Boolean))].sort().join(", ");
  const dates = rows.map(d => d.date).sort();
  return {
    Brand: rows[0].brand_display,
    brand_slug: brand,
    Models: models,
    "Vehicle types": types,
    "Earliest date": dates[0],
    "Latest date": dates.at(-1),
  };
});
```

```js
const search = Inputs.search(brandRows, {placeholder: "Search brands…"});
const filtered = Generators.input(search);
display(search);
```

```js
display(Inputs.table(filtered, {
  columns: ["Brand", "Models", "Vehicle types", "Earliest date", "Latest date"],
  format: {
    Brand: (v, i) => {
      const slug = filtered[i]?.brand_slug ?? v.toLowerCase();
      return htl.html`<a href="explorer?brand=${slug}">${v}</a>`;
    },
  },
  sort: "Brand",
}));
```
