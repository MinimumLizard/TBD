"use client";

// The little behaviour the collapsible sections and menus need; every page works without it.
// - A link to a section (#id) opens that section, and any closed section around the target.
// - The "open all / close all" button on long pages.
// - Opening one menu closes the others; a click elsewhere closes them all.
// - Lists with a filter bar (components/FilterBar.tsx) filter as the visitor types (lib/filter.ts has the rule).
// The static preview copy carries the same behaviour in scripts/export-static.mjs (it has no React).
import { usePathname } from "next/navigation";
import { useEffect } from "react";

import { matchesQuery } from "@/lib/filter";

function openTarget() {
  const id = decodeURIComponent(window.location.hash.slice(1));
  if (!id) return;
  let el: HTMLElement | null = document.getElementById(id);
  while (el) {
    if (el instanceof HTMLDetailsElement) el.open = true;
    el = el.parentElement;
  }
}

function wireFilter(form: HTMLFormElement): () => void {
  const scope = document.getElementById(form.dataset.filter ?? "");
  const input = form.querySelector<HTMLInputElement>("input[name=q]");
  if (!scope || !input) return () => {};
  const selects = Array.from(form.querySelectorAll<HTMLSelectElement>("select"));
  const count = form.querySelector<HTMLElement>("[data-filter-count]");
  form.querySelector<HTMLElement>("[data-filter-go]")?.setAttribute("hidden", "");
  const items = Array.from(scope.querySelectorAll<HTMLElement>("[data-search]"));
  const groups = Array.from(scope.querySelectorAll<HTMLElement>("[data-group]"));
  for (const g of groups) if (g instanceof HTMLDetailsElement && g.dataset.openInitial === undefined) g.dataset.openInitial = String(g.open);
  const apply = () => {
    let shown = 0;
    for (const el of items) {
      const ok = matchesQuery(el.dataset.search ?? "", input.value) && selects.every((s) => !s.value || el.dataset[s.name] === s.value);
      el.hidden = !ok;
      if (ok) shown++;
    }
    const active = input.value.replace(/\s+/g, "") !== "" || selects.some((s) => s.value);
    scope.toggleAttribute("data-idle", !active && scope.hasAttribute("data-idle-list"));
    for (const g of groups) {
      const any = g.querySelector("[data-search]:not([hidden])") !== null;
      g.hidden = !any;
      if (g instanceof HTMLDetailsElement) g.open = active ? any : g.dataset.openInitial === "true";
    }
    if (count?.dataset.template) count.textContent = count.dataset.template.replace("{shown}", String(shown)).replace("{total}", String(items.length));
    const url = new URL(window.location.href); // keep the address in step, so a filtered list can be shared
    for (const [name, value] of [["q", input.value], ...selects.map((s) => [s.name, s.value])]) {
      if (value) url.searchParams.set(name, value); else url.searchParams.delete(name);
    }
    window.history.replaceState(window.history.state, "", url);
  };
  const onSubmit = (e: Event) => { e.preventDefault(); apply(); };
  form.addEventListener("submit", onSubmit);
  input.addEventListener("input", apply);
  selects.forEach((s) => s.addEventListener("change", apply));
  return () => {
    form.removeEventListener("submit", onSubmit);
    input.removeEventListener("input", apply);
    selects.forEach((s) => s.removeEventListener("change", apply));
  };
}

// Starting paths (lib/paths.ts): a path page names itself in a hidden link; the home page offers to continue it. Only
// this site's own /start/<type>/<answer> addresses are kept, and the label is shown as text, never as markup.
const PATH_KEY = "ziq-path";
function rememberPath() {
  try {
    const own = document.querySelector<HTMLAnchorElement>("a[data-remember-path]");
    if (own) localStorage.setItem(PATH_KEY, JSON.stringify({ href: own.getAttribute("href"), label: own.textContent }));
    const slot = document.querySelector<HTMLElement>("[data-continue-path]");
    const saved = slot ? JSON.parse(localStorage.getItem(PATH_KEY) ?? "null") : null;
    if (!slot || !saved || typeof saved.href !== "string" || !/^\/start\/[a-z]+\/[a-z]+$/.test(saved.href)) return;
    const link = document.createElement("a");
    link.href = saved.href;
    link.textContent = (slot.dataset.template ?? "").replace("{label}", String(saved.label ?? ""));
    slot.replaceChildren(link);
    slot.hidden = false;
  } catch {
    // storage blocked or unreadable: the home page simply offers no shortcut
  }
}

export default function PageScripts() {
  const pathname = usePathname(); // the layout stays mounted across pages: wire each new page again
  useEffect(() => {
    openTarget();
    rememberPath();
    window.addEventListener("hashchange", openTarget);

    const toggles = Array.from(document.querySelectorAll<HTMLButtonElement>("button[data-toggle-all]"));
    const sections = () => Array.from(document.querySelectorAll<HTMLDetailsElement>("details.section"));
    const label = (b: HTMLButtonElement) => {
      b.textContent = sections().every((d) => d.open) ? b.dataset.close ?? "" : b.dataset.open ?? "";
    };
    const onToggle = (e: Event) => {
      const b = e.currentTarget as HTMLButtonElement;
      const open = !sections().every((d) => d.open);
      sections().forEach((d) => { d.open = open; });
      label(b);
    };
    for (const b of toggles) {
      b.hidden = false;
      label(b);
      b.addEventListener("click", onToggle);
    }

    const menus = () => Array.from(document.querySelectorAll<HTMLDetailsElement>("header.site details"));
    const onMenu = (e: Event) => {
      const d = e.target as HTMLDetailsElement;
      if (d.open) menus().forEach((m) => { if (m !== d && !m.contains(d)) m.open = false; });
    };
    const onClick = (e: MouseEvent) => {
      const followed = (e.target as Element).closest?.("a"); // a menu link was followed: the page changes, close it
      menus().forEach((m) => { if (m.open && (followed || !m.contains(e.target as Node))) m.open = false; });
    };
    menus().forEach((m) => m.addEventListener("toggle", onMenu));
    document.addEventListener("click", onClick);
    const filters = Array.from(document.querySelectorAll<HTMLFormElement>("form[data-filter]")).map(wireFilter);
    return () => {
      filters.forEach((off) => off());
      window.removeEventListener("hashchange", openTarget);
      toggles.forEach((b) => b.removeEventListener("click", onToggle));
      menus().forEach((m) => m.removeEventListener("toggle", onMenu));
      document.removeEventListener("click", onClick);
    };
  }, [pathname]);
  return null;
}
