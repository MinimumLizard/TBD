import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";

import AsOf from "@/components/AsOf";
import Chart from "@/components/Chart";
import Locked from "@/components/Locked";
import ModelFooter from "@/components/ModelFooter";
import { lineOption } from "@/lib/charts";
import StatTile from "@/components/StatTile";
import Term from "@/components/Term";
import { actionAmount, companyName } from "@/lib/cse-display";
import { type TotalReturnSession, corporateActions, securityNames, shareHistory, totalReturns } from "@/lib/data/cse";
import { NONE, date, int, lkr, num, pct, ratio, tone } from "@/lib/format";
import { decodeSegment } from "@/lib/params";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";

export async function generateMetadata({ params }: { params: Promise<{ symbol: string }> }) {
  return { title: decodeSegment((await params).symbol) };
}

export default async function SharePage({ params }: { params: Promise<{ symbol: string }> }) {
  const symbol = decodeSegment((await params).symbol);
  const [t, viewer] = await Promise.all([getTranslations(), getViewer()]);
  const [history, names, actions, returns] = await Promise.all([
    shareHistory(viewer, symbol), securityNames(viewer), corporateActions(viewer, symbol), totalReturns(viewer, symbol),
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
  return (
    <>
      <h1>{companyName(ref?.name) ?? symbol}</h1>
      <p className="lead">
        {symbol}
        {ref?.sector_label ? ` · ${ref.sector_label}` : ""}
      </p>
      <AsOf day={last.session_date} calendar="cse" />
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
      {trLine.length > 1 ? (
        <>
          <h2>{t("share.chart")}</h2>
          <Chart
            label={t("share.chart")}
            option={lineOption([{ name: t("share.priceSeries"), points: priceLine }, { name: t("share.totalReturnSeries"), points: trLine }])}
          />
          <p className="small muted">{t("share.chartNote", { date: date(trRows[0].session_date) })}</p>
        </>
      ) : (
        <>
          <h2>{t("share.priceChart")}</h2>
          <Chart label={t("share.priceChart")} option={lineOption([{ name: symbol, points: priceLine }], undefined, { area: true })} />
        </>
      )}
      {!returns.access.allowed && <Locked access={returns.access} />}
      <h2>{t("share.returns")}</h2>
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
      <h2>{t("share.actions")}</h2>
      {!actions.access.allowed ? (
        <Locked access={actions.access} />
      ) : (actions.data ?? []).length === 0 ? (
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
                {(actions.data ?? []).map((a) => {
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
      <ModelFooter models={["cse_security_metrics", ...(actions.access.allowed ? ["cse_corporate_actions" as const] : []),
                            ...(returns.access.allowed ? ["cse_total_returns" as const] : [])]} />
    </>
  );
}
