import Link from "next/link";
import { getTranslations } from "next-intl/server";

import Chart from "@/components/Chart";
import Locked from "@/components/Locked";
import ModelFooter from "@/components/ModelFooter";
import StatTile from "@/components/StatTile";
import Term from "@/components/Term";
import { lineOption } from "@/lib/charts";
import { type Basis, type Instrument, type SavingsGrowth, type SavingsSummary, savingsGrowth, savingsOverview } from "@/lib/data/savings";
import { NONE, monthYear, pct, percent, rupees } from "@/lib/format";
import { MAX_AMOUNT, YEARS, addMonths, readCalc } from "@/lib/savings-calc";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";

export async function generateMetadata() {
  const t = await getTranslations();
  return { title: t("savings.title") };
}

const HORIZONS = [1, 3, 5, 10];
const START = 100_000;
const MONTHS = Array.from({ length: 12 }, (_, i) =>
  new Intl.DateTimeFormat("en", { month: "long", timeZone: "UTC" }).format(new Date(Date.UTC(2000, i, 1))),
);

// Education page (docs/plan-retail-features.md §4): what Rs 100,000 grew to in a fixed deposit and in treasury bills,
// before and after tax and inflation. Everything is rendered on the server, the calculator included (a GET form).
export default async function SavingsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = await searchParams;
  const [t, viewer] = await Promise.all([getTranslations(), getViewer()]);
  const overview = await savingsOverview(viewer);

  if (!overview.access.allowed || !overview.data) {
    return (
      <>
        <h1>{t("savings.title")}</h1>
        <p className="lead">{t("savings.lead")}</p>
        {!overview.access.allowed ? <Locked access={overview.access} /> : <p>{t("common.noData")}</p>}
        <ModelFooter models={["lk_savings_compare"]} />
      </>
    );
  }
  const { rates, through, summary, path, pathStart } = overview.data;
  const latest = rates.find((r) => r.month === through) ?? null;
  const first = summary.length ? summary.map((s) => s.first_start).sort()[0] : (rates[0]?.month ?? null);

  // The calculator reads its own query string; a period that ends after the data is explained, not guessed.
  const calc = through && first ? readCalc(params, first, through) : null;
  const calcEnd = calc ? addMonths(calc.start, 12 * calc.years) : null;
  const calcRows = calc && calcEnd && calc.start >= first! && calcEnd <= through!
    ? (await savingsGrowth(viewer, calc.start, calc.years)).data ?? []
    : [];
  const pick = (rows: SavingsGrowth[], instrument: Instrument, basis: Basis) => rows.find((r) => r.instrument === instrument && r.basis === basis) ?? null;
  const sum = (h: number, instrument: Instrument, basis: Basis): SavingsSummary | null =>
    summary.find((s) => s.horizon_years === h && s.instrument === instrument && s.basis === basis) ?? null;
  const countOf = (n: number | null | undefined, total: number | null | undefined) =>
    n == null || total == null ? NONE : t("savings.countOf", { count: n, total });

  const pathSeries = (basis: "nominal" | "real", fdBasis: Basis) => {
    const line = (instrument: Instrument, b: Basis) => [
      [pathStart!, START] as [string, number],
      ...path.filter((r) => r.instrument === instrument && r.basis === b).map((r) => [r.end_month, Math.round(r.value)] as [string, number]),
    ];
    return [
      { name: t("savings.seriesFd"), points: line("fd", basis) },
      { name: t("savings.seriesFdTax"), points: line("fd", fdBasis) },
      { name: t("savings.seriesBill"), points: line("tbill", basis) },
    ];
  };
  const pathEnd = path.length ? path.map((r) => r.end_month).sort().slice(-1)[0] : null;

  return (
    <>
      <h1>{t("savings.title")}</h1>
      <p className="lead">{t("savings.lead")}</p>
      {through && <p className="asof">{t("savings.latest", { month: monthYear(through) })}</p>}

      {latest && (
        <div className="tiles">
          <StatTile label={t("savings.fdRateTile")} value={percent(latest.fd_rate_pct, 2)} note={<>{t("savings.fdRateNote", { month: monthYear(latest.month) })} · <Term id="awfdr">{t("common.whatIsThis")}</Term></>} />
          <StatTile label={t("savings.billTile")} value={percent(latest.bill_rate_pct, 2)} note={<>{t("savings.billNote", { month: monthYear(latest.month) })} · <Term id="treasuryBill" /></>} />
          <StatTile label={t("savings.inflationTile")} value={pct(latest.inflation_yoy, 1).replace(/^\+/, "")} note={<>{t("savings.inflationNote", { month: monthYear(latest.month) })} · <Term id="inflation" /></>} />
          <StatTile label={t("savings.taxTile")} value={percent(latest.fd_tax_pct, 0)} note={t("savings.taxNote")} />
        </div>
      )}
      <p className="small muted" style={{ marginTop: 8 }}>{t("savings.sourcesBoth")}</p>

      <section className="card" style={{ marginTop: 24 }}>
        <h2>{t("savings.plainTitle")}</h2>
        <p><Term id="fixedDeposit" /> · <Term id="treasuryBill" /> · <Term id="inflation" /> · <Term id="realReturn" /></p>
        <p>{t("savings.plain1")}</p>
        <p>{t("savings.plain2")}</p>
        <p style={{ marginBottom: 0 }}>{t("savings.plain3")}</p>
      </section>

      {pathStart && pathEnd && (
        <>
          <div className="section-head">
            <h2>{t("savings.chartTitle")}</h2>
          </div>
          <p className="small muted">{t("savings.chartNote", { start: monthYear(pathStart), end: monthYear(pathEnd) })}</p>
          <div className="grid two">
            <section className="card">
              <h3>{t("savings.chartNominal")}</h3>
              <Chart label={t("savings.chartNominal")} height={280} option={lineOption(pathSeries("nominal", "nominal_after_tax"))} />
            </section>
            <section className="card">
              <h3>{t("savings.chartReal", { start: monthYear(pathStart) })}</h3>
              <Chart label={t("savings.chartReal", { start: monthYear(pathStart) })} height={280} option={lineOption(pathSeries("real", "real_after_tax"))} />
            </section>
          </div>
          <p className="small muted">{t("savings.sourcesBoth")}</p>
        </>
      )}

      {summary.length > 0 && first && (
        <>
          <div className="section-head">
            <h2>{t("savings.summaryTitle", { first: monthYear(first) })}</h2>
          </div>
          <p className="small muted">{t("savings.summaryNote")}</p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{t("savings.period")}</th>
                  <th className="num">{t("savings.periods")}</th>
                  <th className="num">{t("savings.fdAhead")}</th>
                  <th className="num">{t("savings.billAhead")}</th>
                  <th className="num">{t("savings.fdAboveInflation")}</th>
                  <th className="num">{t("savings.fdTaxAboveInflation")}</th>
                  <th className="num">{t("savings.billAboveInflation")}</th>
                </tr>
              </thead>
              <tbody>
                {HORIZONS.map((h) => {
                  const fd = sum(h, "fd", "nominal");
                  const bill = sum(h, "tbill", "nominal");
                  if (!fd || !bill) return null;
                  return (
                    <tr key={h}>
                      <td>{t("savings.years", { count: h })}</td>
                      <td className="num">{fd.n_periods}</td>
                      <td className="num">{countOf(fd.n_ahead, fd.n_periods)}</td>
                      <td className="num">{countOf(bill.n_ahead, bill.n_periods)}</td>
                      <td className="num">{countOf(sum(h, "fd", "real")?.n_above_start, fd.n_periods)}</td>
                      <td className="num">{countOf(sum(h, "fd", "real_after_tax")?.n_above_start, fd.n_periods)}</td>
                      <td className="num">{countOf(sum(h, "tbill", "real")?.n_above_start, bill.n_periods)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <h3 style={{ marginTop: 24 }}>{t("savings.rangeTitle")}</h3>
          <p className="small muted">{t("savings.rangeNote")} <Term id="realReturn" /></p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{t("savings.period")}</th>
                  <th>{t("savings.instrument")}</th>
                  <th className="num">{t("savings.worst")}</th>
                  <th className="num">{t("savings.median")}</th>
                  <th className="num">{t("savings.best")}</th>
                </tr>
              </thead>
              <tbody>
                {HORIZONS.flatMap((h) =>
                  ([["fd", "real", "seriesFd"], ["fd", "real_after_tax", "seriesFdTax"], ["tbill", "real", "seriesBill"]] as const).map(([instrument, basis, label]) => {
                    const s = sum(h, instrument, basis);
                    if (!s) return null;
                    return (
                      <tr key={`${h}-${instrument}-${basis}`}>
                        <td>{t("savings.years", { count: h })}</td>
                        <td>{t(`savings.${label}`)}</td>
                        <td className="num">{pct(s.worst_annual, 1)}<span className="sub">{t("savings.startedIn", { month: monthYear(s.worst_start) })}</span></td>
                        <td className="num">{pct(s.median_annual, 1)}</td>
                        <td className="num">{pct(s.best_annual, 1)}<span className="sub">{t("savings.startedIn", { month: monthYear(s.best_start) })}</span></td>
                      </tr>
                    );
                  }),
                )}
              </tbody>
            </table>
          </div>
          <p className="small muted">{t("savings.sourcesBoth")}</p>
        </>
      )}

      {calc && through && first && (
        <section className="card" id="calculator" style={{ marginTop: 24 }}>
          <h2>{t("savings.calcTitle")}</h2>
          <p className="muted">{t("savings.calcIntro")}</p>
          <form method="get" action="/learn/savings#calculator" className="calc-form">
            <label className="wide">
              {t("savings.amount")}
              <input type="number" name="amount" min={1} max={MAX_AMOUNT} step={1} inputMode="numeric" defaultValue={calc.amount} />
            </label>
            <label>
              {t("savings.startYear")}
              <select name="sy" defaultValue={calc.start.slice(0, 4)}>
                {Array.from({ length: Number(through.slice(0, 4)) - Number(first.slice(0, 4)) + 1 }, (_, i) => Number(first.slice(0, 4)) + i).map((y) => (
                  <option key={y} value={y}>{y}</option>
                ))}
              </select>
            </label>
            <label>
              {t("savings.startMonth")}
              <select name="sm" defaultValue={String(Number(calc.start.slice(5, 7)))}>
                {MONTHS.map((name, i) => (
                  <option key={name} value={i + 1}>{name}</option>
                ))}
              </select>
            </label>
            <label>
              {t("savings.calcYears")}
              <select name="years" defaultValue={String(calc.years)}>
                {YEARS.map((y) => (
                  <option key={y} value={y}>{y}</option>
                ))}
              </select>
            </label>
            <button type="submit">{t("savings.calcSubmit")}</button>
          </form>
          {calc.invalid && <div className="notice warn">{t("savings.calcInvalid")}</div>}
          {calc.start < first ? (
            <div className="notice warn">{t("savings.calcTooEarly", { month: monthYear(first) })}</div>
          ) : calcEnd! > through ? (
            <div className="notice warn">{t("savings.calcTooLate", { month: monthYear(through) })}</div>
          ) : calcRows.length ? (
            (() => {
              const k = calc.amount / START;
              const tile = (label: string, instrument: Instrument, basis: Basis, realBasis: Basis) => {
                const nominal = pick(calcRows, instrument, basis);
                const real = pick(calcRows, instrument, realBasis);
                return (
                  <StatTile label={label} value={rupees(nominal ? nominal.value * k : null)}
                            note={<>{t("savings.calcRate", { rate: pct(nominal?.annual_rate, 2) })}<br />{t("savings.calcReal", { value: rupees(real ? real.value * k : null) })}</>} />
                );
              };
              const fd = pick(calcRows, "fd", "nominal");
              return (
                <>
                  <p><strong>{t("savings.calcResult", { amount: rupees(calc.amount).replace(/^Rs /, ""), start: monthYear(calc.start), years: t("savings.years", { count: calc.years }), end: monthYear(calcEnd) })}</strong></p>
                  <div className="tiles">
                    {tile(t("savings.calcFd"), "fd", "nominal", "real")}
                    {tile(t("savings.calcFdTax"), "fd", "nominal_after_tax", "real_after_tax")}
                    {tile(t("savings.calcBill"), "tbill", "nominal", "real")}
                  </div>
                  {fd?.fd_series?.includes("AWFDR") && <p className="small muted" style={{ marginTop: 8 }}>{t("savings.calcAwfdr")}</p>}
                </>
              );
            })()
          ) : (
            <p>{t("common.noData")}</p>
          )}
          <p className="small muted" style={{ marginBottom: 0 }}>{t("savings.sourcesBoth")}</p>
        </section>
      )}

      {rates.length > 1 && (
        <>
          <div className="section-head">
            <h2>{t("savings.ratesTitle")}</h2>
          </div>
          <p className="small muted">{t("savings.ratesNote")}</p>
          <section className="card">
            <Chart
              label={t("savings.ratesTitle")}
              height={300}
              option={lineOption([
                { name: t("savings.seriesFdRate"), points: rates.map((r) => [r.month, r.fd_rate_pct]) },
                { name: t("savings.seriesBillRate"), points: rates.map((r) => [r.month, r.bill_rate_pct == null ? null : Math.round(r.bill_rate_pct * 100) / 100]) },
                { name: t("savings.seriesInflation"), points: rates.map((r) => [r.month, r.inflation_yoy == null ? null : Math.round(r.inflation_yoy * 1000) / 10]) },
              ], "%", { zeroLine: false })}
            />
            <p className="small muted" style={{ marginBottom: 0 }}>{t("savings.sourceCbsl")} · {t("savings.sourceDcs")}</p>
          </section>
        </>
      )}

      <section className="card" style={{ marginTop: 24 }}>
        <h2>{t("savings.assumptionsTitle")}</h2>
        <ul className="assumptions">
          {(["assume1", "assume2", "assume3", "assume4", "assume5", "assume6", "assume7"] as const).map((k) => (
            <li key={k}>{t(`savings.${k}`)}</li>
          ))}
        </ul>
        <p className="small" style={{ marginBottom: 0 }}>
          <Link href="/methods/lk_savings_compare">{t("common.method")} →</Link>
        </p>
      </section>

      <ModelFooter models={["lk_savings_compare"]} />
    </>
  );
}
