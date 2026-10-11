import Link from "next/link";
import { getTranslations } from "next-intl/server";

import type { Viewer } from "@/lib/entitlements";

export default async function SiteHeader({ viewer }: { viewer: Viewer }) {
  const t = await getTranslations();
  const links = [
    ["/", t("nav.home")],
    ["/cse", t("nav.cse")],
    ["/cse/shares", t("nav.shares")],
    ["/bonds", t("nav.bonds")],
    ["/methods", t("nav.methods")],
    ["/about", t("nav.about")],
  ] as const;
  return (
    <header className="site">
      <div className="container bar">
        <Link href="/" className="brand">
          {t("site.name")}
        </Link>
        <nav aria-label="Main">
          {links.map(([href, label]) => (
            <Link key={href} href={href}>
              {label}
            </Link>
          ))}
        </nav>
        <span className="tier-badge">{t("tiers.viewing", { tier: t(`tiers.${viewer.tier}`) })}</span>
      </div>
    </header>
  );
}
