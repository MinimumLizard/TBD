import Link from "next/link";
import { getTranslations } from "next-intl/server";

import AsOf from "@/components/AsOf";
import Brief from "@/components/Brief";
import BreadthBar from "@/components/BreadthBar";
import Chart from "@/components/Chart";
import Locked from "@/components/Locked";
import ModelFooter from "@/components/ModelFooter";
import StartChooser from "@/components/StartChooser";
import StatTile from "@/components/StatTile";
import Stats from "@/components/Stats";
import Term from "@/components/Term";
import { LOW_WEIGHT, curveOption, curvePoints, lineOption, nelsonSiegel } from "@/lib/charts";
import { bondCurve, bondCurveHistory } from "@/lib/data/bonds";
import { indexHistory, marketTape } from "@/lib/data/cse";
import { date, lkr, num, percent, ratio } from "@/lib/format";
import { marketSummary } from "@/lib/summary";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";

const TENORS = [1, 5, 10] as const;
const ns = (fit: { beta0: number; beta1: number; beta2: number; lambda_years: number }, tau: number) =>
  nelsonSiegel(tau, fit.beta0, fit.beta1, fit.beta2, fit.lambda_years);

export default async function Home() {
  const [t, viewer] = await Promise.all([getTranslations(), getViewer()]);
  const [tape, aspi, sp, curve, fits] = await Promise.all([
    marketTape(viewer),
    indexHistory(viewer, "ASI"),
    indexHistory(viewer, "S&P SL20"),
    bondCurve(viewer),
    bondCurveHistory(viewer),
  ]);
  const session = tape.data?.session ?? null;
  const index = (code: string) => tape.data?.indices.find((i) => i.index_code === code) ?? null;
  const aspiNow = index("ASI");
  const spNow = index("S&P SL20");
  const fit = curve.data?.fit ?? null;
  const fitHistory = fits.data ?? [];
  const prevFit = fitHistory.length > 1 ? fitHistory[fitHistory.length - 2] : null;
  const lastYear = (rows: { value: number }[] | null) => (rows ?? []).slice(-250).map((r) => r.value);

  const summary = marketSummary({
    aspi: aspiNow ? { value: aspiNow.value, pct: aspiNow.pct } : null,
    breadth: session ? { up: session.equities_up ?? 0, down: session.equities_down ?? 0, flat: session.equities_flat ?? 0 } : null,
    turnover: session ? { value: session.turnover, avg20: session.turnover_avg20 } : null,
    foreignNet: session?.foreign_net ?? null,
    curve: fit ? { y1: ns(fit, 1), y5: ns(fit, 5), y10: ns(fit, 10) } : null,
  });

  const when = session || fit ? t("home.when", { cse: date(session?.session_date), bonds: date(fit?.obs_date) }) : null;
  return (
    <>
      <section className="intro">
        <p className="eyebrow">{t("home.eyebrow")}</p>
        <h1>{t("home.heroTitle")}</h1>
        <p className="lead">{t("home.heroLead")}</p>
        <ul className="trust">
          <li>{t("home.trust1")}</li>
          <li>{t("home.trust2")}</li>
          <li>{t("home.trust3")}</li>
        </ul>
      </section>

      <section className="start-band" aria-labelledby="start-title">
        <div className="section-head">
          <h2 id="start-title">{t("start.homeTitle")}</h2>
        </div>
        <p className="muted" style={{ marginTop: -4 }}>{t("start.homeLead")}</p>
        <p className="continue-path" data-continue-path="" data-template={t("start.continue", { label: "{label}" })} hidden />
        <StartChooser />
      </section>

      <Brief title={t("home.briefTitle")} lines={summary.map((line) => t(line.key as never, line.values as never))} when={when} />

      <div className="section-head">
        <h2>{t("home.snapshot")}</h2>
      </div>
      <p className="small muted" style={{ marginTop: -4 }}>{t("home.snapshotLead")}</p>
      {!tape.access.allowed ? (
        <Locked access={tape.access} />
      ) : (
        <div className="tiles">
          {aspiNow && (
            <StatTile label={t("home.aspiTile")} value={num(aspiNow.value)} change={aspiNow.pct}
                      note={t("home.today")} spark={lastYear(aspi.data)} sparkLabel={t("cse.aspiChart")} sparkCaption={t("home.trendYear")} />
          )}
          {spNow && (
            <StatTile label={t("home.spTile")} value={num(spNow.value)} change={spNow.pct}
                      note={t("home.today")} spark={lastYear(sp.data)} sparkLabel={t("home.spTile")} sparkCaption={t("home.trendYear")} />
          )}
          {session && (
            <StatTile label={t("home.turnoverTile")} value={lkr(session.turnover)}
                      note={session.turnover && session.turnover_avg20 ? t("cse.vsAverage", { ratio: ratio(session.turnover / session.turnover_avg20) })
                        : session.sessions_needed ? t("cse.averagePending", { count: session.sessions_needed }) : null} />
          )}
          {session && (
            <div className="tile stat">
              <span className="label">{t("home.breadthTile")}</span>
              <BreadthBar up={session.equities_up} flat={session.equities_flat} down={session.equities_down}
                          labels={{ up: t("cse.rose"), flat: t("cse.unchanged"), down: t("cse.fell") }} />
              <span className="sub"><Term id="breadth" /></span>
            </div>
          )}
        </div>
      )}
      {curve.access.allowed && fit && (
        <div className="tiles" style={{ marginTop: 16 }}>
          {TENORS.map((years) => (
            <StatTile key={years} label={t("home.yieldTile", { years })} value={percent(ns(fit, years), 2)}
                      note={prevFit ? `${ns(fit, years) >= ns(prevFit, years) ? "+" : "−"}${num(Math.abs(ns(fit, years) - ns(prevFit, years)) * 100, 1)} bp ${t("home.vsPrevDay")}` : t("home.yieldNote")}
                      spark={fitHistory.map((f) => ns(f, years))} sparkLabel={t("home.trend30")} sparkCaption={t("home.trend30")} />
          ))}
        </div>
      )}

      <div className="grid two" style={{ marginTop: 24 }}>
        <section className="card">
          <div className="card-head">
            <h2>{t("home.cseTitle")}</h2>
            <Link className="more" href="/cse">{t("home.more")} →</Link>
          </div>
          {!tape.access.allowed ? (
            <Locked access={tape.access} />
          ) : (
            <>
              <AsOf day={session?.session_date ?? null} calendar="cse" />
              {aspi.data && aspi.data.length > 1 && (
                <Chart label={t("cse.aspiChart")} height={240}
                       option={lineOption([{ name: "ASPI", points: aspi.data.map((r) => [r.session_date, r.value]) }], undefined, { area: true })} />
              )}
              <p className="small muted">{t("home.cseWhy")}</p>
              <p className="small muted"><Term id="aspi" /> · <Term id="turnover" /> · <Term id="foreign" /></p>
            </>
          )}
        </section>
        <section className="card">
          <div className="card-head">
            <h2>{t("home.bondsTitle")}</h2>
            <Link className="more" href="/bonds">{t("home.more")} →</Link>
          </div>
          {!curve.access.allowed ? (
            <Locked access={curve.access} />
          ) : fit ? (
            <>
              <AsOf day={fit.obs_date} calendar="lk_bond_market" />
              <Chart
                label={t("bonds.curveTitle")}
                height={260}
                option={curveOption({
                  quotes: curve.data!.points.filter((p) => p.source === "quote" && (p.weight ?? 1) >= LOW_WEIGHT).map((p) => [p.tau_years, p.observed_yield, p.isin]),
                  wide: curve.data!.points.filter((p) => p.source === "quote" && (p.weight ?? 1) < LOW_WEIGHT).map((p) => [p.tau_years, p.observed_yield, p.isin]),
                  trades: curve.data!.points.filter((p) => p.source === "trade").map((p) => [p.tau_years, p.observed_yield, p.isin]),
                  curve: curvePoints(fit, Math.max(...curve.data!.points.map((p) => p.tau_years))),
                  names: { quotes: t("bonds.quotes"), wide: t("bonds.wideQuotes"), trades: t("bonds.trades"), curve: t("bonds.curve"), years: t("bonds.years"), yield: t("bonds.yield") },
                })}
              />
              <p className="small muted">{t("home.bondsWhy")}</p>
              <p className="small muted"><Term id="curve" /> · <Term id="yield" /> · <Term id="bp" /></p>
            </>
          ) : (
            <p>{t("common.noData")}</p>
          )}
        </section>
      </div>

      <div className="section-head">
        <h2>{t("home.linksTitle")}</h2>
      </div>
      <p className="muted" style={{ marginTop: -4 }}>{t("home.linksLead")}</p>
      <div className="links3">
        {([["1", "/learn/yield-curve"], ["2", "/learn/savings"], ["3", "/learn/shares-basics"]] as const).map(([n, href]) => (
          <div key={n}>
            <h3>{t(`home.link${n}Title`)}</h3>
            <p>{t(`home.link${n}Body`)}</p>
            <Link className="more" href={href}>{t(`home.link${n}Go`)} →</Link>
          </div>
        ))}
      </div>

      <Stats viewer={viewer} keys={["investors", "literacy", "savers"]} />

      <div className="section-head">
        <h2>{t("home.differsTitle")}</h2>
      </div>
      <ul className="differs">
        {(["1", "2", "3", "4"] as const).map((n) => (
          <li key={n}>
            <strong>{t(`home.differ${n}Title`)}</strong>
            <span>{t(`home.differ${n}Body`)}</span>
          </li>
        ))}
      </ul>

      <div className="section-head">
        <h2>{t("home.tiersTitle")}</h2>
        <Link className="more" href="/plans">{t("home.plansLink")} →</Link>
      </div>
      <p className="muted" style={{ marginTop: -4 }}>{t("home.tiersLead")}</p>
      <div className="tier-strip">
        {(["free", "plus", "pro"] as const).map((tier) => (
          <div key={tier}>
            <span className={`tier-pill ${tier}`} style={{ justifySelf: "start" }}>{t(`tiers.${tier}`)}</span>
            <p>{t(`home.tier${tier === "free" ? "Free" : tier === "plus" ? "Plus" : "Pro"}`)}</p>
          </div>
        ))}
      </div>

      <ModelFooter models={["cse_market_tape", "bond_ns_curve"]} />
    </>
  );
}
