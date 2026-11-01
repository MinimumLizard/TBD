import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";

import AsOf from "@/components/AsOf";
import Chart from "@/components/Chart";
import CompanyFigures from "@/components/CompanyFigures";
import CompanyOwnership from "@/components/CompanyOwnership";
import Locked from "@/components/Locked";
import ModelFooter from "@/components/ModelFooter";
import Brief from "@/components/Brief";
import DirectorsDealings from "@/components/DirectorsDealings";
import PageHead from "@/components/PageHead";
import Section from "@/components/Section";
import { lineOption } from "@/lib/charts";
import StatTile from "@/components/StatTile";
import Term from "@/components/Term";
import { actionAmount, companyName } from "@/lib/cse-display";
import {
  type TotalReturnSession, companyFigures, companyOwnership, corporateActions, securityNames, shareHistory, totalReturns,
} from "@/lib/data/cse";
import { companyDealings } from "@/lib/data/dealings";
import { NONE, date, int, lkr, num, pct, percent, ratio, tone } from "@/lib/format";
import { decodeSegment } from "@/lib/params";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";

export async function generateMetadata({ params }: { params: Promise<{ symbol: string }> }) {
  return { title: decodeSegment((await params).symbol) };
}

export default async function SharePage({ params }: { params: Promise<{ symbol: string }> }) {
  const symbol = decodeSegment((await params).symbol);
  const [t, viewer] = await Promise.all([getTranslations(), getViewer()]);
  const code = symbol.split(".")[0];
  const [history, names, actions, returns, figures, owners, dealings] = await Promise.all([
    shareHistory(viewer, symbol), securityNames(viewer), corporateActions(viewer, symbol), totalReturns(viewer, symbol),
    companyFigures(viewer, code), companyOwnership(viewer, code), companyDealings(viewer, symbol),
  ]);
  const ref = names.data?.get(symbol);
  if (!history.access.allowed) {
    return (
      <>
        <h1>{symbol}</h1>
        <Locked access={history.access} />
      </>
    );
  }
  const rows = history.data ?? [];
  const last = rows[rows.length - 1];
  if (!last) notFound();
  // Total returns are computed on the sessions a share traded in: the latest session's row, or the last trade's.
  const trRows = returns.data ?? [];
  const trLast: TotalReturnSession | undefined = trRows.filter((r) => r.session_date <= last.session_date).at(-1);
  const windows = [
    ["w1", last.ret_1w, last.rel_1w, last.flag_1w, trLast?.tr_1w],
    ["m1", last.ret_1m, last.rel_1m, last.flag_1m, trLast?.tr_1m],
    ["m3", last.ret_3m, last.rel_3m, last.flag_3m, trLast?.tr_3m],
  ] as const;
  const priceLine = rows.filter((r) => r.traded).map((r) => [r.session_date, r.close] as [string, number | null]);
  // The total-return line in rupees: the first close, grown by the total-return index (both lines start together).
  const trLine = trRows.map((r) => [r.session_date, Math.round(r.tri * trRows[0].close * 1e4) / 1e4] as [string, number | null]);
  // What the collapsed sections and "at a glance" say: facts from the same tier-checked results, in plain words.
  const f = figures.access.allowed ? figures.data : null;
  const o = owners.access.allowed ? owners.data : null;
  const top = o?.holders.find((h) => h.share_class === "N") ?? o?.holders[0] ?? null;
  const yearAgo = new Date(Date.parse(last.session_date) - 365 * 86400000).toISOString().slice(0, 10);
  const recentDealings = (dealings.data ?? []).filter((d) => d.deal_date && d.deal_date >= yearAgo);
  const actionRows = actions.data ?? [];
  const lastEx = actionRows.map((a) => a.ex_date).filter((d): d is string => !!d).sort().at(-1) ?? null;
  const loss = f?.ttm_eps != null && f.ttm_eps <= 0;
  const hasFigures = !!f && (f.nav != null || f.ttm_eps != null);
  const glance: string[] = [];
  glance.push(last.traded
    ? t("share.glance.close", { price: `Rs ${num(last.close)}`, date: date(last.session_date), change: pct(last.pct) })
    : t("share.glance.closeNoTrade", { price: `Rs ${num(last.close)}`, date: date(last.session_date) }));
  if (last.ret_3m != null && last.rel_3m != null) {
    glance.push(t(last.rel_3m >= 0 ? "share.glance.rel3mMore" : "share.glance.rel3mLess",
                  { ret: pct(last.ret_3m), gap: num(Math.abs(last.rel_3m) * 100, 1) }));
  }
  if (trLast?.tr_3m != null) glance.push(t("share.glance.tr3m", { tr: pct(trLast.tr_3m) }));
  if (hasFigures && f!.report_period) {
    glance.push(loss
      ? t("share.glance.figuresLoss", { pb: num(f!.pb, 2), date: date(f!.report_period) })
      : t("share.glance.figures", { pe: num(f!.pe, 1), pb: num(f!.pb, 2), dy: f!.dy == null ? NONE : percent(f!.dy * 100, 2), date: date(f!.report_period) }));
  }
  if (o?.top20_pct != null && top) glance.push(t("share.glance.owners", { top20: percent(o.top20_pct, 1), name: top.owner_name, pct: percent(top.pct, 2) }));
  if (dealings.access.allowed) {
    glance.push(recentDealings.length
      ? t("share.glance.dealings", { count: recentDealings.length, date: date(recentDealings[0].deal_date) })
      : t("share.glance.dealingsNone"));
  }
  const parts = [
    { id: "price", label: t("share.sections.price") },
    { id: "figures", label: t("share.sections.figures") },
    { id: "owners", label: t("share.sections.owners") },
    { id: "actions", label: t("share.sections.actions") },
    { id: "dealings", label: t("share.sections.dealings") },
  ];
  return (
    <>
      <PageHead
        eyebrow={ref?.sector_label ? t("share.eyebrow", { sector: ref.sector_label }) : t("share.eyebrowNoSector")}
        title={companyName(ref?.name) ?? symbol}
        lead={t("share.leadLine", { symbol })}
        meta={<AsOf day={last.session_date} calendar="cse" />}
        parts={parts}
      />
      <div className="tiles">
        <StatTile label={t("share.latest")} value={num(last.close)} change={last.traded ? last.pct : null}
                  note={last.traded ? null : t("common.notTraded")}
                  spark={rows.filter((r) => r.traded).slice(-120).map((r) => r.close)} />
        <div className="tile stat">
          <span className="label"><Term id="range52">{t("share.range52")}</Term></span>
          <span className="value">
            {num(last.low_52w)} – {num(last.high_52w)}
          </span>
          {last.range_pos != null && (
            <>
              <div className="breadth" aria-hidden="true"><span className="b-up" style={{ width: `${Math.max(0, Math.min(1, last.range_pos)) * 100}%`, opacity: 0.55 }} /></div>
              <span className="sub">{`${num(last.range_pos * 100, 0)}%`}</span>
            </>
          )}
        </div>
        <div className="tile stat">
          <span className="label"><Term id="marketCap">{t("share.marketCap")}</Term></span>
          <span className="value">{lkr(last.market_cap)}</span>
          <span className="sub">
            <Term id="beta">{t("share.beta")}</Term>: {num(last.beta)}
          </span>
        </div>
      </div>
      <div style={{ marginTop: 16 }}>
        <Brief title={t("ui.atAGlance")} lines={glance} />
      </div>

      <Section id="price" open title={t("share.sections.price")}
               summary={trLast?.tr_3m != null ? t("share.sections.priceSum", { ret3m: pct(last.ret_3m), tr3m: pct(trLast.tr_3m) })
                 : t("share.sections.priceSumNoTr", { ret3m: pct(last.ret_3m) })}
               why={t("share.sections.priceWhy")} how={<p>{t("share.sections.priceHow")}</p>}
               related={[{ href: "/learn/total-return", label: t("share.guideReturns") }, { href: "/learn/shares-basics", label: t("share.guideShares") }]}>
        {trLine.length > 1 ? (
          <>
            <h3>{t("share.chart")}</h3>
            <Chart
              label={t("share.chart")}
              option={lineOption([{ name: t("share.priceSeries"), points: priceLine }, { name: t("share.totalReturnSeries"), points: trLine }])}
            />
            <p className="small muted">{t("share.chartNote", { date: date(trRows[0].session_date) })}</p>
          </>
        ) : (
          <>
            <h3>{t("share.priceChart")}</h3>
            <Chart label={t("share.priceChart")} option={lineOption([{ name: symbol, points: priceLine }], undefined, { area: true })} />
          </>
        )}
        {!returns.access.allowed && <Locked access={returns.access} />}
        <h3>{t("share.returns")}</h3>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{t("share.window")}</th>
                <th className="num">{t("share.price")}</th>
                <th className="num"><Term id="relative">{t("share.relative")}</Term></th>
                {returns.access.allowed && <th className="num"><Term id="totalReturn">{t("share.totalReturn")}</Term></th>}
                <th>{t("shares.flag")}</th>
              </tr>
            </thead>
            <tbody>
              {windows.map(([key, ret, rel, flag, total]) => (
                <tr key={key}>
                  <td>{t(`share.${key}`)}</td>
                  <td className={`num ${tone(ret)}`}>{pct(ret)}</td>
                  <td className={`num ${tone(rel)}`}>{pct(rel)}</td>
                  {returns.access.allowed && <td className={`num ${tone(total)}`}>{pct(total)}</td>}
                  <td className="small">{flag ? (flag.startsWith("unadjusted") ? t("shares.flagJump") : t("shares.flagNoTrade")) : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {trLast && trLast.session_date !== last.session_date && (
          <p className="small muted">{t("share.totalReturnAsOf", { date: date(trLast.session_date) })}</p>
        )}
        <dl className="facts" style={{ marginTop: 16 }}>
          <dt>{t("share.volume")}</dt>
          <dd>{int(last.volume)}</dd>
          <dt>{t("share.volAverage")}</dt>
          <dd>
            {int(last.vol_avg20)} ({ratio(last.vol_ratio)})
          </dd>
        </dl>
        {last.range_flag && <div className="notice warn">{t("shares.flagRange")}</div>}
      </Section>

      <Section id="figures" title={t("share.sections.figures")}
               summary={hasFigures && !loss ? t("share.sections.figuresSum", { pe: num(f!.pe, 1), pb: num(f!.pb, 2), roe: f!.roe == null ? NONE : percent(f!.roe * 100, 1), dy: f!.dy == null ? NONE : percent(f!.dy * 100, 2) })
                 : t("share.sections.figuresSumNone")}
               why={t("share.sections.figuresWhy")} how={<p>{t("share.sections.figuresHow")}</p>}
               related={[{ href: "/learn/company-figures", label: t("share.guideFigures") }]}>
        <CompanyFigures result={figures} symbol={symbol} />
      </Section>

      <Section id="owners" title={t("share.sections.owners")}
               summary={o?.top20_pct != null ? t("share.sections.ownersSum", { top20: percent(o.top20_pct, 1), ff: percent(o.free_float_pct, 1) }) : t("share.sections.ownersSumNone")}
               why={t("share.sections.ownersWhy")} how={<p>{t("share.sections.ownersHow")}</p>}
               related={[{ href: "/learn/ownership", label: t("share.guideOwners") }]}>
        <CompanyOwnership result={owners} />
      </Section>

      <Section id="actions" title={t("share.sections.actions")}
               summary={actionRows.length && lastEx ? t("share.sections.actionsSum", { count: actionRows.length, date: date(lastEx) }) : t("share.sections.actionsSumNone")}
               why={t("share.sections.actionsWhy")} how={<p>{t("share.sections.actionsHow")}</p>}
               related={[{ href: "/learn/total-return", label: t("share.guideReturns") }]}>
        {!actions.access.allowed ? (
          <Locked access={actions.access} />
        ) : actionRows.length === 0 ? (
          <p className="muted">{t("share.noActions")}</p>
        ) : (
          <>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th><Term id="exDate">{t("share.exDate")}</Term></th>
                    <th>{t("share.type")}</th>
                    <th>{t("share.amount")}</th>
                    <th>{t("share.status")}</th>
                    <th>{t("share.source")}</th>
                  </tr>
                </thead>
                <tbody>
                  {actionRows.map((a) => {
                    const amount = actionAmount(a);
                    return (
                      <tr key={a.action_id}>
                        <td>{a.ex_date ? date(a.ex_date) : t("share.notYetKnown")}</td>
                        <td>{t(`share.types.${a.action_type}` as never)}</td>
                        <td>{amount ? t(`share.amounts.${amount.key}` as never, amount.values as never) : NONE}</td>
                        <td>{a.confirmed ? t("share.confirmed") : <span className="muted">{t("share.awaiting")}</span>}</td>
                        <td>{a.source_url ? <a href={a.source_url} rel="noopener noreferrer">{t("share.pdf")}</a> : NONE}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="small muted">{t("share.actionsNote")}</p>
          </>
        )}
      </Section>

      <Section id="dealings" title={t("share.sections.dealings")}
               summary={!dealings.access.allowed ? undefined : (dealings.data ?? []).length ? t("share.sections.dealingsSum", { count: (dealings.data ?? []).length, date: date((dealings.data ?? [])[0].deal_date) }) : t("share.sections.dealingsSumNone")}
               why={t("share.sections.dealingsWhy")} how={<p>{t("share.sections.dealingsHow")}</p>}
               related={[{ href: "/learn/directors-dealings", label: t("share.guideDealings") }]}>
        <DirectorsDealings result={dealings} />
      </Section>
      <ModelFooter models={["cse_security_metrics", ...(actions.access.allowed ? ["cse_corporate_actions" as const] : []),
                            ...(returns.access.allowed ? ["cse_total_returns" as const] : []),
                            ...(figures.access.allowed ? ["cse_fundamentals" as const] : []),
                            ...(owners.access.allowed ? ["cse_ownership" as const] : [])]} />
    </>
  );
}
