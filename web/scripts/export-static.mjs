// A static, clickable copy of the running site, for the owners' private preview (an Artifact on claude.ai).
//
//   DATABASE_URL=... ALLOW_TEST_TIERS=1 npx next start -p 3100 &      # the site, on the data to show
//   node scripts/export-static.mjs <out_dir> [--as-of "16 Oct 2026"] [--lab <lab report .html>]
//
// It crawls every page a visitor can reach, then fetches each page again as a Plus and a Pro subscriber. Every page
// file holds all three versions: the free one as the page, the paid ones (where they differ) in inert <template>
// elements, and a bar at the top switches between them, and between three colour palettes for the owners to choose
// from. For each page it removes the app's scripts (the copy is plain HTML), links one shared stylesheet and script,
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

const SEEDS = ["/", "/cse", "/cse/shares", "/cse/dealings", "/bonds", "/bonds/zscores", "/bonds/execution", "/bonds/carry", "/learn",
               "/learn/glossary", "/learn/savings", "/plans", "/methods", "/about", "/feedback", "/email/cse", "/email/bonds"];
const TIERS = ["free", "plus", "pro"];
const TIER_NAMES = { free: "Free", plus: "Plus", pro: "Pro" };
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
  const res = await fetch(BASE + path, { headers: tier === "free" ? {} : { "x-test-tier": tier } });
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

// 1. Crawl as a free visitor, then fetch every page as Plus and Pro.
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
  v.plus = await get(path, "plus");
  v.pro = await get(path, "pro");
}

// 2. One shared stylesheet: the site's, without its self-hosted font faces (Google Fonts serves the same faces to
// the copy), plus the two alternative palettes and the preview bar.
const first = pages.get("/").free;
let css = "";
for (const m of first.matchAll(/<link rel="stylesheet" href="([^"]+\.css)"[^>]*>/g)) css += await (await fetch(BASE + m[1])).text();
css = css.replace(/@font-face\s*{[^}]*}/g, "");
css += `
/* Preview only: two alternative palettes for the owners to compare with the default (app/globals.css). */
:root[data-theme="harbour"] { --bg: #f4f6f8; --surface: #ffffff; --surface-2: #eef1f4; --border: #dde3e9; --border-strong: #c6cfd8;
  --text: #14212e; --muted: #586575; --accent: #0e5e6f; --accent-strong: #0a4654; --accent-soft: #e3eff1; --navy: #10222f;
  --gold: #9b7a2f; --up: #1d7a50; --up-soft: #e4f1ea; --down: #b2392d; --down-soft: #f7e6e3; --plus: #55508f; --pro: #8a6116;
  --warn-bg: #fbf3e1; --warn-text: #6e4b0f; color-scheme: light; }
:root[data-theme="evergreen"] { --bg: #f5f5f2; --surface: #ffffff; --surface-2: #efefea; --border: #deded6; --border-strong: #c9c9bf;
  --text: #1a1d1a; --muted: #5d625c; --accent: #23573f; --accent-strong: #183f2d; --accent-soft: #e6efe9; --navy: #17241d;
  --gold: #a3741c; --up: #23704a; --up-soft: #e5f0e9; --down: #ad3a2c; --down-soft: #f6e6e2; --plus: #5b4d86; --pro: #8a5a12;
  --warn-bg: #fbf3e1; --warn-text: #6e4b0f; color-scheme: light; }
.pv-bar { background: #14181d; color: #e8e6e1; font: 13px/1.4 Inter, system-ui, sans-serif; padding: 8px 16px; display: flex; gap: 8px 18px;
  flex-wrap: wrap; align-items: center; justify-content: center; }
.pv-bar strong { font-weight: 600; }
.pv-group { display: inline-flex; gap: 4px; align-items: center; flex-wrap: wrap; }
.pv-group > span { opacity: .75; margin-right: 2px; }
.pv-group button { font: inherit; color: #e8e6e1; background: transparent; border: 1px solid rgba(255,255,255,.3); border-radius: 999px;
  padding: 1px 10px; cursor: pointer; }
.pv-group button[aria-pressed="true"] { background: #e8e6e1; color: #14181d; font-weight: 600; }
.pv-group button .pv-same { opacity: .6; font-size: 11px; }
.pv-bar a { color: #e8e6e1; text-decoration: underline; }
/* The internal lab page. */
.lab-page .notice.warn b { font-weight: 600; }
.lab-page .mockup { border: 2px dashed var(--down); border-radius: var(--radius); padding: 8px 16px; margin: 16px 0; background: var(--surface); }
.lab-page .mock { color: var(--down); font-weight: 600; }
.lab-page .note { color: var(--muted); font-size: 0.85rem; }
.lab-page svg { width: 100%; max-width: 640px; font-size: 11px; }
.lab-page .axis { stroke: var(--muted); }
.lab-page .frontier { fill: none; stroke: var(--accent); stroke-width: 2; }
.lab-page circle { fill: var(--gold); }
.lab-page h2 { border-bottom: 1px solid var(--border); padding-bottom: 4px; }
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
    var p = { text: v("--text", "#1c2127"), muted: v("--muted", "#5c6370"), border: v("--border", "#e2ded4"), surface: v("--surface", "#ffffff"),
              series: [v("--accent", "#1d4f7a"), v("--gold", "#a06b16"), v("--plus", "#5a4a8a"), v("--down", "#b03a2e"), v("--up", "#1f7a4d")] };
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
  function wire() {
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
  function setTheme(theme) {
    if (theme === "ledger") document.documentElement.removeAttribute("data-theme"); else document.documentElement.setAttribute("data-theme", theme);
    document.querySelectorAll("[data-pv-theme]").forEach(function (b) { b.setAttribute("aria-pressed", String(b.dataset.pvTheme === theme)); });
    store.set("ziq-theme", theme);
    charts();
  }
  document.querySelectorAll("[data-pv-tier]").forEach(function (b) { b.addEventListener("click", function () { setTier(b.dataset.pvTier); }); });
  document.querySelectorAll("[data-pv-theme]").forEach(function (b) { b.addEventListener("click", function () { setTheme(b.dataset.pvTheme); }); });
  setTheme(store.get("ziq-theme") || "ledger");
  var saved = store.get("ziq-tier");
  if (saved && saved !== "free" && ${JSON.stringify(TIERS)}.indexOf(saved) >= 0) setTier(saved); else wire();
})();`;

// 4. Each page: links rewritten, scripts removed, the "behind the calendar" notices dropped (the preview's data
// stops on its as-of date by design, and the bar says so).
function rewriteBody(html) {
  let body = (html.match(/<body[^>]*>([\s\S]*)<\/body>/) ?? ["", html])[1];
  body = body
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/g, "")
    .replace(/<div class="notice warn">\d+ sessions? behind[\s\S]*?<\/div>/g, "")
    // the copy has no server behind it: its forms (feedback, the calculator) do nothing when sent
    .replace(/<form\b([^>]*?)action="[^"]*"/g, '<form$1action="#" onsubmit="return false"');
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
  const themes = [["ledger", "Ledger"], ["harbour", "Harbour"], ["evergreen", "Evergreen"]]
    .map(([k, n]) => `<button type="button" data-pv-theme="${k}" aria-pressed="${k === "ledger"}">${n}</button>`).join("");
  const lab = LAB ? `<a href="${fileName(LAB_PATH)}">Portfolio lab (internal)</a>` : "";
  return `<div class="pv-bar"><strong>Private preview of ZinvestIQ</strong><span>Real data${AS_OF ? ` to ${AS_OF}` : ""}; not the live site.</span>` +
    `<span class="pv-group"><span>View as</span>${tierButtons}</span><span class="pv-group"><span>Colours</span>${themes}</span>${lab}</div>`;
}

function page(path, title, freeBody, variants) {
  const groups = new Map(); // body -> the tiers that see it
  for (const t of TIERS) if (variants[t]) groups.set(variants[t], [...(groups.get(variants[t]) ?? []), t]);
  const templates = [...groups].map(([body, tiers]) => `<template data-tier="${tiers.join(" ")}">${body}</template>`).join("");
  const head = `<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">${title}` +
    `<link rel="stylesheet" href="${FONTS}"><link rel="stylesheet" href="style.css">`;
  const body = `${bar(path, variants)}<div id="ziq-root" data-tier="free">${freeBody}</div>${templates}` +
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
  const plus = rewriteBody(v.plus);
  const pro = rewriteBody(v.pro);
  // A paid version is stored only when it differs from the free page; Plus and Pro share one template when equal.
  const variants = {};
  if (comparable(plus) !== comparable(free)) variants.plus = plus;
  if (comparable(pro) !== comparable(free)) variants.pro = variants.plus && comparable(pro) === comparable(plus) ? variants.plus : pro;
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
    .replace(/<table class="([^"]*)">/g, '<div class="table-wrap"><table class="$1">').replace(/<\/table>/g, "</table></div>")
    .replace(/<h1>[\s\S]*?<\/h1>/, "");
  const head = `<header class="page-head"><p class="eyebrow">Internal research · not part of the site</p><h1>Portfolio lab</h1>` +
    `<p class="lead">The owner's research report on model portfolios (decision 0023). It stays off the site until the lawyer has given a view; ` +
    `the three mock-ups at the end show the ways it could be published, for that conversation.</p></header>`;
  const framed = aboutFree.replace(/(<main\b[^>]*>)[\s\S]*(<\/main>)/, `$1<div class="lab-page">${head}${content}</div>$2`);
  write(LAB_PATH, page(LAB_PATH, "<title>Portfolio lab (internal) · ZinvestIQ</title>", framed, {}));
}

writeFileSync(join(OUT, "style.css"), css);
writeFileSync(join(OUT, "preview.js"), SCRIPT);
writeFileSync(join(OUT, "manifest.json"), JSON.stringify(files, null, 1));
console.log(`${Object.keys(files).length} pages, ${variantCount} paid versions that differ from the free page, ${(bytes / 1e6).toFixed(1)} MB (+ style.css, preview.js)`);
