import { getTranslations } from "next-intl/server";

import AsOf from "@/components/AsOf";
import Chart from "@/components/Chart";
import Locked from "@/components/Locked";
import ModelFooter from "@/components/ModelFooter";
import { lineOption } from "@/lib/charts";
import { shareHistory } from "@/lib/data/cse";
import { NONE, int, lkr, num, pct, ratio, tone } from "@/lib/format";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";

export async function generateMetadata({ params }: { params: Promise<{ symbol: string }> }) {
  return { title: decodeURIComponent((await params).symbol) };
}

export default async function SharePage({ params }: { params: Promise<{ symbol: string }> }) {
  const symbol = decodeURIComponent((await params).symbol);
  const [t, viewer] = await Promise.all([getTranslations(), getViewer()]);
  const history = await shareHistory(viewer, symbol);
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
  if (!last) {
    return (
      <>
        <h1>{symbol}</h1>
        <p>{t("share.unknown")}</p>
      </>
    );
  }
  const windows = [
    ["w1", last.ret_1w, last.rel_1w, last.flag_1w],
    ["m1", last.ret_1m, last.rel_1m, last.flag_1m],
    ["m3", last.ret_3m, last.rel_3m, last.flag_3m],
  ] as const;
  return (
    <>
      <h1>{symbol}</h1>
      <AsOf day={last.session_date} calendar="cse" />
      <div className="grid three">
        <div className="card stat">
          <span className="label">{t("share.latest")}</span>
          <span className="value">{num(last.close)}</span>
          <span className={tone(last.pct)}>{last.traded ? pct(last.pct) : t("common.notTraded")}</span>
        </div>
        <div className="card stat">
          <span className="label">{t("share.range52")}</span>
          <span className="value">
            {num(last.low_52w)} – {num(last.high_52w)}
          </span>
          <span className="muted small">{last.range_pos == null ? NONE : `${num(last.range_pos * 100, 0)}%`}</span>
        </div>
        <div className="card stat">
          <span className="label">{t("share.marketCap")}</span>
          <span className="value">{lkr(last.market_cap)}</span>
          <span className="muted small">
            {t("share.beta")}: {num(last.beta)}
          </span>
        </div>
      </div>
      <h2>{t("share.priceChart")}</h2>
      <Chart
        label={t("share.priceChart")}
        option={lineOption([{ name: symbol, points: rows.filter((r) => r.traded).map((r) => [r.session_date, r.close]) }])}
      />
      <h2>{t("share.returns")}</h2>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>{t("share.window")}</th>
              <th className="num">{t("share.price")}</th>
              <th className="num">{t("share.relative")}</th>
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
