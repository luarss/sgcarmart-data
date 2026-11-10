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
  head: `<script>try{var storedTheme=localStorage.getItem("theme");if(storedTheme==="light"||storedTheme==="dark")document.documentElement.dataset.theme=storedTheme}catch(error){}</script>
<script>document.documentElement.lang="en";document.querySelector('meta[name="viewport"]')?.setAttribute("content","width=device-width, initial-scale=1");</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter+Tight:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&family=Source+Serif+4:opsz,wght@8..60,600&display=swap">`,
  header: ({path}) => `<a class="skip-link" href="#observablehq-main">Skip to content</a>
<nav class="masthead" aria-label="Primary">
  <a class="wordmark" href="/">SGCM<span aria-hidden="true">/</span><b>VALUE</b></a>
  <div class="nav-end">
  <ul>${navigation
    .map(({name, path: target}) => {
      const current = target === "/" ? path === "/index" || path === "/detail" : path === target;
      return `<li><a href="${target}"${current ? ` aria-current="page"` : ""}>${name}</a></li>`;
    })
    .join("")}</ul>
  <button class="theme-toggle" type="button" aria-label="Toggle dark mode" onclick="toggleTheme()">
    <svg class="icon-moon" viewBox="0 0 24 24" aria-hidden="true"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>
    <svg class="icon-sun" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>
  </button>
  </div>
</nav>
<script>function toggleTheme(){var root=document.documentElement;var isDark=root.dataset.theme?root.dataset.theme==="dark":matchMedia("(prefers-color-scheme: dark)").matches;var next=isDark?"light":"dark";root.dataset.theme=next;try{localStorage.setItem("theme",next)}catch(error){}}</script>`,
  footer: `Data: SGCarMart used-car snapshots, COE results via data.gov.sg. Educational use only — not financial advice.`
};
