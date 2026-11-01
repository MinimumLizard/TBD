import Link from "next/link";
import { getTranslations } from "next-intl/server";

import AsOf from "@/components/AsOf";
import Brief from "@/components/Brief";
import PageHead from "@/components/PageHead";
import Section from "@/components/Section";
import BreadthBar from "@/components/BreadthBar";
import Chart from "@/components/Chart";
import Locked from "@/components/Locked";
import ModelFooter from "@/components/ModelFooter";
import { lineOption } from "@/lib/charts";
import { MOVERS_MIN_TURNOVER, isHeadline } from "@/lib/cse-display";
import Term from "@/components/Term";
import { companyName } from "@/lib/cse-display";
import { type IndexSession, type ShareSession, indexHistory, marketTape, securityNames, shares } from "@/lib/data/cse";
import { int, lkr, num, pct, percent, ratio, signed, tone } from "@/lib/format";
import { marketSummary } from "@/lib/summary";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";

export async function generateMetadata() {
  const t = await getTranslations();
  return { title: t("cse.title") };
}

export default async function CsePage() {
  const [t, viewer] = await Promise.all([getTranslations(), getViewer()]);
  const [tape, aspi, all, names] = await Promise.all([marketTape(viewer), indexHistory(viewer, "ASI"), shares(viewer), securityNames(viewer)]);

  const indexRows = (rows: IndexSession[]) => (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>{t("cse.index")}</th>
            <th className="num">{t("cse.level")}</th>
            <th className="num">{t("cse.change")}</th>
            <th className="num">{t("cse.changePct")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.index_code}>
              <td>{t.has(`cse.indexNames.${r.index_code}` as never) ? t(`cse.indexNames.${r.index_code}` as never) : r.index_code}</td>
              <td className="num">{num(r.value)}</td>
              <td className={`num ${tone(r.change)}`}>{signed(r.change)}</td>
              <td className={`num ${tone(r.pct)}`}>{pct(r.pct)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  const shareRows = (rows: ShareSession[]) => (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>{t("shares.symbol")}</th>
            <th className="num">{t("shares.close")}</th>
            <th className="num">{t("shares.changePct")}</th>
            <th className="num">{t("shares.turnover")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.symbol}>
              <td>
                <Link href={`/cse/shares/${encodeURIComponent(r.symbol)}`}>{r.symbol}</Link>
                <span className="sub">{companyName(names.data?.get(r.symbol)?.name)}</span>
              </td>
              <td className="num">{num(r.close)}</td>
              <td className="num"><span className={`chip ${tone(r.pct)}`}>{pct(r.pct)}</span></td>
              <td className="num">{lkr(r.turnover)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  const s = tape.data?.session ?? null;
  const vsAvg = (value: number | null, avg: number | null) =>
    value != null && avg ? t("cse.vsAverage", { ratio: ratio(value / avg) }) : s?.sessions_needed ? t("cse.averagePending", { count: s.sessions_needed }) : "";
  const traded = (all.data?.rows ?? []).filter((r) => r.traded);
  // A session filled in from the price history has no turnover; ranking by it would only list shares alphabetically.
  const withTurnover = traded.filter((r) => r.turnover != null);
  const liquid = traded.filter((r) => (r.turnover ?? 0) >= MOVERS_MIN_TURNOVER && r.pct != null);

  const indices = tape.data?.indices ?? [];
  const idx = (code: string) => indices.find((i) => i.index_code === code) ?? null;
  const aspiNow = idx("ASI");
  const spNow = idx("S&P SL20");
  const sectors = indices.filter((r) => !isHeadline(r.index_code));
  const topTraded = [...withTurnover].sort((a, b) => (b.turnover ?? 0) - (a.turnover ?? 0));
  const summary = marketSummary({
    aspi: aspiNow ? { value: aspiNow.value, pct: aspiNow.pct } : null,
    breadth: s ? { up: s.equities_up ?? 0, down: s.equities_down ?? 0, flat: s.equities_flat ?? 0 } : null,
    turnover: s ? { value: s.turnover, avg20: s.turnover_avg20 } : null,
    foreignNet: s?.foreign_net ?? null,
    curve: null,
  });
  const parts = [
    { id: "indices", label: t("cse.sections.indices") },
    { id: "activity", label: t("cse.sections.activity") },
    { id: "breadth", label: t("cse.sections.breadth") },
    { id: "valuation", label: t("cse.sections.valuation") },
    { id: "movers", label: t("cse.sections.movers") },
    { id: "sectors", label: t("cse.sections.sectors") },
  ];
  const guides = [{ href: "/learn/shares-basics", label: t("cse.guideShares") }, { href: "/learn/markets-map", label: t("cse.guideMap") }];

  return (
    <>
      <PageHead eyebrow={t("cse.eyebrow")} title={t("cse.title")} lead={t("cse.leadLong")}
                meta={tape.access.allowed ? <AsOf day={s?.session_date ?? null} calendar="cse" /> : null}
                parts={tape.access.allowed ? parts : undefined} />
      {!tape.access.allowed ? (
        <Locked access={tape.access} />
      ) : (
        <>
          <Brief title={t("ui.atAGlance")} lines={summary.map((line) => t(line.key as never, line.values as never))} />
          <Section id="indices" open title={t("cse.sections.indices")}
                   summary={aspiNow && spNow ? t("cse.sections.indicesSum", { aspi: num(aspiNow.value), aspiPct: pct(aspiNow.pct), sp: num(spNow.value), spPct: pct(spNow.pct) }) : undefined}
                   why={t("cse.sections.indicesWhy")} how={<p>{t("cse.sections.indicesHow")}</p>} related={guides}>
            {indexRows(indices.filter((r) => isHeadline(r.index_code)))}
            {aspi.data && aspi.data.length > 1 && (
              <Chart label={t("cse.aspiChart")} option={lineOption([{ name: "ASPI", points: aspi.data.map((r) => [r.session_date, r.value]) }], undefined, { area: true })} />
            )}
          </Section>
          {s && (
            <>
              <Section id="activity" title={t("cse.sections.activity")}
                       summary={t("cse.sections.activitySum", { turnover: lkr(s.turnover), trades: int(s.trades) })}
                       why={t("cse.sections.activityWhy")} how={<p>{t("cse.sections.activityHow")}</p>}>
                <div className="tiles">
                  <div className="tile stat">
                    <span className="label"><Term id="turnover">{t("cse.turnover")}</Term></span>
                    <span className="value">{lkr(s.turnover)}</span>
                    <span className="muted small">{vsAvg(s.turnover, s.turnover_avg20)}</span>
                  </div>
                  <div className="tile stat">
                    <span className="label">{t("cse.volume")}</span>
                    <span className="value">{int(s.volume)}</span>
                    <span className="muted small">{vsAvg(s.volume, s.volume_avg20)}</span>
                  </div>
                  <div className="tile stat">
                    <span className="label">{t("cse.trades")}</span>
                    <span className="value">{int(s.trades)}</span>
                    <span className="muted small">{vsAvg(s.trades, s.trades_avg20)}</span>
                  </div>
                </div>
              </Section>
              <Section id="breadth" title={t("cse.sections.breadth")}
                       summary={t("cse.sections.breadthSum", { up: s.equities_up ?? 0, down: s.equities_down ?? 0, net: lkr(s.foreign_net) })}
                       why={t("cse.sections.breadthWhy")} how={<p>{t("cse.sections.breadthHow")}</p>}>
                <div className="grid two">
                  <div>
                    <h3><Term id="breadth">{t("cse.breadth")}</Term></h3>
                    <BreadthBar up={s.equities_up} flat={s.equities_flat} down={s.equities_down}
                                labels={{ up: t("cse.rose"), flat: t("cse.unchanged"), down: t("cse.fell") }} />
                    <p className="small muted">{t("cse.breadthNote")}</p>
                    {s.listed != null && s.traded_all != null && (
                      <p className="small muted">{t("cse.listedTraded", { traded: s.traded_all, listed: s.listed })}</p>
                    )}
                  </div>
                  <div>
                    <h3><Term id="foreign">{t("cse.foreign")}</Term></h3>
                    <dl className="facts">
                      <dt>{t("cse.foreignPurchases")}</dt>
                      <dd>{lkr(s.foreign_buy)}</dd>
                      <dt>{t("cse.foreignSales")}</dt>
                      <dd>{lkr(s.foreign_sell)}</dd>
                      <dt>{t("cse.foreignNet")}</dt>
                      <dd className={tone(s.foreign_net)}>{lkr(s.foreign_net)}</dd>
                    </dl>
                  </div>
                </div>
              </Section>
              <Section id="valuation" title={t("cse.sections.valuation")}
                       summary={t("cse.sections.valuationSum", { per: num(s.per, 1), pbv: num(s.pbv, 1), dy: percent(s.dy, 1) })}
                       why={t("cse.sections.valuationWhy")} how={<p>{t("cse.sections.valuationHow")}</p>}
                       related={[{ href: "/learn/company-figures", label: t("share.guideFigures") }]}>
                <dl className="facts">
                  <dt><Term id="pe">{t("cse.per")}</Term></dt>
                  <dd>{num(s.per, 1)}</dd>
                  <dt><Term id="pbv">{t("cse.pbv")}</Term></dt>
                  <dd>{num(s.pbv, 1)}</dd>
                  <dt><Term id="dividendYield">{t("cse.dy")}</Term></dt>
                  <dd>{percent(s.dy, 1)}</dd>
                  <dt><Term id="marketCap">{t("cse.marketCap")}</Term></dt>
                  <dd>{lkr(s.market_cap)}</dd>
                </dl>
              </Section>
            </>
          )}
        </>
      )}
      {!all.access.allowed ? (
        <Locked access={all.access} />
      ) : (
        <Section id="movers" title={t("cse.sections.movers")}
                 summary={topTraded.length ? t("cse.sections.moversSum", { symbol: companyName(names.data?.get(topTraded[0].symbol)?.name) ?? topTraded[0].symbol }) : undefined}
                 why={t("cse.sections.moversWhy")} how={<p>{t("cse.sections.moversHow")}</p>}>
          {withTurnover.length === 0 ? (
            <p className="muted">{t("cse.noTurnover")}</p>
          ) : (
            <>
              <h3>{t("cse.topTurnover")}</h3>
              {shareRows(topTraded.slice(0, 10))}
              <div className="grid two">
                <section>
                  <h3>{t("cse.largestRises")}</h3>
                  {shareRows(liquid.filter((r) => (r.pct ?? 0) > 0).sort((a, b) => (b.pct ?? 0) - (a.pct ?? 0)).slice(0, 10))}
                </section>
                <section>
                  <h3>{t("cse.largestFalls")}</h3>
                  {shareRows(liquid.filter((r) => (r.pct ?? 0) < 0).sort((a, b) => (a.pct ?? 0) - (b.pct ?? 0)).slice(0, 10))}
                </section>
              </div>
              <p className="small muted">{t("cse.moversNote")}</p>
            </>
          )}
        </Section>
      )}
      {tape.access.allowed && (
        <Section id="sectors" title={t("cse.sections.sectors")}
                 summary={t("cse.sections.sectorsSum", { count: sectors.length, up: sectors.filter((r) => (r.pct ?? 0) > 0).length, down: sectors.filter((r) => (r.pct ?? 0) < 0).length })}
                 why={t("cse.sections.sectorsWhy")} how={<p>{t("cse.sections.sectorsHow")}</p>}>
          {indexRows(sectors)}
        </Section>
      )}
      <p><Link href="/cse/dealings">{t("dealings.linkAll")} →</Link></p>
      <ModelFooter models={["cse_market_tape", "cse_security_metrics"]} />
    </>
  );
}
