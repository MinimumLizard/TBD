import { getTranslations } from "next-intl/server";

import BreadthBar from "@/components/BreadthBar";
import Locked from "@/components/Locked";
import StatTile from "@/components/StatTile";
import Term from "@/components/Term";
import { lkr, num, percent, ratio } from "@/lib/format";
import { type Overview, curveYield } from "@/lib/overview";

const TENORS = [1, 5, 10] as const;

// The day's main figures as tiles: the share market (`shares`) and three points of the yield curve (`yields`).
export default async function MarketTiles({ o, shares = true, yields = true }: { o: Overview; shares?: boolean; yields?: boolean }) {
  const t = await getTranslations();
  const { session, aspiNow, spNow, fit, prevFit, fitHistory } = o;
  const lastYear = (rows: { value: number }[] | null) => (rows ?? []).slice(-250).map((r) => r.value);
  return (
    <>
      {!shares ? null : !o.tape.access.allowed ? (
        <Locked access={o.tape.access} />
      ) : (
        <div className="tiles">
          {aspiNow && (
            <StatTile label={t("home.aspiTile")} value={num(aspiNow.value)} change={aspiNow.pct}
                      note={t("home.today")} spark={lastYear(o.aspi.data)} sparkLabel={t("cse.aspiChart")} sparkCaption={t("home.trendYear")} />
          )}
          {spNow && (
            <StatTile label={t("home.spTile")} value={num(spNow.value)} change={spNow.pct}
                      note={t("home.today")} spark={lastYear(o.sp.data)} sparkLabel={t("home.spTile")} sparkCaption={t("home.trendYear")} />
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
      {yields && o.curve.access.allowed && fit && (
        <div className="tiles" style={{ marginTop: shares ? 16 : 0 }}>
          {TENORS.map((years) => (
            <StatTile key={years} label={t("home.yieldTile", { years })} value={percent(curveYield(fit, years), 2)}
                      note={prevFit ? `${curveYield(fit, years) >= curveYield(prevFit, years) ? "+" : "−"}${num(Math.abs(curveYield(fit, years) - curveYield(prevFit, years)) * 100, 1)} bp ${t("home.vsPrevDay")}` : t("home.yieldNote")}
                      spark={fitHistory.map((f) => curveYield(f, years))} sparkLabel={t("home.trend30")} sparkCaption={t("home.trend30")} />
          ))}
        </div>
      )}
    </>
  );
}
