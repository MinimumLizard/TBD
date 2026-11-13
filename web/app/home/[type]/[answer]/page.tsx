import Link from "next/link";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";

import ModelFooter from "@/components/ModelFooter";
import PageHead from "@/components/PageHead";
import SignupBox from "@/components/SignupBox";
import MarketBrief from "@/components/home/MarketBrief";
import { CurveCard, SharesCard } from "@/components/home/MarketCards";
import MarketTiles from "@/components/home/MarketTiles";
import PathStrip from "@/components/home/PathStrip";
import { GuidePicks, ToolPicks } from "@/components/home/Picks";
import SavingsSnapshot from "@/components/home/SavingsSnapshot";
import { type Block, home } from "@/lib/homes";
import { loadOverview } from "@/lib/overview";
import { decodeSegment } from "@/lib/params";
import { answer } from "@/lib/paths";
import type { ModelName } from "@/lib/registry";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";

export async function generateMetadata() {
  const t = await getTranslations();
  return { title: t("homes.eyebrow") };
}

const MODELS: Partial<Record<Block, ModelName[]>> = {
  savings: ["lk_savings_compare"], brief: ["cse_market_tape", "bond_ns_curve"], tiles: ["cse_market_tape", "bond_ns_curve"],
  shareTiles: ["cse_market_tape"], yieldTiles: ["bond_ns_curve"], shares: ["cse_market_tape"], curve: ["bond_ns_curve"],
  charts: ["cse_market_tape", "bond_ns_curve"],
};

// A visitor's own home page: the blocks, guides and pages that fit what they answered (lib/homes.ts). The figures
// are the free ones every visitor may see; a paid page appears only as a link carrying its tier.
export default async function HomePage({ params }: { params: Promise<{ type: string; answer: string }> }) {
  const raw = await params;
  const type = decodeSegment(raw.type);
  const key = decodeSegment(raw.answer);
  const a = answer(type, key);
  const h = home(type, key);
  if (!a || !h) notFound();
  const [t, viewer] = await Promise.all([getTranslations(), getViewer()]);
  const o = await loadOverview(viewer);
  const page = `/home/${type}/${key}`;
  const block = (b: Block) => {
    switch (b) {
      case "savings": return <SavingsSnapshot viewer={viewer} />;
      case "brief": return <MarketBrief o={o} />;
      case "tiles": return <MarketTiles o={o} />;
      case "shareTiles": return <MarketTiles o={o} yields={false} />;
      case "yieldTiles": return <MarketTiles o={o} shares={false} />;
      case "shares": return <SharesCard o={o} />;
      case "curve": return <CurveCard o={o} />;
      case "charts": return <div className="grid two"><SharesCard o={o} /><CurveCard o={o} /></div>;
      case "lookup": return (
        <section className="card lookup">
          <h2>{t("homes.lookupTitle")}</h2>
          <form action="/search" method="get" role="search">
            <label htmlFor="home-lookup" className="muted">{t("homes.lookupLead")}</label>
            <div className="signup-row">
              <input id="home-lookup" type="search" name="q" autoComplete="off" />
              <button className="button" type="submit">{t("homes.lookupButton")}</button>
            </div>
          </form>
        </section>
      );
    }
  };
  const models = [...new Set(h.blocks.flatMap((b) => MODELS[b] ?? []))];
  return (
    <>
      <PageHead
        eyebrow={t("homes.eyebrow")}
        title={t(`homes.titles.${type}` as never)}
        lead={t(`homes.leads.${type}` as never)}
        meta={
          <p className="small muted home-meta">
            <span>{t("homes.youSaid")}: {t(`start.types.${type}.short` as never)} · {t(`start.questions.${type}.${key}` as never)}</span>
            <Link href="/start">{t("homes.change")}</Link>
            <Link href="/markets">{t("homes.everything")}</Link>
          </p>
        }
      />
      <PathStrip steps={a.steps} />
      <div className="home-blocks">
        {h.blocks.map((b) => <div key={b}>{block(b)}</div>)}
      </div>
      <GuidePicks slugs={h.guides} />
      <ToolPicks hrefs={h.tools} />
      <SignupBox page={page} type={type} answer={key} />
      {models.length > 0 && <ModelFooter models={models} />}
    </>
  );
}
