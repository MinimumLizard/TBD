import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { indexHistory, shares } from "@/lib/data/cse";
import { savingsOverview } from "@/lib/data/savings";
import type { Viewer } from "@/lib/entitlements";
import { int, monthYear, num, pct, rupees } from "@/lib/format";
import { AMOUNTS, type AmountKey, EXAMPLE_AMOUNT, HORIZONS, HORIZON_YEARS, type HorizonKey } from "@/lib/paths";

const COST_PER_SIDE = 0.0112; // the CSE's schedule for trades up to Rs 100 mn (docs/research/portfolio-lab-optimisation-2026-11.md §7.4)
const INSURED = 1_100_000; // Sri Lanka Deposit Insurance Scheme, per depositor and institution (savings.assume5)
const SPREAD = 10; // a worked example of spreading an amount over several shares

// "For your amount and timeframe" (questions 3 and 4 of the starting flow). Facts only: what trading costs at an amount
// like the visitor's, and how deposits and bills did over every past period as long as theirs. Nothing here suggests
// what to do (hard rule 4). Every variant is rendered, the visitor's shown and the rest hidden, so the page works
// without scripts and the static preview can show the visitor's own from the browser's storage.
export default async function YourMoney({ viewer, amount, horizon, more }: {
  viewer: Viewer;
  amount: AmountKey | null;
  horizon: HorizonKey | null;
  more: string; // the address of the two questions, to answer or change them
}) {
  const [t, savings, market, aspi] = await Promise.all([
    getTranslations(), savingsOverview(viewer), shares(viewer), indexHistory(viewer, "ASI"),
  ]);
  const closes = (market.data?.rows ?? []).filter((r) => r.traded && r.close && r.symbol.endsWith(".N0000")).map((r) => r.close!).sort((a, b) => a - b);
  const median = closes.length ? closes[Math.floor(closes.length / 2)] : null;
  const year = (aspi.data ?? []).slice(-250).map((r) => r.value);
  let fall: number | null = null;
  if (year.length > 1) {
    let peak = year[0];
    fall = 0;
    for (const v of year) {
      peak = Math.max(peak, v);
      fall = Math.min(fall, v / peak - 1);
    }
  }
  const summary = savings.data?.summary ?? [];
  const row = (years: number, instrument: string, basis: string) =>
    summary.find((r) => r.horizon_years === years && r.instrument === instrument && r.basis === basis);
  return (
    <section className="your-money" aria-labelledby="your-money-title">
      <div className="ym-head">
        <h2 id="your-money-title">{t("money.title")}</h2>
        <Link className="small" href={more}>{amount || horizon ? t("money.change") : t("money.answer")}</Link>
      </div>
      <div className="ym-empty">
        <p>{t("money.empty")}</p>
        <Link className="button" href={more}>{t("money.answer")} →</Link>
      </div>
      <div className="ym-grid">
        <div className="ym-card">
          <h3>{t("money.amountTitle")}</h3>
          <div data-amount="none" hidden={amount != null}>
            <p className="muted">{t("money.amountNone")}</p>
          </div>
          {AMOUNTS.map((a) => {
            const x = EXAMPLE_AMOUNT[a];
            const per = x / SPREAD;
            return (
              <div key={a} data-amount={a} hidden={amount !== a}>
                <p className="ym-label">{t(`start.amounts.${a}` as never)}</p>
                <ul>
                  <li>{t("money.cost", { amount: rupees(x), each: rupees(x * COST_PER_SIDE), both: rupees(2 * x * COST_PER_SIDE) })}</li>
                  {median && <li>{t("money.spread", { amount: rupees(x), count: SPREAD, per: rupees(per), price: rupees(median), shares: int(Math.floor(per / median)) })}</li>}
                  {x > INSURED && <li>{t("money.insured", { limit: rupees(INSURED) })}</li>}
                  {a === "gt10m" && <li>{t("money.large")}</li>}
                </ul>
                <p className="small"><Link href={`/learn/savings?amount=${x}#calculator`}>{t("money.calculator", { amount: rupees(x) })} →</Link></p>
              </div>
            );
          })}
        </div>
        <div className="ym-card">
          <h3>{t("money.horizonTitle")}</h3>
          <div data-horizon="none" hidden={horizon != null}>
            <p className="muted">{t("money.horizonNone")}</p>
          </div>
          {HORIZONS.map((h) => {
            const years = HORIZON_YEARS[h];
            const fd = row(years, "fd", "real_after_tax");
            const bill = row(years, "tbill", "real");
            return (
              <div key={h} data-horizon={h} hidden={horizon !== h}>
                <p className="ym-label">{t(`start.horizons.${h}` as never)}</p>
                <ul>
                  {fd && <li>{t("money.fd", { years, n: fd.n_above_start, total: fd.n_periods, first: monthYear(fd.first_start) })}</li>}
                  {bill && <li>{t("money.bill", { n: bill.n_above_start, total: bill.n_periods })}</li>}
                  {fd && bill && <li>{t("money.worst", { years, fd: pct(fd.worst_annual, 1), bill: pct(bill.worst_annual, 1) })}</li>}
                  {fall != null && <li>{t("money.shares", { fall: `${num(Math.abs(fall) * 100, 1)}%` })}</li>}
                </ul>
                <p className="small"><Link href="/learn/savings#every-period">{t("money.periods")} →</Link></p>
              </div>
            );
          })}
        </div>
      </div>
      <p className="small muted ym-note">{t("money.note")}</p>
    </section>
  );
}
