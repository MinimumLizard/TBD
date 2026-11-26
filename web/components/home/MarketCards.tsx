import Link from "next/link";
import { getTranslations } from "next-intl/server";

import AsOf from "@/components/AsOf";
import Chart from "@/components/Chart";
import Locked from "@/components/Locked";
import Term from "@/components/Term";
import { LOW_WEIGHT, curveOption, curvePoints, lineOption } from "@/lib/charts";
import type { Overview } from "@/lib/overview";

// The share market's year in one line.
export async function SharesCard({ o }: { o: Overview }) {
  const t = await getTranslations();
  return (
    <section className="card">
      <div className="card-head">
        <h2>{t("home.cseTitle")}</h2>
        <Link className="more" href="/cse">{t("home.more")} →</Link>
      </div>
      {!o.tape.access.allowed ? (
        <Locked access={o.tape.access} />
      ) : (
        <>
          <AsOf day={o.session?.session_date ?? null} calendar="cse" />
          {o.aspi.data && o.aspi.data.length > 1 && (
            <Chart label={t("cse.aspiChart")} height={240}
                   option={lineOption([{ name: "ASPI", points: o.aspi.data.map((r) => [r.session_date, r.value]) }], undefined, { area: true })} />
          )}
          <p className="small muted">{t("home.cseWhy")}</p>
          <p className="small muted"><Term id="aspi" /> · <Term id="turnover" /> · <Term id="foreign" /></p>
        </>
      )}
    </section>
  );
}

// Today's government yield curve.
export async function CurveCard({ o }: { o: Overview }) {
  const t = await getTranslations();
  const { curve, fit } = o;
  return (
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
              trades: curve.data!.points.filter((p) => p.source === "trade").map((p) => [p.tau_years, p.observed_yield, p.isin]),
              curve: curvePoints(fit, Math.max(...curve.data!.points.map((p) => p.tau_years))),
              names: { quotes: t("bonds.quotes"), trades: t("bonds.trades"), curve: t("bonds.curve"), years: t("bonds.years"), yield: t("bonds.yield") },
            })}
          />
          <p className="small muted">{t("home.bondsWhy")}</p>
          <p className="small muted"><Term id="curve" /> · <Term id="yield" /> · <Term id="bp" /></p>
        </>
      ) : (
        <p>{t("common.noData")}</p>
      )}
    </section>
  );
}
