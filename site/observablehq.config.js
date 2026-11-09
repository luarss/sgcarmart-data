const navigation = [
  {name: "Picks", path: "/"},
  {name: "Market", path: "/market"},
  {name: "Method", path: "/method"}
];

export default {
  root: "src",
  title: "SGCM Value Watchlist",
  pages: navigation,
  base: "/",
  theme: ["air", "near-midnight"],
  sidebar: false,
  toc: false,
  pager: false,
  style: "style.css",
  head: `<script>document.documentElement.lang="en";document.querySelector('meta[name="viewport"]')?.setAttribute("content","width=device-width, initial-scale=1");</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter+Tight:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&family=Source+Serif+4:opsz,wght@8..60,600&display=swap">`,
  header: ({path}) => `<a class="skip-link" href="#observablehq-main">Skip to content</a>
<nav class="masthead" aria-label="Primary">
  <a class="wordmark" href="/">SGCM<span aria-hidden="true">/</span><b>VALUE</b></a>
  <ul>${navigation
    .map(({name, path: target}) => {
      const current = target === "/" ? path === "/index" || path === "/detail" : path === target;
      return `<li><a href="${target}"${current ? ` aria-current="page"` : ""}>${name}</a></li>`;
    })
    .join("")}</ul>
</nav>`,
  footer: `Data: SGCarMart used-car snapshots, COE results via data.gov.sg. Educational use only — not financial advice.`
};
