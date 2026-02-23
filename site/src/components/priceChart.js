import * as Plot from "npm:@observablehq/plot";

export function priceChart(data, {width} = {}) {
  const listData = data.filter(d => d.list_price != null);
  const finalData = data.filter(d => d.final_price != null);

  return Plot.plot({
    width,
    marginLeft: 80,
    marks: [
      Plot.line(listData, {
        x: d => new Date(d.date),
        y: "list_price",
        stroke: "variant",
        tip: true,
        title: d => `${d.variant}\n${d.date}\n$${d.list_price.toLocaleString()}`,
      }),
      Plot.dot(listData, {
        x: d => new Date(d.date),
        y: "list_price",
        stroke: "variant",
        fill: "white",
        r: 3,
      }),
      ...(finalData.length > 0
        ? [
            Plot.line(finalData, {
              x: d => new Date(d.date),
              y: "final_price",
              stroke: "variant",
              strokeDasharray: "4,3",
              strokeOpacity: 0.6,
              tip: true,
              title: d => `${d.variant} (final)\n${d.date}\n$${d.final_price.toLocaleString()}`,
            }),
          ]
        : []),
    ],
    x: {type: "utc", label: "Date"},
    y: {
      label: "List Price (SGD)",
      tickFormat: d => `$${(d / 1000).toFixed(0)}k`,
    },
    color: {legend: true},
  });
}
