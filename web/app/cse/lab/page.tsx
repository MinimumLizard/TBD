import Link from "next/link";
import { getTranslations } from "next-intl/server";

import Chart from "@/components/Chart";
import Donut, { type Slice } from "@/components/Donut";
import Locked from "@/components/Locked";
import ModelFooter from "@/components/ModelFooter";
import PageHead from "@/components/PageHead";
import Section from "@/components/Section";
import StatTile from "@/components/StatTile";
import { lineOption } from "@/lib/charts";
import { companyName } from "@/lib/cse-display";
import { securityNames } from "@/lib/data/cse";
import { type LabSummary, lab } from "@/lib/data/lab";
import { FLAGSHIP, SCHEDULES } from "@/lib/lab-display";
import { date, monthYear, pct, percent, rupees } from "@/lib/format";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";

const SHOWN = 5; // slices before "other"

export async function generateMetadata() {
  const t = await getTranslations();
  return { title: t("lab.title") };
}

/** The first day of the next review month (January or July) after d. */
function nextReview(d: string): string {
  const [y, m] = [Number(d.slice(0, 4)), Number(d.slice(5, 7))];
  return m < 7 ? `${y}-07-01` : `${y + 1}-01-01`;
}

function slices(parts: [string, number][], other: string): Slice[] {
  const sorted = [...parts].sort((a, b) => b[1] - a[1]);
  const top = sorted.slice(0, SHOWN).map(([label, value]) => ({ label, value }));
  const rest = sorted.slice(SHOWN).reduce((s, [, v]) => s + v, 0);
  return rest > 0.0005 ? [...top, { label: other, value: rest }] : top;
}

const indexed = (rows: { session_date: string; nav: number }[]): [string, number][] =>
  rows.length ? rows.map((r) => [r.session_date, (r.nav / rows[0].nav) * 100]) : [];

// The portfolio lab (Pro, decision 0027): a worked example of a portfolio built by written rules. Shown as education: what
// the rules chose, what they would have done, how the portfolio is kept in shape. It never says what anyone should do.
export default async function LabPage() {
  const [t, viewer] = await Promise.all([getTranslations(), getViewer()]);
  const [result, names] = await Promise.all([lab(viewer), securityNames(viewer)]);
  const head = <PageHead eyebrow={<>{t("lab.eyebrow")} · <span className="tier-pill pro">{t("tiers.pro")}</span></>}
                         title={t("lab.title")} lead={t("lab.lead")} />;
  if (!result.access.allowed) {
    return (
      <>
        {head}
        <Locked access={result.access} />
      </>
    );
  }
  const d = result.data!;
  const nameOf = (s: string) => companyName(names.data?.get(s)?.name) ?? s.replace(".N0000", "");
  const code = (s: string) => s.replace(/\.N0000$/, "");
  const by = new Map<string, LabSummary>(d.summaries.map((r) => [`${r.policy}/${r.portfolio}`, r]));
  const flag = by.get(`${FLAGSHIP.policy}/${FLAGSHIP.portfolio}`);
  const market = by.get(`${FLAGSHIP.policy}/market`);
  const bills = by.get(`${FLAGSHIP.policy}/bills`);
  if (!flag || d.holdings.length === 0) {
    return (<>{head}<p className="muted">{t("lab.notYet")}</p></>);
  }
  const sectors = new Map<string, number>();
  for (const h of d.holdings) sectors.set(h.sector ?? "–", (sectors.get(h.sector ?? "–") ?? 0) + h.weight);
  const other = t("lab.other");
  const series = (p: string) => indexed(d.nav.filter((r) => r.portfolio === p));
  const chart = lineOption([
    { name: t("lab.example"), points: series(FLAGSHIP.portfolio) },
    { name: t("lab.market"), points: series("market") },
    { name: t("lab.bills"), points: series("bills") },
  ]);
  const reviews = d.events.filter((e) => e.kind !== "drift");
  const totalCost = d.events.reduce((s, e) => s + e.cost, 0);
  return (
    <>
      {head}
      <div className="tiles">
        <StatTile label={t("lab.tiles.return")} value={pct(flag.total_return, 1)}
                  note={t("lab.tiles.vs", { market: pct(market?.total_return, 1), bills: pct(bills?.total_return, 1) })} />
        <StatTile label={t("lab.tiles.swings")} value={percent((flag.volatility ?? 0) * 100, 1)}
                  note={t("lab.tiles.marketSwings", { value: percent((market?.volatility ?? 0) * 100, 1) })} />
        <StatTile label={t("lab.tiles.fall")} value={pct(flag.max_drawdown, 1)}
                  note={t("lab.tiles.marketFall", { value: pct(market?.max_drawdown, 1) })} />
        <StatTile label={t("lab.tiles.next")} value={monthYear(nextReview(flag.end_date))}
                  note={t("lab.tiles.formed", { date: date(d.formedOn) })} />
      </div>

      <div className="donuts">
        <Donut label={t("lab.byShare")} centre={String(d.holdings.length)} centreSub={t("lab.shares")} other={other}
               slices={slices(d.holdings.map((h) => [`${nameOf(h.symbol)}`, h.weight]), other)} />
        <Donut label={t("lab.bySector")} centre={String(sectors.size)} centreSub={t("lab.sectors")} other={other}
               slices={slices([...sectors.entries()], other)} />
      </div>

      <Section id="record" open title={t("lab.recordTitle")}
               summary={t("lab.recordSum", { from: date(flag.start_date), to: date(flag.end_date) })}>
        <Chart option={chart} label={t("lab.recordTitle")} height={280} />
        <p className="small muted">{t("lab.recordNote")}</p>
      </Section>

      <Section id="rebalancing" open title={t("lab.keptTitle")} summary={t("lab.keptSum")}>
        <ol className="steps compact">
          {(t.raw("lab.kept") as string[]).map((x) => <li key={x}>{x}</li>)}
        </ol>
        <div className="table-wrap">
          <table>
            <thead><tr><th>{t("lab.cols.schedule")}</th><th className="num">{t("lab.cols.return")}</th>
              <th className="num">{t("lab.cols.swings")}</th><th className="num">{t("lab.cols.costs")}</th></tr></thead>
            <tbody>
              {SCHEDULES.map((p) => {
                const r = by.get(`${p}/${FLAGSHIP.portfolio}`);
                if (!r) return null;
                return (
                  <tr key={p} className={p === FLAGSHIP.policy ? "is-current" : undefined}>
                    <td>{t(`lab.schedules.${p}` as never)}</td>
                    <td className="num">{pct(r.total_return, 1)}</td>
                    <td className="num">{percent((r.volatility ?? 0) * 100, 1)}</td>
                    <td className="num">{rupees(r.costs)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="small muted">{t("lab.keptNote", { reviews: reviews.length, cost: rupees(totalCost) })}</p>
      </Section>

      <Section id="holdings" title={t("lab.holdingsTitle", { count: d.holdings.length })}
               summary={t("lab.holdingsSum", { top: nameOf(d.holdings[0].symbol), weight: percent(d.holdings[0].weight * 100, 1) })}>
        <div className="table-wrap">
          <table>
            <thead><tr><th>{t("lab.cols.share")}</th><th>{t("lab.cols.sector")}</th><th className="num">{t("lab.cols.weight")}</th></tr></thead>
            <tbody>
              {d.holdings.map((h) => (
                <tr key={h.symbol}>
                  <td><Link href={`/cse/shares/${encodeURIComponent(h.symbol)}`}>{code(h.symbol)}</Link>
                    <span className="sub">{nameOf(h.symbol)}</span></td>
                  <td className="wrap">{h.sector ?? "–"}</td>
                  <td className="num">{percent(h.weight * 100, 1)}{h.at_cap && <span className="sub">{t("lab.atCap")}</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <Section id="rules" title={t("lab.rulesTitle")} summary={t("lab.rulesSum")}>
        <ol className="steps compact">
          {(t.raw("lab.rules") as string[]).map((x) => <li key={x}>{x}</li>)}
        </ol>
      </Section>

      <p className="small muted">{t("lab.note")}</p>
      <ModelFooter models={["cse_lab_backtest"]} />
    </>
  );
}
