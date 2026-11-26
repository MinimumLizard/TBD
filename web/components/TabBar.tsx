"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

// The phone's main navigation: five tabs at the bottom of the screen, within reach of a thumb. Hidden on wide screens,
// where the header's menus do the same job. Labels come from the server (the layout), so no messages reach the
// browser here.
const ICONS: Record<string, React.ReactNode> = {
  home: <path d="M4 11 12 4l8 7v8a1 1 0 0 1-1 1h-5v-6h-4v6H5a1 1 0 0 1-1-1v-8Z" />,
  shares: <path d="M4 19h16M6 16l4-5 3 3 5-7" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />,
  bonds: <path d="M4 18c3-8 6-11 16-12M4 20h16" fill="none" strokeWidth="2" strokeLinecap="round" />,
  codes: <path d="M13.5 2 4.5 13.5H11L9.5 22l10-12.5H13L13.5 2Z" />,
  search: <path d="M11 4a7 7 0 1 1 0 14 7 7 0 0 1 0-14Zm5.5 12.5L21 21" fill="none" strokeWidth="2" strokeLinecap="round" />,
};

export interface Tab {
  key: string;
  href: string;
  label: string;
}

export default function TabBar({ tabs, label }: { tabs: Tab[]; label: string }) {
  const path = usePathname() ?? "/";
  const active = (href: string) => (href === "/" ? path === "/" || path.startsWith("/home") : path.startsWith(href));
  return (
    <nav className="tab-bar" aria-label={label}>
      {tabs.map((tab) => (
        <Link key={tab.key} href={tab.href} className={`tab tab-${tab.key}`} aria-current={active(tab.href) ? "page" : undefined}>
          <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" fill="currentColor" stroke="currentColor" strokeWidth="0">
            {ICONS[tab.key]}
          </svg>
          <span>{tab.label}</span>
        </Link>
      ))}
    </nav>
  );
}
