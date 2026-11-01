import Link from "next/link";
import { getTranslations } from "next-intl/server";

import AsOf from "@/components/AsOf";
import Brief from "@/components/Brief";
import FilterBar from "@/components/FilterBar";
import PageHead from "@/components/PageHead";
import Section from "@/components/Section";
import Chart from "@/components/Chart";
import Locked from "@/components/Locked";
import ModelFooter from "@/components/ModelFooter";
import { bondHref, bondName } from "@/lib/bond-display";
import { LOW_WEIGHT, curveOption, curvePoints, nelsonSiegel } from "@/lib/charts";
import { bondCurve, bondLiquidity, bondQuotes, bondReference } from "@/lib/data/bonds";
import { NONE, date, int, lkr, num, percent, signed } from "@/lib/format";
import { matchesQuery, param, searchText } from "@/lib/filter";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";
const WIDE_QUOTE_BP = 50; // the curve model's own line between a dealt quote and an administered one

export async function generateMetadata() {
  const t = await getTranslations();
  return { title: t("bonds.title") };
}

const BANDS = [["short", 0, 2], ["medium", 2, 5], ["long", 5, 10], ["longest", 10, Infinity]] as const;

export default async function BondsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = await searchParams;
  const query = param(params.q);
  const bandParam = param(params.band);
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

  const yearsLeft = (isin: string) => {
    const m = ref.data?.get(isin)?.maturity_date;
    return m && day ? (Date.parse(m) - Date.parse(day)) / (365.25 * 864e5) : null;
  };
  const bandOf = (isin: string) => {
    const y = yearsLeft(isin);
    return y == null ? "" : BANDS.find(([, lo, hi]) => y >= lo && y < hi)?.[0] ?? "";
  };
  const textOf = (isin: string) => searchText(bondName(isin, ref.data), isin, ref.data?.get(isin)?.maturity_date?.slice(0, 4));
  const showRow = (isin: string) => matchesQuery(textOf(isin), query) && (!bandParam || bandOf(isin) === bandParam);
  const ns = (tau: number) => (fit ? nelsonSiegel(tau, fit.beta0, fit.beta1, fit.beta2, fit.lambda_years) : null);
  const [y1, y5, y10] = [ns(1), ns(5), ns(10)];
  const slope = y1 != null && y10 != null ? (y10 - y1) * 100 : null;
  const glance: string[] = [];
  if (fit && y1 != null && y5 != null && y10 != null) {
    glance.push(t("home.summary.bonds", { y1: percent(y1, 2), y5: percent(y5, 2), y10: percent(y10, 2) }));
    if (slope != null) glance.push(t(slope >= 0 ? "bonds.glance.slopeUp" : "bonds.glance.slopeDown", { bp: num(Math.abs(slope), 0) }));
    glance.push(t("bonds.glance.quoted", { n: fit.n_quotes, trades: fit.n_trades }));
    if (fit.rmse_bp != null) glance.push(t("bonds.glance.fit", { rmse: num(fit.rmse_bp, 1) }));
  }
  const parts = [
    { id: "curve", label: t("bonds.sections.curve") },
    { id: "table", label: t("bonds.sections.table") },
    { id: "further", label: t("bonds.sections.further") },
  ];
  const tools = [["zscores", "/bonds/zscores", "plus"], ["execution", "/bonds/execution", "plus"], ["carry", "/bonds/carry", "pro"]] as const;
  return (
    <>
      <PageHead eyebrow={t("bonds.eyebrow")} title={t("bonds.title")} lead={t("bonds.leadLong")}
                meta={fit ? <AsOf day={fit.obs_date} calendar="lk_bond_market" /> : null} parts={parts} />
      <Brief title={t("ui.atAGlance")} lines={glance} />
      <Section id="curve" open title={t("bonds.sections.curve")}
               summary={y1 != null && y5 != null && y10 != null ? t("bonds.sections.curveSum", { y1: percent(y1, 2), y5: percent(y5, 2), y10: percent(y10, 2) }) : undefined}
               why={t("bonds.sections.curveWhy")} how={<p>{t("bonds.sections.curveHow")}</p>}
               related={[{ href: "/learn/yield-curve", label: t("bonds.guideCurve") }, { href: "/learn/bonds-basics", label: t("bonds.guideBonds") }]}>
        {!curve.access.allowed ? (
          <Locked access={curve.access} />
        ) : fit ? (
          <>
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
      </Section>

      <Section id="table" title={t("bonds.sections.table")} open={query !== "" || bandParam !== ""}
               summary={quotes.access.allowed ? t("bonds.sections.tableSum", { n: rows.length }) : undefined}
               why={t("bonds.sections.tableWhy")} how={<p>{t("bonds.sections.tableHow")}</p>}
               related={[{ href: "/learn/bond-relative-value", label: t("bonds.guideRv") }]}>
      {!quotes.access.allowed ? (
          <Locked access={quotes.access} />
        ) : (
          <>
            <FilterBar scope="bond-table" action="/bonds#table" placeholder={t("bonds.searchPlaceholder")} query={query}
                       selects={[{ name: "band", label: t("bonds.band"), all: t("bonds.allBands"), value: bandParam,
                                   options: BANDS.map(([b]) => ({ value: b, label: t(`bonds.bands.${b}`) })) }]}
                       shown={rows.filter((q) => showRow(q.isin)).length} total={rows.length} />
            <p className="small muted">{t("bonds.tableNote")}</p>
            <div className="table-wrap" id="bond-table">
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
                      <tr key={q.isin} data-search={textOf(q.isin)} data-band={bandOf(q.isin)} hidden={!showRow(q.isin)}>
                        <td>
                          <Link href={bondHref(q.isin)}>{bondName(q.isin, ref.data)}</Link>
                        </td>
                        <td>{date(ref.data?.get(q.isin)?.maturity_date)}</td>
                        <td className="num">{percent(q.bid_yield, 3)}</td>
                        <td className="num">{percent(q.offer_yield, 3)}</td>
                        <td className="num">{q.mid_yield == null ? <span className="small muted">{t("bonds.oneWay")}</span> : percent(q.mid_yield, 3)}</td>
                        <td className="num">
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

      </Section>

      <section id="further">
        <div className="section-head">
          <h2>{t("bonds.sections.further")}</h2>
        </div>
        <p className="muted" style={{ marginTop: -4 }}>{t("bonds.sections.furtherLead")}</p>
        <div className="tier-strip">
          {tools.map(([key, href, tier]) => (
            <div key={key}>
              <span className={`tier-pill ${tier}`} style={{ justifySelf: "start" }}>{t(`tiers.${tier}`)}</span>
              <Link href={href} className="display" style={{ fontSize: "1.1rem", fontWeight: 600 }}>{t(`menu.bonds.${key}.title`)}</Link>
              <p>{t(`bonds.tools.${key}`)}</p>
            </div>
          ))}
        </div>
      </section>
      <ModelFooter models={["bond_ns_curve", "bond_identity", "bond_liquidity"]} />
    </>
  );
}
