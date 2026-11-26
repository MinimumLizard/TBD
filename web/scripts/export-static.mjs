// A static, clickable copy of the running site, for the owners' private preview (an Artifact on claude.ai).
//
//   DATABASE_URL=... ALLOW_TEST_TIERS=1 npx next start -p 3100 &      # the site, on the data to show
//   node scripts/export-static.mjs <out_dir> [--as-of "16 Oct 2026"] [--lab <lab report .html>]
//
// It crawls every page a visitor can reach, then fetches each page again as a Pro and a Plus subscriber. Every page
// file holds all three versions: the free one as the page, the paid ones (where they differ) in inert <template>
// elements, and a bar at the top switches between them. For each page it removes the app's scripts (the copy is plain HTML), links one shared stylesheet and script,
// rewrites links to the copy's flat file names, and draws charts from their data-chart attribute with ECharts from
// cdnjs. With --lab, the owner's internal portfolio-lab report (python -m data_platform.jobs.lab_report) is added as
// one page, marked internal. The copy is for the owners' eyes only, never a public site: it carries every tier's
// data in every page (hard rule 5 governs the real site, where the server enforces tiers), and the lab is
// unpublished research (decision 0023).
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { createHash } from "node:crypto";

const BASE = process.env.BASE ?? "http://127.0.0.1:3100";
const OUT = process.argv[2];
const arg = (name) => (process.argv.includes(name) ? process.argv[process.argv.indexOf(name) + 1] : undefined);
const AS_OF = arg("--as-of") ?? "";
const LAB = arg("--lab");
if (!OUT) throw new Error("usage: node scripts/export-static.mjs <out_dir> [--as-of <date text>] [--lab <file>]");
mkdirSync(OUT, { recursive: true });

const SEEDS = ["/", "/start", "/markets", "/privacy", "/signup/thanks", "/search", "/cse", "/cse/shares", "/cse/shares/compare", "/cse/dealings", "/bonds", "/bonds/zscores", "/bonds/execution", "/bonds/carry", "/learn",
               "/learn/glossary", "/learn/savings", "/plans", "/methods", "/about", "/feedback", "/email/cse", "/email/bonds"];
const TIERS = ["free", "pro", "plus"]; // a ladder (decision 0027)
const TIER_NAMES = { free: "Free", pro: "Pro", plus: "Plus" };
const ECHARTS = "https://cdnjs.cloudflare.com/ajax/libs/echarts/6.0.0/echarts.min.js";
const FONTS = "https://fonts.googleapis.com/css2?family=Inter:wght@400..700&family=Source+Serif+4:opsz,wght@8..60,500..700&display=swap";
const LAB_PATH = "/preview/lab";

function fileName(path) {
  if (path === "/") return "index.html";
  if (path === LAB_PATH) return "lab.html";
  const segments = decodeURIComponent(path).replace(/^\//, "").split("/");
  const safe = segments.map((s) => s.replace(/[^A-Za-z0-9._-]+/g, "_"));
  // a segment that had to change (a synthetic bond id such as SYN:2031-01-15:12.000%9.000) gets a short hash, so
  // two different addresses can never share a file
  const tag = safe.every((s, i) => s === segments[i]) ? "" : "-" + createHash("sha1").update(path).digest("hex").slice(0, 6);
  return safe.join("__") + tag + ".html";
}

async function get(path, tier) {
  // the copy's sign-up form opens the thank-you page as it reads after a successful sign-up
  const res = await fetch(BASE + path + (path === "/signup/thanks" ? "?r=ok" : ""), { headers: tier === "free" ? {} : { "x-test-tier": tier } });
  if (!res.ok) throw new Error(`${path} as ${tier}: HTTP ${res.status}`);
  return res.text();
}

function links(html) {
  const out = new Set();
  for (const m of html.matchAll(/href="(\/[^"#?]*)(?:[?#][^"]*)?"/g)) {
    const p = m[1];
    if (p.startsWith("/_next") || p.startsWith("/api")) continue;
    out.add(p.replace(/\/$/, "") || "/");
  }
  return out;
}

// 1. Crawl as a free visitor, then fetch every page as Pro and Plus.
const pages = new Map(); // path -> { free, plus, pro } raw html
const queue = [...SEEDS];
while (queue.length) {
  const path = queue.shift();
  if (pages.has(path)) continue;
  const html = await get(path, "free");
  pages.set(path, { free: html });
  for (const p of links(html)) if (!pages.has(p) && !queue.includes(p)) queue.push(p);
}
for (const [path, v] of pages) {
  v.pro = await get(path, "pro");
  v.plus = await get(path, "plus");
}

// 2. One shared stylesheet: the site's, without its self-hosted font faces (Google Fonts serves the same faces to
// the copy), plus the preview bar and the lab page's styles.
const first = pages.get("/").free;
let css = "";
for (const m of first.matchAll(/<link rel="stylesheet" href="([^"]+\.css)"[^>]*>/g)) css += await (await fetch(BASE + m[1])).text();
css = css.replace(/@font-face\s*{[^}]*}/g, "");
css += `
.pv-bar { background: #0c1a33; color: #e6ebf4; font: 13px/1.4 Inter, system-ui, sans-serif; padding: 8px 16px; display: flex; gap: 8px 18px;
  flex-wrap: wrap; align-items: center; justify-content: center; }
.pv-bar strong { font-weight: 600; }
.pv-group { display: inline-flex; gap: 4px; align-items: center; flex-wrap: wrap; }
.pv-group > span { opacity: .75; margin-right: 2px; }
.pv-group button { font: inherit; color: #e6ebf4; background: transparent; border: 1px solid rgba(255,255,255,.3); border-radius: 999px;
  padding: 1px 10px; cursor: pointer; }
.pv-group button[aria-pressed="true"] { background: #e6ebf4; color: #0c1a33; font-weight: 600; }
.pv-group button .pv-same { opacity: .6; font-size: 11px; }
.pv-bar a { color: #e6ebf4; text-decoration: underline; }
/* The internal lab page. Its charts carry their own styles (data_platform/jobs/lab_charts.py), drawn in the site's
   tokens, so they follow the light and dark themes. */
.lab-page .notice.warn b { font-weight: 600; }
.lab-page .mockup { border: 2px dashed var(--down); border-radius: var(--radius); padding: 8px 16px; margin: 16px 0; background: var(--surface); }
.lab-page .mock { color: var(--down); font-weight: 600; }
.lab-page .note { color: var(--muted); font-size: 0.85rem; }
.lab-page .lab-intro .lead { max-width: 70ch; }
.lab-page .lab-intro ul { padding-left: 1.2rem; max-width: 70ch; }
.lab-page .lab-intro li { margin-bottom: 4px; }
.lab-page .lab-intro ul.three { list-style: none; padding: 0; max-width: none; display: grid; gap: var(--s3); grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); margin: var(--s4) 0 var(--s5); }
.lab-page .lab-intro ul.three li { margin: 0; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: var(--s4); font-size: 0.92rem; color: var(--muted); }
.lab-page .lab-intro ul.three li b { display: block; color: var(--text); font-family: var(--display); font-size: 1.02rem; margin-bottom: 2px; }
.lab-page h2.deeper { margin-top: var(--s7); }
.lab-page .donuts { display: grid; grid-template-columns: 1fr; gap: var(--s2) var(--s6); margin: var(--s4) 0; }
@media (min-width: 900px) { .lab-page .donuts { grid-template-columns: 1fr 1fr; } }
.lab-page .donuts h3 { margin: 0 0 var(--s1); }
.lab-page details.more { margin: var(--s4) 0; border-top: 1px solid var(--border); padding-top: var(--s3); }
.lab-page details.more > summary { cursor: pointer; color: var(--accent); font-weight: 600; }
.lab-page ol.steps li { margin-bottom: 6px; }
.lab-page td { white-space: normal; min-width: 6rem; vertical-align: top; }
.lab-page .table-wrap .table-wrap { border: 0; }
`;

// 3. One shared script: tier and palette switching, the sections' and menus' behaviour (as components/PageScripts.tsx
// does on the real site), and the charts.
const SCRIPT = `
(function () {
  var store = { get: function (k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
                set: function (k, v) { try { localStorage.setItem(k, v); } catch (e) {} } };
  function v(n, f) { var x = getComputedStyle(document.documentElement).getPropertyValue(n).replace(/^\\s+|\\s+$/g, ""); return x || f; }
  function axis(a, p) {
    if (Array.isArray(a)) return a.map(function (x) { return axis(x, p); });
    var o = a || {};
    return Object.assign({}, o, {
      axisLine: Object.assign({ lineStyle: { color: p.border } }, o.axisLine), axisTick: Object.assign({ lineStyle: { color: p.border } }, o.axisTick),
      axisLabel: Object.assign({ color: p.muted }, o.axisLabel), nameTextStyle: Object.assign({ color: p.muted }, o.nameTextStyle),
      splitLine: Object.assign({ lineStyle: { color: p.border, opacity: 0.7 } }, o.splitLine) });
  }
  function charts() {
    if (!window.echarts) return;
    var p = { text: v("--text", "#111a2c"), muted: v("--muted", "#55617a"), border: v("--border", "#dce2ea"), surface: v("--surface", "#ffffff"),
              series: [v("--series-1", "#1b4f9c"), v("--series-2", "#c98500"), v("--series-3", "#00a39a"), v("--series-4", "#6250d6"), v("--series-5", "#c2477e")] };
    document.querySelectorAll("#ziq-root [data-chart]").forEach(function (el) {
      if (!el.offsetParent && el.closest("details:not([open])")) { el.dataset.pending = "1"; return; }
      var o = JSON.parse(el.getAttribute("data-chart"));
      var t = Object.assign({}, o, { color: p.series, textStyle: { color: p.text, fontFamily: "inherit" }, xAxis: axis(o.xAxis, p), yAxis: axis(o.yAxis, p) });
      if (o.legend) t.legend = Object.assign({}, o.legend, { textStyle: { color: p.muted }, pageTextStyle: { color: p.muted } });
      if (o.tooltip) t.tooltip = Object.assign({ backgroundColor: p.surface, borderColor: p.border, textStyle: { color: p.text } }, o.tooltip);
      var c = echarts.getInstanceByDom(el) || echarts.init(el);
      c.setOption(t, true);
      c.resize();
      delete el.dataset.pending;
    });
  }
  window.addEventListener("resize", function () { document.querySelectorAll("#ziq-root [data-chart]").forEach(function (el) { var c = window.echarts && echarts.getInstanceByDom(el); if (c) c.resize(); }); });
  function openTarget() {
    var id = decodeURIComponent(location.hash.slice(1)); if (!id) return;
    var el = document.getElementById(id);
    while (el) { if (el.tagName === "DETAILS") el.open = true; el = el.parentElement; }
  }
  function norm(t) { return (t || "").normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z0-9.%]+/g, " ").replace(/^ +| +$/g, ""); }
  function wireFilter(form) {
    var scope = document.getElementById(form.dataset.filter), input = form.querySelector("input[name=q]");
    if (!scope || !input) return;
    var selects = Array.prototype.slice.call(form.querySelectorAll("select"));
    var count = form.querySelector("[data-filter-count]");
    var go = form.querySelector("[data-filter-go]"); if (go) go.hidden = true;
    var items = Array.prototype.slice.call(scope.querySelectorAll("[data-search]"));
    var groups = Array.prototype.slice.call(scope.querySelectorAll("[data-group]"));
    groups.forEach(function (g) { if (g.tagName === "DETAILS" && g.dataset.openInitial === undefined) g.dataset.openInitial = String(g.open); });
    var params = new URLSearchParams(location.search);
    if (params.get("q")) input.value = params.get("q");
    selects.forEach(function (sel) { if (params.get(sel.name)) sel.value = params.get(sel.name); });
    function apply() {
      var words = norm(input.value).split(" ").filter(Boolean), shown = 0;
      items.forEach(function (el) {
        var t = el.dataset.search || "";
        var ok = words.every(function (w) { return t.indexOf(w) >= 0; }) && selects.every(function (sel) { return !sel.value || el.dataset[sel.name] === sel.value; });
        el.hidden = !ok; if (ok) shown++;
      });
      var active = words.length > 0 || selects.some(function (sel) { return sel.value; });
      if (scope.hasAttribute("data-idle-list")) { if (active) scope.removeAttribute("data-idle"); else scope.setAttribute("data-idle", ""); }
      groups.forEach(function (g) {
        var any = g.querySelector("[data-search]:not([hidden])") !== null;
        g.hidden = !any;
        if (g.tagName === "DETAILS") g.open = active ? any : g.dataset.openInitial === "true";
      });
      if (count && count.dataset.template) count.textContent = count.dataset.template.replace("{shown}", shown).replace("{total}", items.length);
    }
    form.addEventListener("submit", function (e) { e.preventDefault(); apply(); });
    input.addEventListener("input", apply);
    selects.forEach(function (sel) { sel.addEventListener("change", apply); });
    apply();
  }
  // The real site remembers a visitor's starting answers in a cookie set by its server (web/proxy.ts) and opens
  // the front door on their own home page. The copy has no server, so it does the same from the browser's storage.
  function rememberPath() {
    try {
      var own = document.querySelector("#ziq-root a[data-remember-path]");
      if (own) store.set("ziq-path", own.getAttribute("href").replace(/^start__/, "home__"));
      document.querySelectorAll("#ziq-root a[data-skip-start]").forEach(function (a) {
        a.addEventListener("click", function () { store.set("ziq-path", a.getAttribute("href")); });
      });
    } catch (e) {}
  }
  // Questions 3 and 4: the real site keeps the answers in its cookie and shows the matching facts from the server.
  // The copy keeps them in the browser and shows the matching variant (every variant is in the page).
  function personal() {
    try {
      var saved = (store.get("ziq-more") || "na.na").split(".");
      [["amount", saved[0]], ["horizon", saved[1]]].forEach(function (kv) {
        var els = document.querySelectorAll("#ziq-root [data-" + kv[0] + "]");
        els.forEach(function (el) { el.hidden = el.getAttribute("data-" + kv[0]) !== (kv[1] && kv[1] !== "na" ? kv[1] : "none"); });
      });
      document.querySelectorAll("#ziq-root form[data-start-more]").forEach(function (f) {
        f.addEventListener("submit", function (e) {
          e.preventDefault();
          var pick = function (n) { var c = f.querySelector('input[name="' + n + '"]:checked'); return c && c.value ? c.value : "na"; };
          store.set("ziq-more", pick("amount") + "." + pick("horizon"));
          location.href = f.querySelector("a[data-start-next]").getAttribute("href");
        });
      });
    } catch (e) {}
  }
  function wire() {
    rememberPath();
    personal();
    document.querySelectorAll("#ziq-root form[data-filter]").forEach(wireFilter);
    var sections = function () { return Array.prototype.slice.call(document.querySelectorAll("#ziq-root details.section")); };
    document.querySelectorAll("#ziq-root button[data-toggle-all]").forEach(function (b) {
      var label = function () { b.textContent = sections().every(function (d) { return d.open; }) ? b.dataset.close : b.dataset.open; };
      b.hidden = false; label();
      b.addEventListener("click", function () { var open = !sections().every(function (d) { return d.open; }); sections().forEach(function (d) { d.open = open; }); label(); });
    });
    document.querySelectorAll("#ziq-root details.section").forEach(function (d) {
      d.addEventListener("toggle", function () { if (d.open && d.querySelector("[data-pending]")) charts(); });
    });
    var menus = function () { return Array.prototype.slice.call(document.querySelectorAll("#ziq-root header.site details")); };
    menus().forEach(function (m) { m.addEventListener("toggle", function () { if (m.open) menus().forEach(function (o) { if (o !== m && !o.contains(m)) o.open = false; }); }); });
    openTarget();
    charts();
  }
  document.addEventListener("click", function (e) {
    document.querySelectorAll("#ziq-root header.site details[open]").forEach(function (m) { if (!m.contains(e.target)) m.open = false; });
  });
  window.addEventListener("hashchange", openTarget);

  var root = document.getElementById("ziq-root");
  var home = store.get("ziq-path");
  if (root.hasAttribute("data-front-door") && home && /^[A-Za-z0-9_.-]+\\.html$/.test(home)) { location.replace(home); return; }
  document.querySelectorAll("[data-pv-reset]").forEach(function (b) {
    b.addEventListener("click", function () { try { localStorage.removeItem("ziq-path"); localStorage.removeItem("ziq-more"); } catch (e) {} location.href = "index.html"; });
  });
  var original = root.innerHTML;
  function setTier(tier) {
    var tpl = document.querySelector('template[data-tier~="' + tier + '"]');
    root.innerHTML = tpl ? tpl.innerHTML : original;
    root.dataset.tier = tier;
    var badge = root.querySelector(".tier-badge");
    if (badge) badge.textContent = badge.textContent.replace(/(Free|Plus|Pro)\\s*$/, ${JSON.stringify(TIER_NAMES)}[tier]);
    document.querySelectorAll("[data-pv-tier]").forEach(function (b) { b.setAttribute("aria-pressed", String(b.dataset.pvTier === tier)); });
    store.set("ziq-tier", tier);
    wire();
  }
  document.querySelectorAll("[data-pv-tier]").forEach(function (b) { b.addEventListener("click", function () { setTier(b.dataset.pvTier); }); });
  var saved = store.get("ziq-tier");
  if (saved && saved !== "free" && ${JSON.stringify(TIERS)}.indexOf(saved) >= 0) setTier(saved); else wire();
})();`;

// 4. Each page: links rewritten, scripts removed, the "behind the calendar" notices dropped (the preview's data
// stops on its as-of date by design, and the bar says so).
function rewriteBody(html) {
  let body = (html.match(/<body[^>]*>([\s\S]*)<\/body>/) ?? ["", html])[1];
  body = body
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/g, "")
    .replace(/<span class="behind">[\s\S]*?<\/span>/g, "")
    // the copy has no server behind it: the site's search box opens the copy's search page (which filters itself);
    // other forms (feedback, the calculator, list filters) are not sent anywhere
    .replace(/<form\b([^>]*?)action="([^"]*)"/g, (m, attrs, action) =>
      action === "/search" ? `<form${attrs}action="${fileName("/search")}"`
        // nothing typed into the copy is sent or kept: the sign-up form only opens the thank-you page
        : action === "/api/signup" ? `<form${attrs}action="#" onsubmit="location.href='${fileName("/signup/thanks")}';return false"`
        : `<form${attrs}action="#" onsubmit="return false"`);
  return body.replace(/href="(\/[^"#?]*)((?:\?[^"#]*)?)((?:#[^"]*)?)"/g, (m, p, _q, hash) => {
    if (p.startsWith("/api")) return 'href="#"';
    const target = p.replace(/\/$/, "") || "/";
    if (!pages.has(target) && target !== LAB_PATH) return 'href="#"';
    return `href="${fileName(target)}${hash}"`;
  });
}
// two versions are the same page when they differ only in the "Access: <tier>" badge
const comparable = (body) => body.replace(/<a class="tier-badge"[^>]*>[\s\S]*?<\/a>/, "");

function bar(path, variants) {
  const tierButtons = TIERS.map((tier) => {
    const same = tier !== "free" && !variants[tier];
    return `<button type="button" data-pv-tier="${tier}" aria-pressed="${tier === "free"}"${same ? ' title="The same as Free on this page"' : ""}>${TIER_NAMES[tier]}${same ? ' <span class="pv-same">=</span>' : ""}</button>`;
  }).join("");
  const lab = LAB ? `<a href="${fileName(LAB_PATH)}">Lab: full workings</a>` : "";
  return `<div class="pv-bar"><strong>Preview of ZinvestIQ</strong><span>Real data${AS_OF ? ` to ${AS_OF}` : ""}; not the live site.</span>` +
    `<span class="pv-group"><span>View as</span>${tierButtons}</span>` +
    `<span class="pv-group"><button type="button" data-pv-reset title="Forget the starting answers and open the first page again">First visit</button></span>${lab}</div>`;
}

function page(path, title, freeBody, variants) {
  const groups = new Map(); // body -> the tiers that see it
  for (const t of TIERS) if (variants[t]) groups.set(variants[t], [...(groups.get(variants[t]) ?? []), t]);
  const templates = [...groups].map(([body, tiers]) => `<template data-tier="${tiers.join(" ")}">${body}</template>`).join("");
  const head = `<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">${title}` +
    `<meta name="robots" content="noindex, nofollow"><link rel="stylesheet" href="${FONTS}"><link rel="stylesheet" href="style.css">`;
  const body = `${bar(path, variants)}<div id="ziq-root" data-tier="free"${path === "/" ? " data-front-door" : ""}>${freeBody}</div>${templates}` +
    `<script src="${ECHARTS}"></script><script src="preview.js"></script>`;
  // the main page is wrapped in a document skeleton when it is published, so it carries only its content
  return path === "/" ? `${head}\n${body}` : `<!doctype html><html lang="en"><head>${head}</head><body>${body}</body></html>`;
}

let bytes = 0;
const files = {};
let variantCount = 0;
function write(path, html) {
  const name = fileName(path);
  writeFileSync(join(OUT, name), html);
  files[name] = path;
  bytes += html.length;
}
let aboutFree = null;
for (const [path, v] of pages) {
  const title = (v.free.match(/<title>[\s\S]*?<\/title>/) ?? [""])[0];
  const free = rewriteBody(v.free);
  const pro = rewriteBody(v.pro);
  const plus = rewriteBody(v.plus);
  // A paid version is stored only when it differs from the free page; Pro and Plus share one template when equal.
  const variants = {};
  if (comparable(pro) !== comparable(free)) variants.pro = pro;
  if (comparable(plus) !== comparable(free)) variants.plus = variants.pro && comparable(plus) === comparable(pro) ? variants.pro : plus;
  variantCount += new Set(Object.values(variants)).size;
  if (path === "/about") aboutFree = free;
  write(path, page(path, title, free, variants));
}

// 5. The internal lab: the owner's report, inside the site's own layout (the About page's frame).
if (LAB && aboutFree) {
  const report = readFileSync(LAB, "utf8");
  let content = (report.match(/<body[^>]*>([\s\S]*)<\/body>/) ?? ["", report])[1];
  content = content
    .replace(/<p class="warn">/g, '<p class="notice warn">')
    .replace(/<div class="table-wrap">/g, "").replace(/<\/table><\/div>/g, "</table>")
    .replace(/<table class="([^"]*)">/g, '<div class="table-wrap"><table class="$1">').replace(/<\/table>/g, "</table></div>")
    .replace(/<h1>[\s\S]*?<\/h1>/, "");
  // the owner's report opens with an internal-use warning; the preview frames the page as the education piece it is
  content = content.replace(/<p class="notice warn">[\s\S]*?<\/p>/, "");
  // the report opens with its own plain-language introduction (data_platform/jobs/lab_backtest_report.py)
  const head = `<header class="page-head"><p class="eyebrow">Portfolio lab · full workings (owners only)</p>` +
    `<h1>How a rules-based portfolio is built</h1>` +
    `<div class="notice warn">For the owners: the complete report behind the Pro lab page (decision 0027), with the ` +
    `evidence, the comparisons and the specialist workings. It is not a page of the site.</div></header>`;
  const framed = aboutFree.replace(/(<main\b[^>]*>)[\s\S]*(<\/main>)/, `$1<div class="lab-page">${head}${content}</div>$2`);
  write(LAB_PATH, page(LAB_PATH, "<title>Portfolio lab · ZinvestIQ</title>", framed, {}));
}

writeFileSync(join(OUT, "style.css"), css);
writeFileSync(join(OUT, "preview.js"), SCRIPT);
writeFileSync(join(OUT, "manifest.json"), JSON.stringify(files, null, 1));
console.log(`${Object.keys(files).length} pages, ${variantCount} paid versions that differ from the free page, ${(bytes / 1e6).toFixed(1)} MB (+ style.css, preview.js)`);
