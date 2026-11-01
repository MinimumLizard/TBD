import Link from "next/link";
import { getTranslations } from "next-intl/server";

import Logo from "./Logo";
import type { Viewer } from "@/lib/entitlements";
import { MENUS, type Menu } from "@/lib/menu";

// Menus grouped by market (lib/menu.ts). Each menu is a <details>, so it opens without JavaScript; on a phone they
// fold into one "Menu" panel. A menu with a single page is a plain link.
export default async function SiteHeader({ viewer }: { viewer: Viewer }) {
  const t = await getTranslations();
  const name = t("site.name");
  const items = (menu: Menu) =>
    menu.items.map((item) => (
      <Link key={item.href} href={item.href}>
        <span className="m-title">
          {t(`menu.${menu.key}.${item.key}.title` as never)}
          {item.tier && <span className={`tier-pill ${item.tier}`}>{t(`tiers.${item.tier}`)}</span>}
        </span>
        <span className="m-desc">{t(`menu.${menu.key}.${item.key}.desc` as never)}</span>
      </Link>
    ));
  return (
    <header className="site">
      <div className="container bar">
        <Link href="/" className="brand" aria-label={name}>
          <Logo />
          <span>
            {name.replace(/IQ$/, "")}
            <span className="iq">{name.endsWith("IQ") ? "IQ" : ""}</span>
          </span>
        </Link>
        <nav className="menus" aria-label={t("ui.mainMenu")}>
          {MENUS.map((menu) =>
            menu.items.length === 1 ? (
              <Link key={menu.key} href={menu.items[0].href}>{t(`menu.${menu.key}.label` as never)}</Link>
            ) : (
              <details key={menu.key}>
                <summary>{t(`menu.${menu.key}.label` as never)}</summary>
                <div className="menu-panel">{items(menu)}</div>
              </details>
            ),
          )}
          <Link href="/plans">{t("nav.plans")}</Link>
        </nav>
        <Link href="/plans" className="tier-badge">
          {t("tiers.viewing", { tier: t(`tiers.${viewer.tier}`) })}
        </Link>
        <details className="mobile-menu">
          <summary>{t("ui.menu")}</summary>
          <nav className="menu-panel" aria-label={t("ui.mainMenu")}>
            {MENUS.map((menu) => (
              <div key={menu.key} style={{ display: "contents" }}>
                <span className="m-group">{t(`menu.${menu.key}.label` as never)}</span>
                {items(menu)}
              </div>
            ))}
            <span className="m-group">{t("nav.plans")}</span>
            <Link href="/plans">
              <span className="m-title">{t("nav.plans")}</span>
              <span className="m-desc">{t("menu.plansDesc")}</span>
            </Link>
          </nav>
        </details>
      </div>
    </header>
  );
}
