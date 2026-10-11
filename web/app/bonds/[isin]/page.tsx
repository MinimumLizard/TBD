import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";

import AsOf from "@/components/AsOf";
import Chart from "@/components/Chart";
import Locked from "@/components/Locked";
import ModelFooter from "@/components/ModelFooter";
import { bondName, isSynthetic } from "@/lib/bond-display";
import { lineOption } from "@/lib/charts";
import { bondLiquidity, bondQuoteHistory, bondReference, bondResidualHistory } from "@/lib/data/bonds";
import { NONE, date, percent, ratio } from "@/lib/format";
import { decodeSegment } from "@/lib/params";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";

export async function generateMetadata({ params }: { params: Promise<{ isin: string }> }) {
  return { title: decodeSegment((await params).isin) };
}

export default async function BondPage({ params }: { params: Promise<{ isin: string }> }) {
  const isin = decodeSegment((await params).isin);
  const [t, viewer] = await Promise.all([getTranslations(), getViewer()]);
  const [ref, quotes, residuals, liquidity] = await Promise.all([
    bondReference(viewer),
    bondQuoteHistory(viewer, isin),
    bondResidualHistory(viewer, isin),
    bondLiquidity(viewer),
  ]);
  const bond = ref.data?.get(isin);
  const title = bondName(isin, ref.data);
  if (ref.access.allowed && !bond) notFound();
  const history = quotes.data ?? [];
  const last = history[history.length - 1];
  const l = liquidity.data?.rows.find((r) => r.isin === isin);
  return (
    <>
      <h1>{title}</h1>
      {!ref.access.allowed ? (
        <Locked access={ref.access} />
      ) : (
        <>
          <AsOf day={last?.obs_date ?? null} calendar="lk_bond_market" />
          {isSynthetic(isin) && <div className="notice warn">{t("bond.synthetic")}</div>}
          <div className="grid two">
            <section>
              <h2>{t("bond.facts")}</h2>
              <dl className="facts">
                <dt>ISIN</dt>
                <dd>{isSynthetic(isin) ? NONE : isin}</dd>
                <dt>{t("bond.label")}</dt>
                <dd>{bond?.series_label ?? NONE}</dd>
                {bond?.notes && bond.notes !== bond.series_label && (
                  <>
                    <dt>{t("bond.printed")}</dt>
                    <dd>{bond.notes}</dd>
                  </>
                )}
                <dt>{t("bond.coupon")}</dt>
                <dd>{percent(bond?.coupon_pct, 2)}</dd>
                <dt>{t("bond.maturity")}</dt>
                <dd>{date(bond?.maturity_date)}</dd>
                {liquidity.access.allowed && l && (
                  <>
                    <dt>{t("bonds.activity")}</dt>
                    <dd>{t(`bonds.tier_${l.tier}`)}</dd>
                    <dt>{t("bond.lastAuction")}</dt>
                    <dd>{date(l.last_auction)}</dd>
                    <dt>{t("bond.bidToCover")}</dt>
                    <dd>{ratio(l.bid_to_cover)}</dd>
                    <dt>{t("bond.lastTrade")}</dt>
                    <dd>
                      {date(l.last_trade_date)} {l.last_trade_yield != null && `(${percent(l.last_trade_yield, 3)})`}
                    </dd>
                  </>
                )}
              </dl>
            </section>
            <section>
              <h2>{t("bonds.mid")}</h2>
              <dl className="facts">
                <dt>{t("bonds.bid")}</dt>
                <dd>{percent(last?.bid_yield, 3)}</dd>
                <dt>{t("bonds.offer")}</dt>
                <dd>{percent(last?.offer_yield, 3)}</dd>
                <dt>{t("bonds.mid")}</dt>
                <dd>{percent(last?.mid_yield, 3)}</dd>
              </dl>
            </section>
          </div>
          <h2>{t("bond.yieldChart")}</h2>
          <Chart label={t("bond.yieldChart")} option={lineOption([{ name: title, points: history.map((q) => [q.obs_date, q.mid_yield]) }], "%")} />
        </>
      )}
      <h2>{t("bond.residualChart")}</h2>
      {!residuals.access.allowed ? (
        <Locked access={residuals.access} />
      ) : (
        <Chart
          label={t("bond.residualChart")}
          option={lineOption([{ name: title, points: (residuals.data ?? []).map((p) => [p.obs_date, Math.round(p.residual_bp * 10) / 10]) }], "bp")}
        />
      )}
      <ModelFooter models={["bond_identity", "bond_ns_curve", "bond_liquidity"]} />
    </>
  );
}
