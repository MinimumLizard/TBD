import Link from "next/link";
import { getTranslations } from "next-intl/server";

import Logo from "./Logo";
import type { Viewer } from "@/lib/entitlements";

export default async function SiteHeader({ viewer }: { viewer: Viewer }) {
  const t = await getTranslations();
  const links = [
    ["/", t("nav.home")],
    ["/cse", t("nav.cse")],
    ["/cse/shares", t("nav.shares")],
    ["/bonds", t("nav.bonds")],
    ["/crypto", t("nav.crypto")],
    ["/learn", t("nav.learn")],
    ["/plans", t("nav.plans")],
    ["/methods", t("nav.methods")],
  ] as const;
  const name = t("site.name");
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
        <nav aria-label="Main">
          {links.map(([href, label]) => (
            <Link key={href} href={href}>
              {label}
            </Link>
          ))}
        </nav>
        <Link href="/plans" className="tier-badge">
          {t("tiers.viewing", { tier: t(`tiers.${viewer.tier}`) })}
        </Link>
      </div>
    </header>
  );
}
