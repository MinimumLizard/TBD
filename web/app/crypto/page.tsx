import Link from "next/link";
import { getTranslations } from "next-intl/server";

import AsOf from "@/components/AsOf";
import Chart from "@/components/Chart";
import CryptoNotice from "@/components/CryptoNotice";
import Locked from "@/components/Locked";
import ModelFooter from "@/components/ModelFooter";
import PreviewNote from "@/components/PreviewNote";
import Sparkline from "@/components/Sparkline";
import Term from "@/components/Term";
import { lineOption, weeklyPoints } from "@/lib/charts";
import { CRYPTO_ASSETS, assetByPair, price } from "@/lib/crypto-display";
import { cryptoCycle, cryptoHistory, cryptoOverview } from "@/lib/data/crypto";
import { NONE, date, pct, percent, tone } from "@/lib/format";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";

export async function generateMetadata() {
  const t = await getTranslations();
  return { title: t("crypto.title") };
}

export default async function CryptoPage() {
  const [t, viewer] = await Promise.all([getTranslations(), getViewer()]);
  const [overview, btc, cycle] = await Promise.all([
    cryptoOverview(viewer),
    cryptoHistory(viewer, "btcusd"),
    cryptoCycle(viewer, "btcusd"),
  ]);
  const order = (pair: string) => CRYPTO_ASSETS.findIndex((a) => a.pair === pair);
  const latest = [...(overview.data?.latest ?? [])].filter((r) => assetByPair(r.pair)).sort((a, b) => order(a.pair) - order(b.pair));
  const name = (pair: string) => t(`crypto.assets.${assetByPair(pair)!.slug}` as never);
  const cycleDays = cycle.data?.daily ?? [];
  const lastCycle = cycleDays[cycleDays.length - 1];

  return (
    <>
      <h1>{t("crypto.title")}</h1>
      <p className="lead">{t("crypto.intro")}</p>
      <CryptoNotice />
      {!overview.access.allowed ? (
        <Locked access={overview.access} />
      ) : (
        <>
          <AsOf day={overview.data?.day ?? null} calendar="crypto" />
          <h2>{t("crypto.assetsTitle")}</h2>
          <div className="tiles">
            {latest.map((r) => {
              const asset = assetByPair(r.pair)!;
              return (
                <Link key={r.pair} href={`/crypto/${asset.slug}`} className="tile stat asset-card">
                  <span className="label">
                    {name(r.pair)} <span className="code">{asset.label}</span>
                  </span>
                  <span className="value">{price(r.close, asset.quote)}</span>
                  <span className="sub">
                    <span className={`chip ${tone(r.ret_1d)}`}>{pct(r.ret_1d)}</span>{" "}
                    {r.drawdown < 0 ? t("crypto.fromHigh", { pct: pct(r.drawdown) }) : t("crypto.atHigh")}
                  </span>
                  <Sparkline values={overview.data?.recent[r.pair] ?? []} label={`${name(r.pair)}, ${t("crypto.last90")}`} />
                  <span className="caption">{t("crypto.last90")}</span>
                </Link>
              );
            })}
          </div>
          <p className="small muted" style={{ marginTop: 12 }}>{t("crypto.utcDay")} {t("crypto.history")}</p>
        </>
      )}

      <div className="section-head">
        <h2>{t("crypto.btcTitle")}</h2>
        <span className="tier-pill plus">{t("tiers.plus")}</span>
      </div>
      {!cycle.access.allowed ? (
        <Locked access={cycle.access} />
      ) : (
        <>
          <PreviewNote access={cycle.access} />
          {lastCycle && (
            <div className="tiles">
              <div className="tile stat">
                <span className="label"><Term id="movingAverage">{t("crypto.sma200wTile")}</Term></span>
                <span className="value">{price(lastCycle.sma_200w)}</span>
                <span className="sub">
                  {date(lastCycle.day)} · {t("crypto.sma200wChange", { pct: pct(lastCycle.sma_200w_chg_4w) })}
                </span>
              </div>
              <div className="tile stat">
                <span className="label">{t("crypto.priceVs200w")}</span>
                <span className="value">{lastCycle.sma_200w ? pct(lastCycle.close / lastCycle.sma_200w - 1) : NONE}</span>
                <span className="sub">{date(lastCycle.day)} · {price(lastCycle.close)}</span>
              </div>
            </div>
          )}
        </>
      )}
      {btc.access.allowed && btc.data && btc.data.length > 1 && (
        <>
        <Chart
          label={t("crypto.btcChart")}
          option={lineOption([
            { name: t("crypto.price"), points: weeklyPoints(btc.data, (r) => r.close) },
            ...(cycleDays.length ? [{ name: t("crypto.sma200w"), points: weeklyPoints(cycleDays, (r) => r.sma_200w), dashed: true }] : []),
          ], "USD", { logY: true })}
        />
        <p className="small muted">{t("crypto.btcChart")}</p>
        </>
      )}

      {overview.access.allowed && latest.length > 0 && (
        <>
          <h2>{t("crypto.tableTitle")}</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{t("crypto.asset")}</th>
                  <th className="num">{t("crypto.close")}</th>
                  <th className="num">{t("crypto.d1")}</th>
                  <th className="num">{t("crypto.d7")}</th>
                  <th className="num">{t("crypto.d30")}</th>
                  <th className="num">{t("crypto.y1")}</th>
                  <th className="num"><Term id="drawdown">{t("crypto.drawdown")}</Term></th>
                  <th className="num"><Term id="volatility">{t("crypto.vol30")}</Term></th>
                </tr>
              </thead>
              <tbody>
                {latest.map((r) => {
                  const asset = assetByPair(r.pair)!;
                  return (
                    <tr key={r.pair}>
                      <td>
                        <Link href={`/crypto/${asset.slug}`}>{name(r.pair)}</Link>
                        <span className="sub">{asset.label}</span>
                      </td>
                      <td className="num">{price(r.close, asset.quote)}</td>
                      <td className={`num ${tone(r.ret_1d)}`}>{pct(r.ret_1d)}</td>
                      <td className={`num ${tone(r.ret_7d)}`}>{pct(r.ret_7d)}</td>
                      <td className={`num ${tone(r.ret_30d)}`}>{pct(r.ret_30d)}</td>
                      <td className={`num ${tone(r.ret_1y)}`}>{pct(r.ret_1y)}</td>
                      <td className="num">{pct(r.drawdown)}</td>
                      <td className="num">{percent(r.vol_30d == null ? null : r.vol_30d * 100, 0)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
      <ModelFooter models={["crypto_market", "crypto_cycle"]} shownAbove={["crypto_risk"]} />
    </>
  );
}
