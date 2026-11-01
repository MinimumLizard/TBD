"use client";

// The little behaviour the collapsible sections and menus need; every page works without it.
// - A link to a section (#id) opens that section, and any closed section around the target.
// - The "open all / close all" button on long pages.
// - Opening one menu closes the others; a click elsewhere closes them all.
// The static preview copy carries the same behaviour in scripts/export-static.mjs (it has no React).
import { usePathname } from "next/navigation";
import { useEffect } from "react";

function openTarget() {
  const id = decodeURIComponent(window.location.hash.slice(1));
  if (!id) return;
  let el: HTMLElement | null = document.getElementById(id);
  while (el) {
    if (el instanceof HTMLDetailsElement) el.open = true;
    el = el.parentElement;
  }
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
    return () => {
      window.removeEventListener("hashchange", openTarget);
      toggles.forEach((b) => b.removeEventListener("click", onToggle));
      menus().forEach((m) => m.removeEventListener("toggle", onMenu));
      document.removeEventListener("click", onClick);
    };
  }, [pathname]);
  return null;
}
