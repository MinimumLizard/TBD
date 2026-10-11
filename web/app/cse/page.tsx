import Link from "next/link";
import { getTranslations } from "next-intl/server";

import AsOf from "@/components/AsOf";
import Chart from "@/components/Chart";
import Locked from "@/components/Locked";
import ModelFooter from "@/components/ModelFooter";
import { lineOption } from "@/lib/charts";
import { MOVERS_MIN_TURNOVER, isHeadline } from "@/lib/cse-display";
import { type IndexSession, type ShareSession, indexHistory, marketTape, shares } from "@/lib/data/cse";
import { int, lkr, num, pct, percent, ratio, signed, tone } from "@/lib/format";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";

export async function generateMetadata() {
  const t = await getTranslations();
  return { title: t("cse.title") };
}

export default async function CsePage() {
  const [t, viewer] = await Promise.all([getTranslations(), getViewer()]);
  const [tape, aspi, all] = await Promise.all([marketTape(viewer), indexHistory(viewer, "ASI"), shares(viewer)]);

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
              <td>{isHeadline(r.index_code) ? t(`cse.indexNames.${r.index_code}` as never) : r.index_code}</td>
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
              </td>
              <td className="num">{num(r.close)}</td>
              <td className={`num ${tone(r.pct)}`}>{pct(r.pct)}</td>
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
  const liquid = traded.filter((r) => (r.turnover ?? 0) >= MOVERS_MIN_TURNOVER && r.pct != null);

  return (
    <>
      <h1>{t("cse.title")}</h1>
      <p className="lead">{t("cse.intro")}</p>
      {!tape.access.allowed ? (
        <Locked access={tape.access} />
      ) : (
        <>
          <AsOf day={s?.session_date ?? null} calendar="cse" />
          {s && (
            <>
              <h2>{t("cse.activity")}</h2>
              <div className="grid three">
                <div className="card stat">
                  <span className="label">{t("cse.turnover")}</span>
                  <span className="value">{lkr(s.turnover)}</span>
                  <span className="muted small">{vsAvg(s.turnover, s.turnover_avg20)}</span>
                </div>
                <div className="card stat">
                  <span className="label">{t("cse.volume")}</span>
                  <span className="value">{int(s.volume)}</span>
                  <span className="muted small">{vsAvg(s.volume, s.volume_avg20)}</span>
                </div>
                <div className="card stat">
                  <span className="label">{t("cse.trades")}</span>
                  <span className="value">{int(s.trades)}</span>
                  <span className="muted small">{vsAvg(s.trades, s.trades_avg20)}</span>
                </div>
              </div>
              <div className="grid three">
                <section>
                  <h2>{t("cse.foreign")}</h2>
                  <dl className="facts">
                    <dt>{t("cse.foreignPurchases")}</dt>
                    <dd>{lkr(s.foreign_buy)}</dd>
                    <dt>{t("cse.foreignSales")}</dt>
                    <dd>{lkr(s.foreign_sell)}</dd>
                    <dt>{t("cse.foreignNet")}</dt>
                    <dd className={tone(s.foreign_net)}>{lkr(s.foreign_net)}</dd>
                  </dl>
                </section>
                <section>
                  <h2>{t("cse.breadth")}</h2>
                  <dl className="facts">
                    <dt>{t("cse.rose")}</dt>
                    <dd className="up">{int(s.equities_up)}</dd>
                    <dt>{t("cse.fell")}</dt>
                    <dd className="down">{int(s.equities_down)}</dd>
                    <dt>{t("cse.unchanged")}</dt>
                    <dd>{int(s.equities_flat)}</dd>
                  </dl>
                  <p className="small muted">{t("cse.breadthNote")}</p>
                  {s.listed != null && s.traded_all != null && (
                    <p className="small muted">{t("cse.listedTraded", { traded: s.traded_all, listed: s.listed })}</p>
                  )}
                </section>
                <section>
                  <h2>{t("cse.valuation")}</h2>
                  <dl className="facts">
                    <dt>{t("cse.per")}</dt>
                    <dd>{num(s.per, 1)}</dd>
                    <dt>{t("cse.pbv")}</dt>
                    <dd>{num(s.pbv, 1)}</dd>
                    <dt>{t("cse.dy")}</dt>
                    <dd>{percent(s.dy, 1)}</dd>
                    <dt>{t("cse.marketCap")}</dt>
                    <dd>{lkr(s.market_cap)}</dd>
                  </dl>
                </section>
              </div>
            </>
          )}
          <h2>{t("cse.headline")}</h2>
          {indexRows((tape.data?.indices ?? []).filter((r) => isHeadline(r.index_code)))}
          {aspi.data && aspi.data.length > 1 && (
            <Chart label={t("cse.aspiChart")} option={lineOption([{ name: "ASPI", points: aspi.data.map((r) => [r.session_date, r.value]) }])} />
          )}
          <h2>{t("cse.sectors")}</h2>
          {indexRows((tape.data?.indices ?? []).filter((r) => !isHeadline(r.index_code)))}
        </>
      )}
      {!all.access.allowed ? (
        <Locked access={all.access} />
      ) : (
        <>
          <div className="grid three">
            <section>
              <h2>{t("cse.topTurnover")}</h2>
              {shareRows([...traded].sort((a, b) => (b.turnover ?? 0) - (a.turnover ?? 0)).slice(0, 10))}
            </section>
            <section>
              <h2>{t("cse.largestRises")}</h2>
              {shareRows(liquid.filter((r) => (r.pct ?? 0) > 0).sort((a, b) => (b.pct ?? 0) - (a.pct ?? 0)).slice(0, 10))}
            </section>
            <section>
              <h2>{t("cse.largestFalls")}</h2>
              {shareRows(liquid.filter((r) => (r.pct ?? 0) < 0).sort((a, b) => (a.pct ?? 0) - (b.pct ?? 0)).slice(0, 10))}
            </section>
          </div>
          <p className="small muted">{t("cse.moversNote")}</p>
        </>
      )}
      <ModelFooter models={["cse_market_tape", "cse_security_metrics"]} />
    </>
  );
}
