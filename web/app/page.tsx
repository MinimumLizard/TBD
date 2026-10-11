import Link from "next/link";
import { getTranslations } from "next-intl/server";

import AsOf from "@/components/AsOf";
import Chart from "@/components/Chart";
import Locked from "@/components/Locked";
import ModelFooter from "@/components/ModelFooter";
import { LOW_WEIGHT, curveOption, curvePoints, lineOption } from "@/lib/charts";
import { HEADLINE_INDICES } from "@/lib/cse-display";
import { bondCurve } from "@/lib/data/bonds";
import { indexHistory, marketTape } from "@/lib/data/cse";
import { int, lkr, num, pct, ratio, tone } from "@/lib/format";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";

export default async function Home() {
  const [t, viewer] = await Promise.all([getTranslations(), getViewer()]);
  const [tape, aspi, curve] = await Promise.all([marketTape(viewer), indexHistory(viewer, "ASI"), bondCurve(viewer)]);
  return (
    <>
      <h1>{t("home.title")}</h1>
      <p className="lead">{t("home.intro")}</p>
      <div className="grid two">
        <section className="card">
          <h2>{t("home.cseTitle")}</h2>
          {!tape.access.allowed ? (
            <Locked access={tape.access} />
          ) : (
            <>
              <AsOf day={tape.data?.session?.session_date ?? null} calendar="cse" />
              <div className="grid two">
                {tape.data?.indices
                  .filter((i) => i.index_code === HEADLINE_INDICES[0] || i.index_code === HEADLINE_INDICES[1])
                  .map((i) => (
                    <div className="stat" key={i.index_code}>
                      <span className="label">{t(`cse.indexNames.${i.index_code}` as never)}</span>
                      <span className="value">{num(i.value)}</span>
                      <span className={tone(i.pct)}>{pct(i.pct)}</span>
                    </div>
                  ))}
                {tape.data?.session && (
                  <div className="stat">
                    <span className="label">{t("cse.turnover")}</span>
                    <span className="value">{lkr(tape.data.session.turnover)}</span>
                    {tape.data.session.turnover_avg20 && tape.data.session.turnover ? (
                      <span className="muted small">
                        {t("cse.vsAverage", { ratio: ratio(tape.data.session.turnover / tape.data.session.turnover_avg20) })}
                      </span>
                    ) : null}
                  </div>
                )}
                {tape.data?.session && (
                  <div className="stat">
                    <span className="label">{t("cse.breadth")}</span>
                    <span className="value">
                      <span className="up">{int(tape.data.session.equities_up)}</span> /{" "}
                      <span className="down">{int(tape.data.session.equities_down)}</span>
                    </span>
                    <span className="muted small">
                      {t("cse.rose")} / {t("cse.fell")}
                    </span>
                  </div>
                )}
              </div>
              {aspi.data && aspi.data.length > 1 && (
                <Chart
                  label={t("cse.aspiChart")}
                  height={220}
                  option={lineOption([{ name: "ASPI", points: aspi.data.map((r) => [r.session_date, r.value]) }])}
                />
              )}
              <p>
                <Link href="/cse">{t("home.more")} →</Link>
              </p>
            </>
          )}
        </section>
        <section className="card">
          <h2>{t("home.bondsTitle")}</h2>
          {!curve.access.allowed ? (
            <Locked access={curve.access} />
          ) : curve.data?.fit ? (
            <>
              <AsOf day={curve.data.fit.obs_date} calendar="lk_bond_market" />
              <Chart
                label={t("bonds.curveTitle")}
                height={260}
                option={curveOption({
                quotes: curve.data.points.filter((p) => p.source === "quote" && (p.weight ?? 1) >= LOW_WEIGHT).map((p) => [p.tau_years, p.observed_yield, p.isin]),
                wide: curve.data.points.filter((p) => p.source === "quote" && (p.weight ?? 1) < LOW_WEIGHT).map((p) => [p.tau_years, p.observed_yield, p.isin]),
                trades: curve.data.points.filter((p) => p.source === "trade").map((p) => [p.tau_years, p.observed_yield, p.isin]),
                curve: curvePoints(curve.data.fit, Math.max(...curve.data.points.map((p) => p.tau_years))),
                names: { quotes: t("bonds.quotes"), wide: t("bonds.wideQuotes"), trades: t("bonds.trades"), curve: t("bonds.curve"), years: t("bonds.years"), yield: t("bonds.yield") },
              })}
              />
              <p>
                <Link href="/bonds">{t("home.more")} →</Link>
              </p>
            </>
          ) : (
            <p>{t("common.noData")}</p>
          )}
        </section>
      </div>
      <ModelFooter models={["cse_market_tape", "bond_ns_curve"]} />
    </>
  );
}
