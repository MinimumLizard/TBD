import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";

import AsOf from "@/components/AsOf";
import Chart from "@/components/Chart";
import Locked from "@/components/Locked";
import ModelFooter from "@/components/ModelFooter";
import { lineOption } from "@/lib/charts";
import StatTile from "@/components/StatTile";
import Term from "@/components/Term";
import { companyName } from "@/lib/cse-display";
import { securityNames, shareHistory } from "@/lib/data/cse";
import { NONE, int, lkr, num, pct, ratio, tone } from "@/lib/format";
import { decodeSegment } from "@/lib/params";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";

export async function generateMetadata({ params }: { params: Promise<{ symbol: string }> }) {
  return { title: decodeSegment((await params).symbol) };
}

export default async function SharePage({ params }: { params: Promise<{ symbol: string }> }) {
  const symbol = decodeSegment((await params).symbol);
  const [t, viewer] = await Promise.all([getTranslations(), getViewer()]);
  const [history, names] = await Promise.all([shareHistory(viewer, symbol), securityNames(viewer)]);
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
  const windows = [
    ["w1", last.ret_1w, last.rel_1w, last.flag_1w],
    ["m1", last.ret_1m, last.rel_1m, last.flag_1m],
    ["m3", last.ret_3m, last.rel_3m, last.flag_3m],
  ] as const;
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
      <h2>{t("share.priceChart")}</h2>
      <Chart
        label={t("share.priceChart")}
        option={lineOption([{ name: symbol, points: rows.filter((r) => r.traded).map((r) => [r.session_date, r.close]) }], undefined, { area: true })}
      />
      <h2>{t("share.returns")}</h2>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>{t("share.window")}</th>
              <th className="num">{t("share.price")}</th>
              <th className="num"><Term id="relative">{t("share.relative")}</Term></th>
              <th>{t("shares.flag")}</th>
            </tr>
          </thead>
          <tbody>
            {windows.map(([key, ret, rel, flag]) => (
              <tr key={key}>
                <td>{t(`share.${key}`)}</td>
                <td className={`num ${tone(ret)}`}>{pct(ret)}</td>
                <td className={`num ${tone(rel)}`}>{pct(rel)}</td>
                <td className="small">{flag ? (flag.startsWith("unadjusted") ? t("shares.flagJump") : t("shares.flagNoTrade")) : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <dl className="facts" style={{ marginTop: 16 }}>
        <dt>{t("share.volume")}</dt>
        <dd>{int(last.volume)}</dd>
        <dt>{t("share.volAverage")}</dt>
        <dd>
          {int(last.vol_avg20)} ({ratio(last.vol_ratio)})
        </dd>
      </dl>
      {last.range_flag && <div className="notice warn">{t("shares.flagRange")}</div>}
      <ModelFooter models={["cse_security_metrics"]} />
    </>
  );
}
