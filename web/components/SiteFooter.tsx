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
            <p className="footer-brand">
              <Logo size={24} /> {t("site.name")}
            </p>
            <p>{t("footer.tagline")}</p>
          </div>
          <div>
            <h3>{t("footer.markets")}</h3>
            <ul>
              <li><Link href="/cse">{t("menu.shares.market.title")}</Link></li>
              <li><Link href="/cse/shares">{t("menu.shares.allShares.title")}</Link></li>
              <li><Link href="/cse/dealings">{t("menu.shares.dealings.title")}</Link></li>
              <li><Link href="/bonds">{t("menu.bonds.curve.title")}</Link></li>
              <li><Link href="/learn/savings">{t("menu.savings.savings.title")}</Link></li>
            </ul>
          </div>
          <div>
            <h3>{t("footer.learn")}</h3>
            <ul>
              <li><Link href="/learn">{t("menu.learn.guides.title")}</Link></li>
              <li><Link href="/learn/glossary">{t("menu.learn.glossary.title")}</Link></li>
              <li><Link href="/methods">{t("menu.learn.methods.title")}</Link></li>
            </ul>
          </div>
          <div>
            <h3>{t("footer.company")}</h3>
            <ul>
              <li><Link href="/about">{t("nav.about")}</Link></li>
              <li><Link href="/plans">{t("nav.plans")}</Link></li>
              <li><Link href="/email/cse">{t("nav.weekly")}</Link></li>
              <li><Link href="/feedback">{t("nav.feedback")}</Link></li>
            </ul>
          </div>
        </div>
        <form className="vote" method="post" action="/api/feedback">
          <input type="hidden" name="kind" value="page_vote" />
          <span>{t("feedback.vote.question")}</span>
          <button type="submit" name="useful" value="yes">{t("feedback.vote.yes")}</button>
          <button type="submit" name="useful" value="no">{t("feedback.vote.no")}</button>
          <Link href="/feedback">{t("feedback.vote.more")}</Link>
        </form>
        <Disclaimer keys={SITE_WIDE_DISCLAIMERS} />
        <p style={{ marginTop: 12 }}>{t("footer.rights")}</p>
      </div>
    </footer>
  );
}
