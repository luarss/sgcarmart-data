---
title: Listing Detail — SGCM Value Watchlist
toc: false
---

```js
const watchlist = await FileAttachment("data/watchlist.json").json();
const top100 = watchlist.top_listings;
const weights = watchlist.scoring_weights;
const metricNames = Object.keys(weights);

const params = new URLSearchParams(location.search);
const listingId = params.get("id");
const listing = top100.find(l => l.id === listingId);

if (!listing) {
  display(htl.html`<div class="content" style="text-align:center; padding:80px 24px;">
    <h2>Listing not found</h2>
    <p style="color:var(--slate-500)">No listing with ID "${listingId}" in the current watchlist.</p>
    <a href="/" style="display:inline-block; margin-top:20px; padding:8px 20px; border-radius:20px; background:var(--slate-100); color:var(--slate-700); text-decoration:none; font-weight:500;">← Back to Top 100</a>
  </div>`);
}

if (listing) {

const idx = top100.indexOf(listing);
const prev = idx > 0 ? top100[idx - 1] : null;
const next = idx < top100.length - 1 ? top100[idx + 1] : null;

const avgScores = {};
for (const m of metricNames) {
  avgScores[m] = top100.reduce((s, l) => s + l.metric_scores[m], 0) / top100.length;
}

const fmtPrice = (n) => "$" + n.toLocaleString();
const sc = listing.composite_score;
const scoreCls = sc >= 0.9 ? "high" : sc >= 0.8 ? "mid" : "low";

const scoreData = metricNames.map(m => ({
  metric: m.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase()),
  key: m,
  score: listing.metric_scores[m],
  weight: weights[m],
  contribution: listing.metric_scores[m] * weights[m],
}));

display(htl.html`<div class="content">

<a href="/" class="back-link">← Back to Top 100</a>

<div class="detail-header">
  <div class="car-brand">${listing.brand}</div>
  <div class="car-title">${listing.title}</div>
  <div class="car-price">${fmtPrice(listing.price)} <span class="score-badge ${scoreCls}">Score: ${sc.toFixed(4)}</span></div>
  <div class="car-depr">$${listing.depreciation.toLocaleString()}/yr depreciation · Rank #${listing.rank} of ${top100.length}</div>

  <div class="detail-meta">
    <div class="meta-item"><div class="meta-val">${listing.age_years.toFixed(1)} yrs</div><div class="meta-lbl">Age</div></div>
    <div class="meta-item"><div class="meta-val">${listing.coe_years_left.toFixed(1)} yrs</div><div class="meta-lbl">COE Left</div></div>
    <div class="meta-item"><div class="meta-val">${listing.coe_category}</div><div class="meta-lbl">COE Cat</div></div>
    <div class="meta-item"><div class="meta-val">${listing.road_tax != null ? "$" + listing.road_tax.toLocaleString() + "/yr" : "N/A"}</div><div class="meta-lbl">Road Tax</div></div>
    <div class="meta-item"><div class="meta-val">${listing.mileage_km.toLocaleString()} km</div><div class="meta-lbl">Mileage</div></div>
    <div class="meta-item"><div class="meta-val">${listing.num_owners}</div><div class="meta-lbl">Owners</div></div>
    <div class="meta-item"><div class="meta-val">${listing.days_on_market} days</div><div class="meta-lbl">On Market</div></div>
    <div class="meta-item"><div class="meta-val">${(listing.value_retention * 100).toFixed(1)}%</div><div class="meta-lbl">Value Retention</div></div>
    <div class="meta-item"><div class="meta-val">${listing.is_direct_owner ? "Yes" : "No"}</div><div class="meta-lbl">Direct Owner</div></div>
  </div>
</div>

<div class="grid-2">

<div>

<h2>Metric Scores (Radar)</h2>

<div class="chart-container">
  <div class="radar-container" id="radarChart"></div>
</div>

</div>

<div>

<h2>Score Breakdown</h2>

<div class="chart-container">
${scoreData.map(d => {
  const pct = (d.score * 100).toFixed(1);
  const wPct = (d.weight * 100).toFixed(0);
  return htl.html`<div class="score-bar-row">
    <div class="score-bar-label">${d.metric} (${wPct}%)</div>
    <div class="score-bar-track">
      <div class="score-bar-fill" style="width:${pct}%"></div>
    </div>
    <div class="score-bar-val">${pct}</div>
  </div>`;
})}
</div>

<div class="chart-container" style="text-align:center;">
  <div style="font-size:0.9rem; color:var(--slate-500); margin-bottom:8px;">Composite Score Calculation</div>
  <div style="font-size:1.3rem; font-weight:700; color:var(--slate-800);">
    ${scoreData.map(d => (d.contribution * 100).toFixed(1) + "%").join(" + ")} = ${(sc * 100).toFixed(2)}%
  </div>
  <div style="font-size:0.75rem; color:var(--slate-400); margin-top:4px;">
    Sum of (normalized score × weight) for each metric
  </div>
</div>

<h2>Key Metrics</h2>

<div class="chart-container">
<table class="data-table">
<thead><tr><th>Metric</th><th>Value</th><th>Note</th></tr></thead>
<tbody>
<tr><td style="font-weight:600;">Body Price</td><td style="font-weight:700; color:var(--green-700);">$${Math.round(listing.body_price).toLocaleString()}</td><td style="font-size:0.8rem; color:var(--slate-500);">Price minus estimated COE value</td></tr>
<tr><td style="font-weight:600;">Body Depreciation Rate</td><td style="font-weight:700; color:var(--green-700);">${(listing.body_depreciation_rate * 100).toFixed(1)}%</td><td style="font-size:0.8rem; color:var(--slate-500);">Body depr / body price (lower = better)</td></tr>
<tr><td style="font-weight:600;">Body $ per COE Year</td><td style="font-weight:700; color:var(--green-700);">$${Math.round(listing.body_price_per_coe_year).toLocaleString()}</td><td style="font-size:0.8rem; color:var(--slate-500);">Body price / COE years left (lower = better)</td></tr>
<tr><td style="font-weight:600;">Depreciation per km</td><td style="font-weight:700; color:var(--green-700);">$${listing.depreciation_per_km.toFixed(2)}</td><td style="font-size:0.8rem; color:var(--slate-500);">Annual depr / km driven (lower = better)</td></tr>
<tr><td style="font-weight:600;">Price per Owner</td><td style="font-weight:700; color:var(--green-700);">$${Math.round(listing.price_per_owner).toLocaleString()}</td><td style="font-size:0.8rem; color:var(--slate-500);">Price / number of owners (lower = better)</td></tr>
<tr><td style="font-weight:600;">Annual Mileage</td><td style="font-weight:700; color:var(--green-700);">${Math.round(listing.annual_mileage).toLocaleString()} km</td><td style="font-size:0.8rem; color:var(--slate-500);">Mileage / age in years (lower = better)</td></tr>
<tr><td style="font-weight:600;">Road Tax</td><td style="font-weight:700; color:var(--green-700);">${listing.road_tax != null ? "$" + listing.road_tax.toLocaleString() + "/yr" : "N/A"}</td><td style="font-size:0.8rem; color:var(--slate-500);">Annual road tax (computed from engine capacity)</td></tr>
</tbody></table>
</div>

</div>
</div>

<div style="display:flex; justify-content:space-between; align-items:center; gap:16px; margin-top:32px; padding:20px; background:white; border-radius:var(--radius); box-shadow:var(--shadow);">
  <div>${prev ? htl.html`<a href="/detail?id=${prev.id}" style="padding:6px 16px; border-radius:20px; font-size:0.85rem; font-weight:500; text-decoration:none; color:var(--slate-600); background:var(--slate-100);">← #${prev.rank} ${prev.title.substring(0, 35)}...</a>` : htl.html`<span style="color:var(--slate-300); font-size:0.85rem;">← First in list</span>`}</div>
  <div style="font-weight:600; color:var(--slate-500);">#${listing.rank} of ${top100.length}</div>
  <div>${next ? htl.html`<a href="/detail?id=${next.id}" style="padding:6px 16px; border-radius:20px; font-size:0.85rem; font-weight:500; text-decoration:none; color:var(--slate-600); background:var(--slate-100);">#${next.rank} ${next.title.substring(0, 35)}... →</a>` : htl.html`<span style="color:var(--slate-300); font-size:0.85rem;">Last in list →</span>`}</div>
</div>

</div>`);

// Radar chart
const width = 380;
const height = 380;
const cx = width / 2;
const cy = height / 2;
const radius = 150;
const levels = 5;

const shortLabels = {
  "body_depreciation_rate": "Body Depr Rate",
  "body_price_per_coe_year": "Body $/COE yr",
  "depreciation_rate": "Depr Rate",
  "annual_mileage": "Annual Mileage",
  "depreciation_per_km": "Depr/km",
  "price_per_owner": "Price/Owner",
  "days_on_market": "Days Listed"
};

const axes = metricNames.map((m, i) => {
  const angle = (2 * Math.PI * i) / metricNames.length - Math.PI / 2;
  return { key: m, angle, label: shortLabels[m] || m };
});

const polarX = (angle, r) => cx + r * Math.cos(angle);
const polarY = (angle, r) => cy + r * Math.sin(angle);

const container = document.getElementById("radarChart");
if (container) {
  const svg = d3.select(container)
    .append("svg")
    .attr("viewBox", `0 0 ${width} ${height}`)
    .attr("width", width)
    .attr("height", height);

  for (let i = 1; i <= levels; i++) {
    const r = (radius / levels) * i;
    const pts = axes.map(a => `${polarX(a.angle, r)},${polarY(a.angle, r)}`).join(" ");
    svg.append("polygon")
      .attr("points", pts)
      .attr("fill", "none")
      .attr("stroke", i === levels ? "#cbd5e1" : "#e2e8f0")
      .attr("stroke-width", i === levels ? 1.5 : 0.5);
  }

  axes.forEach(a => {
    svg.append("line")
      .attr("x1", cx).attr("y1", cy)
      .attr("x2", polarX(a.angle, radius))
      .attr("y2", polarY(a.angle, radius))
      .attr("stroke", "#e2e8f0")
      .attr("stroke-width", 1);
  });

  axes.forEach(a => {
    const lx = polarX(a.angle, radius + 32);
    const ly = polarY(a.angle, radius + 32);
    svg.append("text")
      .attr("x", lx).attr("y", ly)
      .attr("text-anchor", "middle")
      .attr("dominant-baseline", "middle")
      .attr("font-size", "10px")
      .attr("fill", "#475569")
      .text(a.label);
  });

  for (let i = 1; i <= levels; i++) {
    const val = i / levels;
    const lx = polarX(axes[0].angle - 0.15, (radius / levels) * i);
    const ly = polarY(axes[0].angle - 0.15, (radius / levels) * i);
    svg.append("text")
      .attr("x", lx).attr("y", ly)
      .attr("text-anchor", "end")
      .attr("font-size", "9px")
      .attr("fill", "#94a3b8")
      .text(val.toFixed(1));
  }

  const avgPts = axes.map(a => {
    const r = radius * avgScores[a.key];
    return `${polarX(a.angle, r)},${polarY(a.angle, r)}`;
  }).join(" ");
  svg.append("polygon")
    .attr("points", avgPts)
    .attr("fill", "#94a3b8")
    .attr("fill-opacity", 0.2)
    .attr("stroke", "#94a3b8")
    .attr("stroke-width", 1.5)
    .attr("stroke-dasharray", "4 2");

  const listingPts = axes.map(a => {
    const r = radius * listing.metric_scores[a.key];
    return `${polarX(a.angle, r)},${polarY(a.angle, r)}`;
  }).join(" ");
  svg.append("polygon")
    .attr("points", listingPts)
    .attr("fill", "#22c55e")
    .attr("fill-opacity", 0.25)
    .attr("stroke", "#16a34a")
    .attr("stroke-width", 2);

  axes.forEach(a => {
    const r = radius * listing.metric_scores[a.key];
    svg.append("circle")
      .attr("cx", polarX(a.angle, r))
      .attr("cy", polarY(a.angle, r))
      .attr("r", 4)
      .attr("fill", "#16a34a")
      .append("title")
      .text(`${shortLabels[a.key] || a.key}: ${listing.metric_scores[a.key].toFixed(3)}`);
  });

  svg.append("circle").attr("cx", 30).attr("cy", height - 30).attr("r", 5).attr("fill", "#16a34a");
  svg.append("text").attr("x", 40).attr("y", height - 26).attr("font-size","10px").attr("fill","#475569").text("This listing");
  svg.append("line").attr("x1", 110).attr("y1", height - 30).attr("x2", 130).attr("y2", height - 30).attr("stroke", "#94a3b8").attr("stroke-dasharray", "4 2").attr("stroke-width",1.5);
  svg.append("text").attr("x", 135).attr("y", height - 26).attr("font-size","10px").attr("fill","#475569").text("Top 100 avg");
}

} // end if(listing)
```
