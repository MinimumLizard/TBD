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
  const server = form.dataset.server !== undefined; // submit goes to the server, which searches further
  if (!server) form.querySelector<HTMLElement>("[data-filter-go]")?.setAttribute("hidden", "");
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
  const onSubmit = (e: Event) => { if (server) return; e.preventDefault(); apply(); };
  form.addEventListener("submit", onSubmit);
  input.addEventListener("input", apply);
  selects.forEach((s) => s.addEventListener("change", apply));
  return () => {
    form.removeEventListener("submit", onSubmit);
    input.removeEventListener("input", apply);
    selects.forEach((s) => s.removeEventListener("change", apply));
  };
}

export default function PageScripts() {
  const pathname = usePathname(); // the layout stays mounted across pages: wire each new page again
  useEffect(() => {
    openTarget();
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
    // dark mode, only by choice (the footer's button), remembered in this browser
    const themeButtons = Array.from(document.querySelectorAll<HTMLButtonElement>("button[data-theme-toggle]"));
    const themeLabel = (b: HTMLButtonElement) => {
      b.textContent = document.documentElement.dataset.theme === "dark" ? b.dataset.light ?? "" : b.dataset.dark ?? "";
    };
    const onTheme = () => {
      const dark = document.documentElement.dataset.theme !== "dark";
      if (dark) document.documentElement.dataset.theme = "dark";
      else delete document.documentElement.dataset.theme;
      try { localStorage.setItem("ziq-theme", dark ? "dark" : "light"); } catch { /* private mode: not remembered */ }
      themeButtons.forEach(themeLabel);
    };
    for (const b of themeButtons) { b.hidden = false; themeLabel(b); b.addEventListener("click", onTheme); }
    // the pinned section links (phones): mark the section on screen, and keep its link in view
    const links = Array.from(document.querySelectorAll<HTMLAnchorElement>(".onpage a[href^='#']"));
    let frame = 0;
    const onScroll = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        let current: HTMLAnchorElement | null = null;
        for (const a of links) {
          const el = document.getElementById(decodeURIComponent(a.hash.slice(1)));
          if (el && el.getBoundingClientRect().top < 140) current = a;
        }
        links.forEach((a) => a.classList.toggle("current", a === current));
        if (current?.parentElement) current.parentElement.scrollTo({ left: current.offsetLeft - 16, behavior: "smooth" });
      });
    };
    if (links.length) { window.addEventListener("scroll", onScroll, { passive: true }); onScroll(); }
    return () => {
      filters.forEach((off) => off());
      themeButtons.forEach((b) => b.removeEventListener("click", onTheme));
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("hashchange", openTarget);
      toggles.forEach((b) => b.removeEventListener("click", onToggle));
      menus().forEach((m) => m.removeEventListener("toggle", onMenu));
      document.removeEventListener("click", onClick);
    };
  }, [pathname]);
  return null;
}
