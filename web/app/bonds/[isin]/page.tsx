import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";

import AsOf from "@/components/AsOf";
import Chart from "@/components/Chart";
import Locked from "@/components/Locked";
import ModelFooter from "@/components/ModelFooter";
import PreviewNote from "@/components/PreviewNote";
import StatTile from "@/components/StatTile";
import Term from "@/components/Term";
import { bondName, isSynthetic } from "@/lib/bond-display";
import { lineOption } from "@/lib/charts";
import { bondCarryHistory, bondLiquidity, bondQuoteHistory, bondReference, bondResidualHistory, bondTradeHistory, bondZHistory } from "@/lib/data/bonds";
import type { Granted } from "@/lib/entitlements";
import { NONE, date, num, percent, ratio, signed } from "@/lib/format";
import { decodeSegment } from "@/lib/params";
import { yieldScenarios } from "@/lib/scenarios";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";

export async function generateMetadata({ params }: { params: Promise<{ isin: string }> }) {
  return { title: decodeSegment((await params).isin) };
}

// A free visitor sees a recent window of this model's history; say so, and which tier shows all of it.
async function WindowNote({ access }: { access: Granted }) {
  if (!access.minDate || !access.fullHistoryTier) return null;
  const t = await getTranslations();
  return <div className="notice lock" data-window={access.model}>{t("bond.historyWindow", { tier: t(`tiers.${access.fullHistoryTier}`) })}</div>;
}

export default async function BondPage({ params }: { params: Promise<{ isin: string }> }) {
  const isin = decodeSegment((await params).isin);
  const [t, viewer] = await Promise.all([getTranslations(), getViewer()]);
  const [ref, quotes, residuals, liquidity, trades, zs, carry] = await Promise.all([
    bondReference(viewer),
    bondQuoteHistory(viewer, isin),
    bondResidualHistory(viewer, isin),
    bondLiquidity(viewer),
    bondTradeHistory(viewer, isin),
    bondZHistory(viewer, isin),
    bondCarryHistory(viewer, isin),
  ]);
  const bond = ref.data?.get(isin);
  const title = bondName(isin, ref.data);
  if (ref.access.allowed && !bond) notFound();
  const history = quotes.data ?? [];
  const last = history[history.length - 1];
  const prev = history.length > 1 ? history[history.length - 2] : undefined;
  const l = liquidity.data?.rows.find((r) => r.isin === isin);
  const res = residuals.data ?? [];
  const lastRes = res[res.length - 1];
  const yearsLeft = bond?.maturity_date && last ? (Date.parse(bond.maturity_date) - Date.parse(last.obs_date)) / (365.25 * 864e5) : null;
  const z = zs.data ?? [];
  const lastZ = z[z.length - 1];
  const c = carry.data ?? [];
  const lastC = c[c.length - 1];
  const recentTrades = (trades.data ?? []).slice(-10).reverse();

  return (
    <>
      <h1>{title}</h1>
      {bond && (
        <p className="lead">
          {[bond.coupon_pct != null ? `${t("bond.coupon")} ${percent(bond.coupon_pct, 2)}` : null,
            `${t("bond.maturity")} ${date(bond.maturity_date)}`,
            yearsLeft != null ? `${num(yearsLeft, 1)} ${t("bonds.years").toLowerCase()}` : null].filter(Boolean).join(" · ")}
        </p>
      )}
      {!ref.access.allowed ? (
        <Locked access={ref.access} />
      ) : (
        <>
          <AsOf day={last?.obs_date ?? null} calendar="lk_bond_market" />
          {isSynthetic(isin) && <div className="notice warn">{t("bond.synthetic")}</div>}
          <div className="tiles">
            <StatTile label={t("bonds.mid")} value={percent(last?.mid_yield, 3)}
                      note={last?.mid_yield != null && prev?.mid_yield != null ? `${signed((last.mid_yield - prev.mid_yield) * 100, 1)} bp` : null}
                      spark={history.slice(-60).map((q) => q.mid_yield)} />
            <div className="tile stat">
              <span className="label"><Term id="bidOffer">{`${t("bonds.bid")} / ${t("bonds.offer")}`}</Term></span>
              <span className="value">{percent(last?.bid_yield, 2)} / {percent(last?.offer_yield, 2)}</span>
              {last?.bid_yield != null && last?.offer_yield != null && (
                <span className="sub">{num((last.bid_yield - last.offer_yield) * 100, 1)} bp</span>
              )}
            </div>
            {residuals.access.allowed && (
              <div className="tile stat">
                <span className="label"><Term id="residual" /></span>
                <span className="value">{lastRes ? `${signed(lastRes.residual_bp, 1)} bp` : NONE}</span>
                <span className="sub">{lastRes ? date(lastRes.obs_date) : null}</span>
              </div>
            )}
            {liquidity.access.allowed && l && (
              <div className="tile stat">
                <span className="label"><Term id="liquidity">{t("bonds.activity")}</Term></span>
                <span className="value" style={{ fontSize: "1.2rem" }}>{t(`bonds.tier_${l.tier}`)}</span>
                <span className="sub">{t("bond.lastTrade")}: {date(l.last_trade_date)}</span>
              </div>
            )}
          </div>

          <div className="grid two" style={{ marginTop: 16 }}>
            <section className="card">
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
            <section className="card">
              <h2><Term id="yield">{t("bond.yieldChart")}</Term></h2>
              <Chart label={t("bond.yieldChart")} height={240}
                     option={lineOption([{ name: title, points: history.map((q) => [q.obs_date, q.mid_yield]) }], "%", { area: true })} />
            </section>
          </div>
        </>
      )}

      <div className="section-head">
        <h2>{t("bond.analysisTitle")}</h2>
      </div>
      <div className="grid two">
        <section className="card">
          <h3><Term id="residual">{t("bond.residualChart")}</Term> <span className="tier-pill free">{t("tiers.free")}</span></h3>
          {!residuals.access.allowed ? (
            <Locked access={residuals.access} />
          ) : (
            <>
              <WindowNote access={residuals.access} />
              <Chart label={t("bond.residualChart")} height={240}
                     option={lineOption([{ name: title, points: res.map((p) => [p.obs_date, Math.round(p.residual_bp * 10) / 10]) }], "bp", { zeroLine: true })} />
            </>
          )}
        </section>
        <section className="card">
          <h3><Term id="zscore">{t("bond.zTitle")}</Term> <span className="tier-pill plus">{t("tiers.plus")}</span></h3>
          {!zs.access.allowed ? (
            <Locked access={zs.access} />
          ) : (
            <>
              <PreviewNote access={zs.access} />
              <p className="small muted">{t("bond.zBody")}</p>
              {lastZ ? (
                <>
                  <div className="stat" style={{ marginBottom: 8 }}>
                    <span className="label">{t("bond.zLatest")} · {date(lastZ.obs_date)}</span>
                    <span className="value">{signed(lastZ.zscore, 2)}</span>
                  </div>
                  <Chart label={t("bond.zTitle")} height={200}
                         option={lineOption([{ name: title, points: z.map((r) => [r.obs_date, Math.round(r.zscore * 100) / 100]) }], "z", { zeroLine: true })} />
                </>
              ) : (
                <p>{t("common.noData")}</p>
              )}
            </>
          )}
        </section>
      </div>

      <section className="card" style={{ marginTop: 16 }}>
        <h3>{t("bond.tradesTitle")} <span className="tier-pill free">{t("tiers.free")}</span></h3>
        {!trades.access.allowed ? (
          <Locked access={trades.access} />
        ) : (
          <>
            <WindowNote access={trades.access} />
            {recentTrades.length === 0 ? (
              <p className="muted">{t("bond.tradesNone")}</p>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>{t("bond.tradeDate")}</th>
                      <th className="num">{t("bond.tradeYield")}</th>
                      <th className="num">{t("bond.tradeResidual")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recentTrades.map((p) => (
                      <tr key={`${p.obs_date}-${p.observed_yield}`}>
                        <td>{date(p.obs_date)}</td>
                        <td className="num">{percent(p.observed_yield, 3)}</td>
                        <td className="num">{signed(p.residual_bp, 1)} bp</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </section>

      <section className="card" style={{ marginTop: 16 }}>
        <h3>{t("bond.carryTitle")} <span className="tier-pill pro">{t("tiers.pro")}</span></h3>
        {!carry.access.allowed ? (
          <Locked access={carry.access} />
        ) : !lastC ? (
          <p className="muted">{t("common.noData")}</p>
        ) : (
          <>
            <div className="tiles">
              <StatTile label={t("bond.price")} value={num(lastC.price, 2)} />
              <StatTile label={t("bond.duration")} value={num(lastC.duration, 2)} note={<Term id="duration">{t("common.whatIsThis")}</Term>} />
              <StatTile label={t("bond.convexity")} value={num(lastC.convexity, 1)} note={<Term id="convexity">{t("common.whatIsThis")}</Term>} />
              <StatTile label={t("carry.total")} value={`${signed(lastC.total_bp, 0)} bp`}
                        note={<><Term id="carry">{t("carry.carry")}</Term> {signed(lastC.carry_bp, 0)} · <Term id="rolldown">{t("carry.roll")}</Term> {signed(lastC.roll_bp, 0)}</>} />
            </div>
            {lastC.convexity != null && (
              <>
                <h3>{t("bond.scenarioTitle")}</h3>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>{t("bond.shift")}</th>
                        <th className="num">{t("bond.estPrice")}</th>
                        <th className="num">{t("bond.priceChange")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {yieldScenarios(lastC.price, lastC.duration, lastC.convexity).map((s) => (
                        <tr key={s.shiftBp}>
                          <td>{signed(s.shiftBp, 0)} bp</td>
                          <td className="num">{num(s.price, 2)}</td>
                          <td className="num"><span className={`chip ${s.change > 0 ? "up" : s.change < 0 ? "down" : "flat"}`}>{signed(s.change * 100, 2)}%</span></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="small muted">{t("bond.scenarioNote")}</p>
              </>
            )}
          </>
        )}
      </section>

      <ModelFooter models={["bond_identity", "bond_ns_curve", "bond_liquidity", "bond_rv_zscores", "bond_carry"]} />
    </>
  );
}
