import Link from "next/link";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";

import AsOf from "@/components/AsOf";
import Chart from "@/components/Chart";
import CryptoNotice from "@/components/CryptoNotice";
import Locked from "@/components/Locked";
import ModelFooter from "@/components/ModelFooter";
import PreviewNote from "@/components/PreviewNote";
import StatTile from "@/components/StatTile";
import Term from "@/components/Term";
import { lineOption, sig, weeklyPoints } from "@/lib/charts";
import { assetBySlug, price } from "@/lib/crypto-display";
import { type CycleAnchor, type CycleMonth, type TrendDay, cryptoCycle, cryptoHistory, cryptoTrend } from "@/lib/data/crypto";
import { NONE, date, int, num, pct, percent, ratio, tone } from "@/lib/format";
import type { ModelName } from "@/lib/registry";
import { decodeSegment } from "@/lib/params";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";

export async function generateMetadata({ params }: { params: Promise<{ asset: string }> }) {
  const asset = assetBySlug(decodeSegment((await params).asset));
  if (!asset) return {};
  const t = await getTranslations();
  return { title: t(`crypto.assets.${asset.slug}` as never) };
}

function monthGrid(months: CycleMonth[]): { year: number; cells: (number | null | undefined)[] }[] {
  const byYear = new Map<number, (number | null | undefined)[]>();
  for (const m of months) {
    const [y, mo] = m.month.split("-").map(Number);
    if (!byYear.has(y)) byYear.set(y, Array(12).fill(undefined));
    byYear.get(y)![mo - 1] = m.ret_month;
  }
  return [...byYear.entries()].sort((a, b) => b[0] - a[0]).map(([year, cells]) => ({ year, cells }));
}

export default async function CryptoAssetPage({ params }: { params: Promise<{ asset: string }> }) {
  const asset = assetBySlug(decodeSegment((await params).asset));
  if (!asset) notFound();
  const [t, viewer] = await Promise.all([getTranslations(), getViewer()]);
  const isBtc = asset.pair === "btcusd";
  const [history, cycle, trend] = await Promise.all([
    cryptoHistory(viewer, asset.pair),
    asset.cycle ? cryptoCycle(viewer, asset.pair) : null,
    isBtc ? cryptoTrend(viewer, asset.pair) : null,
  ]);
  const name = t(`crypto.assets.${asset.slug}` as never);
  const rows = history.data ?? [];
  const last = rows[rows.length - 1];
  if (history.access.allowed && !last) notFound();
  const cyc = cycle?.access.allowed ? cycle.data : null;
  const daily = cyc?.daily ?? [];
  const lc = daily[daily.length - 1];
  const p = (v: number | null | undefined) => price(v, asset.quote);
  const unit = asset.quote === "USD" ? "USD" : "BTC";
  const models: ModelName[] = ["crypto_market", ...(asset.cycle ? (["crypto_cycle"] as const) : []), ...(isBtc ? (["crypto_trend_bands"] as const) : [])];

  const anchorLabel = (a: CycleAnchor) => t(`cryptoAsset.kind_${a.kind}` as never, { n: a.epoch } as never);

  const trendChart = (fit: TrendDay["fit"]) => {
    const r = (trend?.data?.rows ?? []).filter((x) => x.fit === fit);
    return lineOption([
      { name: t("crypto.price"), points: weeklyPoints(r, (x) => x.close, 200) },
      { name: t("cryptoAsset.fitted"), points: weeklyPoints(r, (x) => x.fitted, 200), dashed: true },
      { name: `${t("cryptoAsset.inner")} (−)`, points: weeklyPoints(r, (x) => x.lower_1, 200), faint: true },
      { name: `${t("cryptoAsset.inner")} (+)`, points: weeklyPoints(r, (x) => x.upper_1, 200), faint: true },
      { name: `${t("cryptoAsset.outer")} (−)`, points: weeklyPoints(r, (x) => x.lower_2, 200), faint: true },
      { name: `${t("cryptoAsset.outer")} (+)`, points: weeklyPoints(r, (x) => x.upper_2, 200), faint: true },
    ], "USD", { logY: true });
  };

  return (
    <>
      <p className="small"><Link href="/crypto">← {t("crypto.title")}</Link></p>
      <h1>{name}</h1>
      {last && <p className="lead">{t("cryptoAsset.pairLine", { pair: asset.label, date: date(rows[0].day) })}</p>}
      <CryptoNotice />
      {!history.access.allowed ? (
        <Locked access={history.access} />
      ) : (
        <>
          <AsOf day={last.day} calendar="crypto" />
          <div className="tiles">
            <StatTile label={t("cryptoAsset.latest")} value={p(last.close)} change={last.ret_1d}
                      spark={rows.slice(-90).map((r) => r.close)} sparkCaption={t("crypto.last90")} />
            <div className="tile stat">
              <span className="label"><Term id="drawdown">{t("cryptoAsset.drawdown")}</Term></span>
              <span className="value">{pct(last.drawdown)}</span>
              <span className="sub">
                {t("cryptoAsset.high")}: {p(last.ath_close)}, {t("cryptoAsset.highOn", { date: date(last.ath_day), days: int(last.days_since_ath) })}
              </span>
            </div>
            <div className="tile stat">
              <span className="label"><Term id="volatility">{t("cryptoAsset.vol30")}</Term></span>
              <span className="value">{percent(last.vol_30d == null ? null : last.vol_30d * 100, 0)}</span>
              <span className="sub">
                {t("cryptoAsset.vol90")}: {percent(last.vol_90d == null ? null : last.vol_90d * 100, 0)} · {t("cryptoAsset.volNote")}
              </span>
            </div>
          </div>
          {asset.slug === "eth" && <p className="small" style={{ marginTop: 8 }}><Link href="/crypto/ethbtc">{t("cryptoAsset.ethbtc")} →</Link></p>}

          <h2>{t("cryptoAsset.returns")}</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{t("cryptoAsset.window")}</th>
                  <th className="num">{t("cryptoAsset.change")}</th>
                </tr>
              </thead>
              <tbody>
                {([["d1", last.ret_1d], ["d7", last.ret_7d], ["d30", last.ret_30d], ["y1", last.ret_1y]] as const).map(([k, v]) => (
                  <tr key={k}>
                    <td>{t(`crypto.${k}`)}</td>
                    <td className={`num ${tone(v)}`}>{pct(v)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <h2><Term id="movingAverage">{daily.length ? t("cryptoAsset.priceChart") : t("cryptoAsset.priceOnly")}</Term></h2>
          {cycle?.access.allowed && <PreviewNote access={cycle.access} />}
          <Chart
            label={t("cryptoAsset.priceChart")}
            option={lineOption([
              { name: t("crypto.price"), points: weeklyPoints(rows, (r) => r.close) },
              ...(daily.length ? [
                { name: t("cryptoAsset.sma50"), points: weeklyPoints(daily, (r) => r.sma_50), dashed: true },
                { name: t("cryptoAsset.sma200"), points: weeklyPoints(daily, (r) => r.sma_200), dashed: true },
              ] : []),
            ], unit, { logY: true })}
          />
          <div className="grid two">
            <section className="card">
              <h3><Term id="drawdown">{t("cryptoAsset.drawdownChart")}</Term></h3>
              <Chart label={t("cryptoAsset.drawdownChart")} height={220}
                     option={lineOption([{ name: name, points: weeklyPoints(rows, (r) => r.drawdown * 100) }], "%", { area: true, percentY: true })} />
            </section>
            <section className="card">
              <h3><Term id="volatility">{t("cryptoAsset.volChart")}</Term></h3>
              <Chart label={t("cryptoAsset.volChart")} height={220}
                     option={lineOption([
                       { name: t("cryptoAsset.vol30"), points: weeklyPoints(rows, (r) => (r.vol_30d == null ? null : r.vol_30d * 100)) },
                       { name: t("cryptoAsset.vol90"), points: weeklyPoints(rows, (r) => (r.vol_90d == null ? null : r.vol_90d * 100)), dashed: true },
                     ], "%", { percentY: true })} />
            </section>
          </div>
        </>
      )}

      {cycle && (
        <>
          <div className="section-head">
            <h2>{t("cryptoAsset.cycleTitle")}</h2>
            <span className="tier-pill plus">{t("tiers.plus")}</span>
          </div>
          {!cycle.access.allowed ? (
            <Locked access={cycle.access} />
          ) : !lc ? (
            <p className="muted">{t("common.noData")}</p>
          ) : (
            <>
              <PreviewNote access={cycle.access} />
              <p className="asof">{t("common.asOf", { date: date(lc.day) })}</p>
              <div className="tiles">
                <StatTile label={t("cryptoAsset.mayer")} value={ratio(lc.mayer)} note={t("cryptoAsset.mayerNote")} />
                <StatTile label={t("crypto.sma200w")} value={p(lc.sma_200w)}
                          note={lc.sma_200w_chg_4w != null ? t("cryptoAsset.sma200wNote", { pct: pct(lc.sma_200w_chg_4w) }) : null} />
                <StatTile label={t("cryptoAsset.dist20w")} value={pct(lc.dist_20w)} note={`${t("cryptoAsset.sma20w")}: ${p(lc.sma_20w)}`} />
                <div className="tile stat">
                  <span className="label"><Term id="halving">{t("cryptoAsset.halving")}</Term></span>
                  <span className="value">{pct(lc.roi_since_halving)}</span>
                  <span className="sub">
                    {lc.last_halving ? t("cryptoAsset.halvingNote", { days: int(lc.days_since_halving), date: date(lc.last_halving) }) : NONE}
                  </span>
                </div>
              </div>

              <h3>{t("cryptoAsset.bandChart")}</h3>
              <Chart
                label={t("cryptoAsset.bandChart")}
                option={lineOption([
                  { name: t("crypto.price"), points: weeklyPoints(daily, (r) => r.close) },
                  { name: t("cryptoAsset.sma20w"), points: weeklyPoints(daily, (r) => r.sma_20w), dashed: true },
                  { name: t("cryptoAsset.ema21w"), points: weeklyPoints(daily, (r) => r.ema_21w), dashed: true },
                  { name: t("crypto.sma200w"), points: weeklyPoints(daily, (r) => r.sma_200w) },
                ], unit, { logY: true })}
              />

              <h3>{t("cryptoAsset.piChart")}</h3>
              <Chart
                label={t("cryptoAsset.piChart")}
                option={lineOption([
                  { name: t("crypto.price"), points: weeklyPoints(daily, (r) => r.close), faint: true },
                  { name: t("cryptoAsset.piTop"), points: weeklyPoints(daily, (r) => r.pi_sma_111) },
                  { name: t("cryptoAsset.piTop2"), points: weeklyPoints(daily, (r) => r.pi_sma_350x2) },
                  { name: t("cryptoAsset.piBottom"), points: weeklyPoints(daily, (r) => r.pi_ema_150), dashed: true },
                  { name: t("cryptoAsset.piBottom2"), points: weeklyPoints(daily, (r) => r.pi_sma_471x0745), dashed: true },
                ], unit, { logY: true })}
              />
              <h3>{t("cryptoAsset.crossings")}</h3>
              {(cyc?.events ?? []).length === 0 ? (
                <p className="muted">{t("cryptoAsset.crossingsNone")}</p>
              ) : (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>{t("cryptoAsset.date")}</th>
                        <th>{t("cryptoAsset.event")}</th>
                        <th className="num">{t("cryptoAsset.closeAt")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(cyc?.events ?? []).map((e) => (
                        <tr key={`${e.kind}-${e.day}`}>
                          <td>{date(e.day)}</td>
                          <td>{e.kind === "pi_top_cross" ? t("cryptoAsset.crossTop") : t("cryptoAsset.crossBottom")}</td>
                          <td className="num">{p(e.close)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              <p className="small muted">{t("cryptoAsset.crossingsNote")}</p>

              <h3><Term id="halving">{t("cryptoAsset.cycleTable")}</Term></h3>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>{t("cryptoAsset.event")}</th>
                      <th>{t("cryptoAsset.date")}</th>
                      <th className="num">{t("cryptoAsset.closeAt")}</th>
                      <th className="num">{t("cryptoAsset.fromPrior")}</th>
                      <th className="num">{t("cryptoAsset.daysFromPrior")}</th>
                      <th className="num">{t("cryptoAsset.since")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(cyc?.anchors ?? []).map((a) => (
                      <tr key={`${a.kind}-${a.epoch}`}>
                        <td>
                          {anchorLabel(a)}
                          {a.provisional && <span className="sub">{t("cryptoAsset.provisional")}</span>}
                        </td>
                        <td>{date(a.anchor_day)}</td>
                        <td className="num">{p(a.anchor_close)}</td>
                        <td className={`num ${tone(a.change_from_prior)}`}>{pct(a.change_from_prior, 0)}</td>
                        <td className="num">{int(a.days_from_prior)}</td>
                        <td className={`num ${tone(a.roi)}`}>{pct(a.roi, 0)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="small muted">{t("cryptoAsset.cycleTableNote")}</p>

              <h3>{t("cryptoAsset.monthly")}</h3>
              <div className="table-wrap">
                <table className="heat">
                  <thead>
                    <tr>
                      <th>{t("cryptoAsset.year")}</th>
                      {(t.raw("cryptoAsset.months") as string[]).map((m) => <th key={m} className="num">{m}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {monthGrid(cyc?.months ?? []).map(({ year, cells }) => (
                      <tr key={year}>
                        <td>{year}</td>
                        {cells.map((v, i) => (
                          <td key={i} className="num">{v === undefined ? "" : <span className={`chip ${tone(v)}`}>{pct(v, v != null && Math.abs(v) < 0.005 ? 1 : 0)}</span>}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="small muted">{t("cryptoAsset.monthlyNote", { pct: pct(lc.ret_mtd) })}</p>
            </>
          )}
        </>
      )}

      {trend && (
        <>
          <div className="section-head">
            <h2><Term id="powerLaw">{t("cryptoAsset.trendTitle")}</Term></h2>
            <span className="tier-pill pro">{t("tiers.pro")}</span>
          </div>
          {!trend.access.allowed ? (
            <Locked access={trend.access} />
          ) : !trend.data?.day ? (
            <p className="muted">{t("common.noData")}</p>
          ) : (
            <>
              <p className="small muted">{t("cryptoAsset.trendNote")}</p>
              <p className="asof">{t("common.asOf", { date: date(trend.data.day) })}</p>
              <div className="grid two">
                {(["power_law", "log_regression"] as const).map((fit) => {
                  const r = trend.data!.rows.filter((x) => x.fit === fit);
                  const lt = r[r.length - 1];
                  return (
                    <section key={fit} className="card">
                      <h3>{t(`cryptoAsset.fit_${fit}`)}</h3>
                      <p className="small muted">{t(`cryptoAsset.fit_${fit}_note`)}</p>
                      {lt && (
                        <>
                          <div className="stat" style={{ marginBottom: 8 }}>
                            <span className="label">{t("cryptoAsset.position")}</span>
                            <span className="value" data-position={fit}>{num(lt.position, 2)}</span>
                            <span className="sub">{t("cryptoAsset.positionNote")}</span>
                          </div>
                          <dl className="facts">
                            <dt>{t("cryptoAsset.fitted")}</dt>
                            <dd>{p(lt.fitted)}</dd>
                            <dt>{t("cryptoAsset.inner")}</dt>
                            <dd>{p(lt.lower_1)} – {p(lt.upper_1)}</dd>
                            <dt>{t("cryptoAsset.outer")}</dt>
                            <dd>{p(lt.lower_2)} – {p(lt.upper_2)}</dd>
                          </dl>
                          <p className="small muted" style={{ marginTop: 8 }}>
                            {t("cryptoAsset.coefficients", { date: date(lt.day), slope: num(sig(lt.slope), 3), n: int(lt.n_obs) })}
                          </p>
                        </>
                      )}
                      <Chart label={t(`cryptoAsset.fit_${fit}`)} height={260} option={trendChart(fit)} />
                    </section>
                  );
                })}
              </div>
            </>
          )}
        </>
      )}
      <ModelFooter models={models} shownAbove={["crypto_risk"]} />
    </>
  );
}
