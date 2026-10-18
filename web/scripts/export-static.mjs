// A static, clickable copy of the running site, for the owner's private preview (an Artifact on claude.ai).
//
//   DATABASE_URL=... ALLOW_TEST_TIERS=1 npx next start -p 3100 &      # the site, on the data to show
//   node scripts/export-static.mjs <out_dir> [--as-of "16 Oct 2026"]
//
// It crawls every page a visitor can reach (free tier), and the bond and crypto pages again as a Pro subscriber, then for each
// page: removes the app's scripts (the copy is plain HTML), inlines the stylesheet, loads the heading font from
// Google Fonts, rewrites links to the copy's flat file names, draws charts from their data-chart attribute with
// ECharts from cdnjs, and adds a banner saying what this is. The Pro pages are for the owners' eyes only: the copy
// is private, never a public site (hard rule 5 governs the real site, where the server enforces tiers).
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { createHash } from "node:crypto";

const BASE = process.env.BASE ?? "http://127.0.0.1:3100";
const OUT = process.argv[2];
const AS_OF = process.argv.includes("--as-of") ? process.argv[process.argv.indexOf("--as-of") + 1] : "";
if (!OUT) throw new Error("usage: node scripts/export-static.mjs <out_dir> [--as-of <date text>]");
mkdirSync(OUT, { recursive: true });

const SEEDS = ["/", "/cse", "/cse/shares", "/bonds", "/bonds/zscores", "/bonds/execution", "/bonds/carry", "/crypto", "/learn", "/plans", "/methods", "/about"];
// the pages a Pro subscriber sees differently
const proPage = (path) => path === "/bonds" || path.startsWith("/bonds/") || path === "/crypto" || path.startsWith("/crypto/");
const ECHARTS = "https://cdnjs.cloudflare.com/ajax/libs/echarts/6.0.0/echarts.min.js";
const FONTS = "https://fonts.googleapis.com/css2?family=Manrope:wght@500..800&display=swap";

function fileName(path, tier) {
  if (path === "/" && tier === "free") return "index.html";
  const segments = (decodeURIComponent(path).replace(/^\//, "") || "home").split("/");
  const safe = segments.map((s) => s.replace(/[^A-Za-z0-9._-]+/g, "_"));
  // a segment that had to change (a synthetic bond id such as SYN:2031-01-15:12.000%9.000) gets a short hash, so
  // two different addresses can never share a file
  const tag = safe.every((s, i) => s === segments[i]) ? "" : "-" + createHash("sha1").update(path).digest("hex").slice(0, 6);
  return (tier === "pro" ? "pro--" : "") + safe.join("__") + tag + ".html";
}

async function get(path, tier) {
  const res = await fetch(BASE + path, { headers: tier === "pro" ? { "x-test-tier": "pro" } : {} });
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

// 1. Crawl.
const pages = new Map(); // path -> free html
const queue = [...SEEDS];
while (queue.length) {
  const path = queue.shift();
  if (pages.has(path)) continue;
  const html = await get(path, "free");
  pages.set(path, html);
  for (const p of links(html)) if (!pages.has(p) && !queue.includes(p)) queue.push(p);
}
const proPages = new Map();
for (const path of pages.keys()) if (proPage(path)) proPages.set(path, await get(path, "pro"));

// 2. The stylesheet, once, without the self-hosted font faces (Google Fonts serves the same face to the copy).
const cssHref = [...pages.get("/").matchAll(/<link rel="stylesheet" href="([^"]+\.css)"[^>]*>/g)].map((m) => m[1]);
let css = "";
for (const href of cssHref) css += await (await fetch(BASE + href)).text();
css = css.replace(/@font-face\s*{[^}]*Manrope[^}]*}/g, "");

const CHART_SCRIPT = `
(function () {
  function v(n, f) { var x = getComputedStyle(document.documentElement).getPropertyValue(n).replace(/^\\s+|\\s+$/g, ""); return x || f; }
  function axis(a, p) {
    if (Array.isArray(a)) return a.map(function (x) { return axis(x, p); });
    var o = a || {};
    return Object.assign({}, o, {
      axisLine: Object.assign({ lineStyle: { color: p.border } }, o.axisLine), axisTick: Object.assign({ lineStyle: { color: p.border } }, o.axisTick),
      axisLabel: Object.assign({ color: p.muted }, o.axisLabel), nameTextStyle: Object.assign({ color: p.muted }, o.nameTextStyle),
      splitLine: Object.assign({ lineStyle: { color: p.border, opacity: 0.7 } }, o.splitLine) });
  }
  function draw() {
    var p = { text: v("--text", "#0f1b2d"), muted: v("--muted", "#5a6a80"), border: v("--border", "#dfe5ee"), surface: v("--surface", "#ffffff"),
              series: [v("--accent", "#0f7c86"), v("--gold", "#e09f3e"), v("--plus", "#6247c9"), v("--down", "#c2412d"), v("--up", "#12805c")] };
    document.querySelectorAll("[data-chart]").forEach(function (el) {
      var o = JSON.parse(el.getAttribute("data-chart"));
      var t = Object.assign({}, o, { color: p.series, textStyle: { color: p.text, fontFamily: "inherit" }, xAxis: axis(o.xAxis, p), yAxis: axis(o.yAxis, p) });
      if (o.legend) t.legend = Object.assign({}, o.legend, { textStyle: { color: p.muted }, pageTextStyle: { color: p.muted } });
      if (o.tooltip) t.tooltip = Object.assign({ backgroundColor: p.surface, borderColor: p.border, textStyle: { color: p.text } }, o.tooltip);
      var c = echarts.getInstanceByDom(el) || echarts.init(el);
      c.setOption(t, true);
      window.addEventListener("resize", function () { c.resize(); });
    });
  }
  if (window.echarts) draw();
})();`;

function banner(path, tier) {
  const other = tier === "free" ? (proPages.has(path) ? fileName(path, "pro") : null) : fileName(path, "free");
  const style = "background:#0b2545;color:#e6edf7;font:13px/1.4 system-ui,sans-serif;padding:8px 16px;display:flex;gap:12px;flex-wrap:wrap;align-items:center;justify-content:center";
  const pill = (label, on) => `<span style="padding:2px 10px;border-radius:999px;border:1px solid #6fd8d3;${on ? "background:#6fd8d3;color:#0b2545;font-weight:700" : ""}">${label}</span>`;
  const view = tier === "free"
    ? `${pill("Free", true)} ${other ? `<a href="${other}" style="color:#e6edf7">${pill("Pro", false)}</a>` : `<span style="opacity:.6">${pill("Pro", false)}</span>`}`
    : `<a href="${other}" style="color:#e6edf7">${pill("Free", false)}</a> ${pill("Pro", true)}`;
  return `<div style="${style}"><strong>Preview copy of ZinvestIQ</strong><span>Real data${AS_OF ? ` to ${AS_OF}` : ""}; not yet the live site.</span><span>Viewing as:</span>${view}</div>`;
}

function rewrite(html, path, tier) {
  let out = html
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/g, "")
    .replace(/<link\b[^>]*rel="(?:preload|modulepreload|icon|apple-touch-icon|manifest)"[^>]*>/g, "")
    .replace(/<link rel="stylesheet" href="[^"]+\.css"[^>]*>/g, "")
    .replace(/<meta name="next-size-adjust"[^>]*>/g, "");
  out = out.replace(/href="(\/[^"#?]*)((?:\?[^"#]*)?)((?:#[^"]*)?)"/g, (m, p, _q, hash) => {
    if (p.startsWith("/api")) return 'href="#"';
    const target = p.replace(/\/$/, "") || "/";
    if (!pages.has(target)) return 'href="#"';
    const t = tier === "pro" && proPages.has(target) ? "pro" : "free";
    return `href="${fileName(target, t)}${hash}"`;
  });
  const head = `<link rel="stylesheet" href="${FONTS}"><style>${css}</style>`;
  const tail = `<script src="${ECHARTS}"></script><script>${CHART_SCRIPT}</script>`;
  out = out.replace("</head>", `${head}</head>`).replace(/<body([^>]*)>/, (m) => `${m}${banner(path, tier)}`).replace("</body>", `${tail}</body>`);
  return out;
}

// The main page is wrapped in a document skeleton when it is published, so it carries only its content.
function bodyOnly(html) {
  const title = (html.match(/<title>[\s\S]*?<\/title>/) ?? [""])[0];
  const headExtra = (html.match(/<head>([\s\S]*?)<\/head>/) ?? ["", ""])[1].match(/<link rel="stylesheet"[^>]*>|<style>[\s\S]*?<\/style>/g) ?? [];
  const body = (html.match(/<body[^>]*>([\s\S]*)<\/body>/) ?? ["", html])[1];
  return `${title}\n${headExtra.join("\n")}\n${body}`;
}

let bytes = 0;
const files = {};
for (const [tier, map] of [["free", pages], ["pro", proPages]]) {
  for (const [path, html] of map) {
    const name = fileName(path, tier);
    const page = rewrite(html, path, tier);
    const body = name === "index.html" ? bodyOnly(page) : page;
    writeFileSync(join(OUT, name), body);
    files[name] = path + (tier === "pro" ? " (pro)" : "");
    bytes += body.length;
  }
}
writeFileSync(join(OUT, "manifest.json"), JSON.stringify(files, null, 1));
console.log(`${Object.keys(files).length} pages (${pages.size} free, ${proPages.size} pro), ${(bytes / 1e6).toFixed(1)} MB`);
