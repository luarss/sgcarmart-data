---
title: SGCarMart Price History
---

# SGCarMart Price History

Track Singapore car price changes across brands and models.

```js
const data = await FileAttachment("data/prices.json").json();
const snapshots = data.snapshots;
```

```js
// Summary stats
const brands = [...new Set(snapshots.map(d => d.brand))].sort();
const lastUpdated = snapshots.map(d => d.date).sort().at(-1);

// Per-brand stats
const brandStats = brands.map(brand => {
  const rows = snapshots.filter(d => d.brand === brand);
  const models = new Set(rows.map(d => d.model_key));
  const types = new Set(rows.map(d => d.vehicle_type).filter(Boolean));
  return {brand, display: rows[0].brand_display, models: models.size, types: [...types]};
});
```

<div class="stats-row">
  <div class="stat-card">
    <div class="stat-value">${brands.length}</div>
    <div class="stat-label">Brands tracked</div>
  </div>
  <div class="stat-card">
    <div class="stat-value">${snapshots.length.toLocaleString()}</div>
    <div class="stat-label">Price snapshots</div>
  </div>
  <div class="stat-card">
    <div class="stat-value">${lastUpdated ?? "—"}</div>
    <div class="stat-label">Last updated</div>
  </div>
</div>

## Browse by Brand

```js
const typeColors = {ICE: "#6b7280", Hybrid: "#16a34a", Electric: "#2563eb"};

function typeBadge(type) {
  const color = typeColors[type] ?? "#6b7280";
  return htl.html`<span style="background:${color};color:white;font-size:0.7rem;padding:1px 6px;border-radius:9999px;margin-right:3px">${type}</span>`;
}

const brandGrid = htl.html`<div class="brand-grid">
  ${brandStats.map(b => htl.html`
    <a class="brand-card" href="explorer?brand=${b.brand}">
      <div class="brand-name">${b.display}</div>
      <div class="brand-models">${b.models} model${b.models !== 1 ? "s" : ""}</div>
      <div class="brand-badges">${b.types.map(typeBadge)}</div>
    </a>
  `)}
</div>`;

display(brandGrid);
```

<style>
.stats-row {
  display: flex;
  gap: 1.5rem;
  margin: 1.5rem 0 2rem;
  flex-wrap: wrap;
}
.stat-card {
  background: var(--theme-background-alt);
  border: 1px solid var(--theme-foreground-faintest);
  border-radius: 8px;
  padding: 1.25rem 1.75rem;
  min-width: 160px;
  flex: 1;
}
.stat-value {
  font-size: 2rem;
  font-weight: 700;
  line-height: 1.1;
}
.stat-label {
  color: var(--theme-foreground-muted);
  font-size: 0.875rem;
  margin-top: 0.25rem;
}
.brand-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 0.75rem;
  margin-top: 1rem;
}
.brand-card {
  background: var(--theme-background-alt);
  border: 1px solid var(--theme-foreground-faintest);
  border-radius: 8px;
  padding: 1rem;
  text-decoration: none;
  color: inherit;
  transition: border-color 0.15s;
}
.brand-card:hover {
  border-color: var(--theme-foreground-focus);
}
.brand-name {
  font-weight: 600;
  margin-bottom: 0.25rem;
}
.brand-models {
  font-size: 0.8rem;
  color: var(--theme-foreground-muted);
  margin-bottom: 0.5rem;
}
</style>
