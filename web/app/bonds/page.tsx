import Link from "next/link";
import { getTranslations } from "next-intl/server";

import AsOf from "@/components/AsOf";
import Chart from "@/components/Chart";
import Locked from "@/components/Locked";
import ModelFooter from "@/components/ModelFooter";
import { bondHref, bondName } from "@/lib/bond-display";
import { LOW_WEIGHT, curveOption, curvePoints } from "@/lib/charts";
import { bondCurve, bondLiquidity, bondQuotes, bondReference } from "@/lib/data/bonds";
import { NONE, date, int, lkr, num, percent, signed, tone } from "@/lib/format";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";
const WIDE_QUOTE_BP = 50; // the curve model's own line between a dealt quote and an administered one

export async function generateMetadata() {
  const t = await getTranslations();
  return { title: t("bonds.title") };
}

export default async function BondsPage() {
  const [t, viewer] = await Promise.all([getTranslations(), getViewer()]);
  const curve = await bondCurve(viewer);
  const day = curve.data?.fit?.obs_date;
  const [ref, quotes, liquidity] = await Promise.all([bondReference(viewer), bondQuotes(viewer, day), bondLiquidity(viewer, day)]);
  const fit = curve.data?.fit ?? null;
  const residual = new Map((curve.data?.points ?? []).filter((p) => p.source === "quote").map((p) => [p.isin, p.residual_bp]));
  const liq = new Map((liquidity.data?.rows ?? []).map((r) => [r.isin, r]));
  const rows = [...(quotes.data?.quotes ?? [])].sort((a, b) =>
    (ref.data?.get(a.isin)?.maturity_date ?? "").localeCompare(ref.data?.get(b.isin)?.maturity_date ?? ""),
  );

  return (
    <>
      <h1>{t("bonds.title")}</h1>
      <p className="lead">{t("bonds.intro")}</p>
      <h2>{t("bonds.curveTitle")}</h2>
      {!curve.access.allowed ? (
        <Locked access={curve.access} />
      ) : fit ? (
        <>
          <AsOf day={fit.obs_date} calendar="lk_bond_market" />
          <Chart
            label={t("bonds.curveTitle")}
            height={380}
            option={curveOption({
                quotes: curve.data!.points.filter((p) => p.source === "quote" && (p.weight ?? 1) >= LOW_WEIGHT).map((p) => [p.tau_years, p.observed_yield, bondName(p.isin, ref.data)]),
                wide: curve.data!.points.filter((p) => p.source === "quote" && (p.weight ?? 1) < LOW_WEIGHT).map((p) => [p.tau_years, p.observed_yield, bondName(p.isin, ref.data)]),
                trades: curve.data!.points.filter((p) => p.source === "trade").map((p) => [p.tau_years, p.observed_yield, bondName(p.isin, ref.data)]),
                curve: curvePoints(fit, Math.max(...curve.data!.points.map((p) => p.tau_years))),
                names: { quotes: t("bonds.quotes"), wide: t("bonds.wideQuotes"), trades: t("bonds.trades"), curve: t("bonds.curve"), years: t("bonds.years"), yield: t("bonds.yield") },
              })}
          />
          <p className="small muted">
            {t("bonds.fitStats", { n: fit.n_quotes, rmse: num(fit.rmse_bp, 1), trades: fit.n_trades })}{" "}
            {fit.trade_bias_bp != null && t("bonds.tradeBias", { bias: signed(fit.trade_bias_bp, 1) })}
          </p>
          <p className="small muted">{t("bonds.curveNote")}</p>
        </>
      ) : (
        <p>{t("common.noData")}</p>
      )}

      <h2>{t("bonds.tableTitle")}</h2>
      {!quotes.access.allowed ? (
        <Locked access={quotes.access} />
      ) : (
        <>
          <p className="small muted">{t("bonds.tableNote")}</p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{t("bonds.bond")}</th>
                  <th>{t("bonds.maturity")}</th>
                  <th className="num">{t("bonds.bid")}</th>
                  <th className="num">{t("bonds.offer")}</th>
                  <th className="num">{t("bonds.mid")}</th>
                  <th className="num">{t("bonds.residual")}</th>
                  <th>{t("bonds.activity")}</th>
                  <th className="num">{t("bonds.turnover60")}</th>
                  <th className="num">{t("bonds.daysTraded")}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((q) => {
                  const l = liq.get(q.isin);
                  const r = residual.get(q.isin);
                  return (
                    <tr key={q.isin}>
                      <td>
                        <Link href={bondHref(q.isin)}>{bondName(q.isin, ref.data)}</Link>
                      </td>
                      <td>{date(ref.data?.get(q.isin)?.maturity_date)}</td>
                      <td className="num">{percent(q.bid_yield, 3)}</td>
                      <td className="num">{percent(q.offer_yield, 3)}</td>
                      <td className="num">{q.mid_yield == null ? <span className="small muted">{t("bonds.oneWay")}</span> : percent(q.mid_yield, 3)}</td>
                      <td className={`num ${tone(r)}`}>
                        {r == null ? NONE : signed(r, 1)}
                        {q.bid_yield != null && q.offer_yield != null && (q.bid_yield - q.offer_yield) * 100 > WIDE_QUOTE_BP && (
                          <>
                            {" "}
                            <span className="badge">{t("bonds.wideQuote")}</span>
                          </>
                        )}
                      </td>
                      <td>{liquidity.access.allowed ? t(`bonds.tier_${l?.tier ?? "wider"}`) : NONE}</td>
                      <td className="num">{l ? lkr(l.turnover_lkr) : NONE}</td>
                      <td className="num">{l ? int(l.days_traded) : NONE}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="small muted">{t("bonds.tierHelp")}</p>
        </>
      )}
      {!liquidity.access.allowed && <Locked access={liquidity.access} />}

      <h2>{t("bonds.more")}</h2>
      <ul>
        <li>
          <Link href="/bonds/zscores">{t("bonds.zscoresLink")}</Link>
        </li>
        <li>
          <Link href="/bonds/execution">{t("bonds.executionLink")}</Link>
        </li>
        <li>
          <Link href="/bonds/carry">{t("bonds.carryLink")}</Link>
        </li>
      </ul>
      <ModelFooter models={["bond_ns_curve", "bond_identity", "bond_liquidity"]} />
    </>
  );
}
