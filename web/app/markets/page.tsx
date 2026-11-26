import Link from "next/link";
import { getTranslations } from "next-intl/server";

import ModelFooter from "@/components/ModelFooter";
import CheatStrip from "@/components/CheatStrip";
import PageHead from "@/components/PageHead";
import Section from "@/components/Section";
import Stats from "@/components/Stats";
import MarketBrief from "@/components/home/MarketBrief";
import { CurveCard, SharesCard } from "@/components/home/MarketCards";
import MarketTiles from "@/components/home/MarketTiles";
import { loadOverview } from "@/lib/overview";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";

export async function generateMetadata() {
  const t = await getTranslations();
  return { title: t("nav.markets") };
}

// Today's markets: the whole overview, for everyone (the front door's "skip", and "the full markets page" on a
// tailored home).
export default async function MarketsPage() {
  const [t, viewer] = await Promise.all([getTranslations(), getViewer()]);
  const o = await loadOverview(viewer);
  return (
    <>
      <PageHead eyebrow={t("home.eyebrow")} title={t("home.heroTitle")} lead={t("home.heroLead")}
                meta={<ul className="trust"><li>{t("home.trust1")}</li><li>{t("home.trust2")}</li><li>{t("home.trust3")}</li></ul>} />
      <CheatStrip />
      <MarketBrief o={o} />

      <div className="section-head">
        <h2>{t("home.snapshot")}</h2>
      </div>
      <MarketTiles o={o} />

      <div className="grid two" style={{ marginTop: 24 }}>
        <SharesCard o={o} />
        <CurveCard o={o} />
      </div>

      <div className="section-head">
        <h2>{t("home.linksTitle")}</h2>
      </div>
      <p className="muted" style={{ marginTop: -4 }}>{t("home.linksLead")}</p>
      <div className="links3">
        {([["1", "/learn/yield-curve"], ["2", "/learn/savings"], ["3", "/learn/shares-basics"]] as const).map(([n, href]) => (
          <div key={n}>
            <h3>{t(`home.link${n}Title`)}</h3>
            <p>{t(`home.link${n}Body`)}</p>
            <Link className="more" href={href}>{t(`home.link${n}Go`)} →</Link>
          </div>
        ))}
      </div>

      <Stats viewer={viewer} keys={["investors", "literacy", "savers"]} />

      <Section id="how-we-work" title={t("home.differsTitle")} summary={t("home.differsSum")}>
      <ul className="differs">
        {(["1", "2", "3", "4"] as const).map((n) => (
          <li key={n}>
            <strong>{t(`home.differ${n}Title`)}</strong>
            <span>{t(`home.differ${n}Body`)}</span>
          </li>
        ))}
      </ul>
      </Section>

      <Section id="plans" title={t("home.tiersTitle")} summary={t("home.tiersLead")}
               related={[{ href: "/plans", label: t("home.plansLink") }]}>
      <div className="tier-strip">
        {(["free", "pro", "plus"] as const).map((tier) => (
          <div key={tier}>
            <span className={`tier-pill ${tier}`} style={{ justifySelf: "start" }}>{t(`tiers.${tier}`)}</span>
            <p>{t(`home.tier${tier === "free" ? "Free" : tier === "plus" ? "Plus" : "Pro"}`)}</p>
          </div>
        ))}
      </div>
      </Section>

      <ModelFooter models={["cse_market_tape", "bond_ns_curve"]} />
    </>
  );
}
