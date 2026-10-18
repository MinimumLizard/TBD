import Link from "next/link";
import { getTranslations } from "next-intl/server";

import Disclaimer, { SITE_WIDE_DISCLAIMERS } from "./Disclaimer";
import Logo from "./Logo";

export default async function SiteFooter() {
  const t = await getTranslations();
  return (
    <footer className="site">
      <div className="container">
        <div className="cols">
          <div>
            <p className="display" style={{ display: "flex", gap: 8, alignItems: "center", fontWeight: 800, color: "#fff", fontSize: "1.05rem" }}>
              <Logo size={24} /> {t("site.name")}
            </p>
            <p>{t("footer.tagline")}</p>
          </div>
          <div>
            <h3>{t("footer.markets")}</h3>
            <ul>
              <li><Link href="/cse">{t("nav.cse")}</Link></li>
              <li><Link href="/cse/shares">{t("nav.shares")}</Link></li>
              <li><Link href="/bonds">{t("nav.bonds")}</Link></li>
            </ul>
          </div>
          <div>
            <h3>{t("footer.company")}</h3>
            <ul>
              <li><Link href="/learn">{t("nav.learn")}</Link></li>
              <li><Link href="/plans">{t("nav.plans")}</Link></li>
              <li><Link href="/methods">{t("nav.methods")}</Link></li>
              <li><Link href="/about">{t("nav.about")}</Link></li>
            </ul>
          </div>
        </div>
        <Disclaimer keys={SITE_WIDE_DISCLAIMERS} />
        <p style={{ marginTop: 12 }}>{t("footer.rights")}</p>
      </div>
    </footer>
  );
}
