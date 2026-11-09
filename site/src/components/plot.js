export const tokens = {
  ink: "var(--ink)",
  muted: "var(--muted)",
  faint: "var(--faint)",
  rule: "var(--rule)",
  good: "var(--good)",
  link: "var(--link)"
};

export function plotDefaults({ariaLabel, ariaDescription, ...options}) {
  return {
    ariaLabel,
    ariaDescription,
    style: {
      fontFamily: "var(--font-mono)",
      fontSize: "11px",
      color: "var(--muted)",
      background: "transparent",
      overflow: "visible"
    },
    marginTop: 16,
    ...options
  };
}

export function figure({title, caption, chart, table}) {
  const element = document.createElement("figure");
  element.className = "chart";
  const heading = document.createElement("h3");
  heading.textContent = title;
  element.append(heading, chart);
  const figcaption = document.createElement("figcaption");
  figcaption.textContent = caption;
  element.append(figcaption);
  if (table) {
    const details = document.createElement("details");
    details.className = "data-view";
    const summary = document.createElement("summary");
    summary.textContent = "View data as table";
    details.append(summary, table);
    element.append(details);
  }
  return element;
}

export function dataTable({caption, columns, rows}) {
  const wrapper = document.createElement("div");
  wrapper.className = "table-scroll";
  const table = document.createElement("table");
  table.className = "data";
  const captionElement = document.createElement("caption");
  captionElement.textContent = caption;
  table.append(captionElement);
  const head = table.createTHead().insertRow();
  for (const column of columns) {
    const th = document.createElement("th");
    th.scope = "col";
    th.textContent = column.label;
    if (column.numeric) th.className = "num";
    head.append(th);
  }
  const body = table.createTBody();
  for (const row of rows) {
    const tr = body.insertRow();
    for (const column of columns) {
      const td = tr.insertCell();
      td.textContent = column.format ? column.format(row[column.key], row) : row[column.key];
      if (column.numeric) td.className = "num";
    }
  }
  wrapper.append(table);
  return wrapper;
}
