import Link from "next/link";
import { getTranslations } from "next-intl/server";

import AsOf from "@/components/AsOf";
import Locked from "@/components/Locked";
import ModelFooter from "@/components/ModelFooter";
import Term from "@/components/Term";
import { companyName } from "@/lib/cse-display";
import { type CompanyRatios, type ShareSession, ratiosByCompany, securityNames, shares } from "@/lib/data/cse";
import { NONE, lkr, num, pct, percent, ratio, tone } from "@/lib/format";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";

const SORTS = ["symbol", "pct", "turnover", "range_pos", "vol_ratio", "rel_1w", "rel_1m", "rel_3m", "pe", "pb", "dy"] as const;
type Sort = (typeof SORTS)[number];
type Row = ShareSession & Partial<CompanyRatios>;

export async function generateMetadata() {
  const t = await getTranslations();
  return { title: t("shares.title") };
}

/** Largest first (or smallest first with dir=asc); a share without the figure always comes last. */
function sortRows(rows: Row[], sort: Sort, asc: boolean): Row[] {
  if (sort === "symbol") return asc ? rows : [...rows].reverse();
  const value = (r: Row) => (r[sort] as number | null | undefined) ?? null;
  return [...rows].sort((a, b) => {
    const x = value(a), y = value(b);
    if (x === null || y === null) return x === null ? (y === null ? 0 : 1) : -1;
    return asc ? x - y : y - x;
  });
}

export default async function SharesPage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const params = await searchParams;
  const sort: Sort = (SORTS as readonly string[]).includes(params.sort ?? "") ? (params.sort as Sort) : "turnover";
  const asc = sort === "symbol" ? params.dir !== "desc" : params.dir === "asc";
  const onlyTraded = params.all !== "1";
  const [t, viewer] = await Promise.all([getTranslations(), getViewer()]);
  const [result, names, ratios] = await Promise.all([shares(viewer), securityNames(viewer), ratiosByCompany(viewer)]);
  const showRatios = ratios.access.allowed;
  // The company's ratios, on its voting share's row (they are computed at the voting share's price).
  const ratiosOf = (symbol: string): Partial<CompanyRatios> =>
    (showRatios && symbol.endsWith(".N0000") ? ratios.data?.byCode.get(symbol.split(".")[0]) : undefined) ?? {};
  const flag = (r: ShareSession) => {
    const notes = [];
    if ([r.flag_1w, r.flag_1m, r.flag_3m].some((f) => f && f.startsWith("unadjusted"))) notes.push(t("shares.flagJump"));
    if (r.range_flag) notes.push(t("shares.flagRange"));
    return notes;
  };
  const header = (key: Sort, label: React.ReactNode) => {
    // a second click on the current column reverses the order
    const flip = sort === key ? (key === "symbol" ? (asc ? "&dir=desc" : "") : (asc ? "" : "&dir=asc")) : "";
    return (
      <th className={key === "symbol" ? "" : "num"}>
        <Link href={`/cse/shares?sort=${key}${flip}${onlyTraded ? "" : "&all=1"}`} aria-current={sort === key ? "true" : undefined}>
          {label}
          {sort === key && key !== "symbol" ? (asc ? " ↑" : " ↓") : ""}
        </Link>
      </th>
    );
  };
  return (
    <>
      <h1>{t("shares.title")}</h1>
      <p className="lead">{t("shares.intro")}</p>
      {!result.access.allowed ? (
        <Locked access={result.access} />
      ) : (
        (() => {
          const rows = sortRows((result.data?.rows ?? []).filter((r) => !onlyTraded || r.traded)
            .map((r) => ({ ...r, ...ratiosOf(r.symbol) })), sort, asc);
          return (
            <>
              <AsOf day={result.data?.date ?? null} calendar="cse" />
              <p className="small">
                <Link href={onlyTraded ? `/cse/shares?sort=${sort}&all=1` : `/cse/shares?sort=${sort}`}>
                  {onlyTraded ? t("shares.all") : t("shares.filterTraded")}
                </Link>{" "}
                · <span className="muted">{t("common.showing", { count: rows.length, total: result.data?.rows.length ?? 0 })}</span>
              </p>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      {header("symbol", t("shares.symbol"))}
                      <th className="num">{t("shares.close")}</th>
                      {header("pct", t("shares.changePct"))}
                      {header("turnover", t("shares.turnover"))}
                      {header("range_pos", t("shares.rangePos"))}
                      {header("vol_ratio", t("shares.volRatio"))}
                      {header("rel_1w", t("shares.rel1w"))}
                      {header("rel_1m", t("shares.rel1m"))}
                      {header("rel_3m", t("shares.rel3m"))}
                      {showRatios && header("pe", t("shares.pe"))}
                      {showRatios && header("pb", t("shares.pb"))}
                      {showRatios && header("dy", t("shares.dy"))}
                      <th>{t("shares.flag")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => {
                      const notes = flag(r);
                      return (
                        <tr key={r.symbol}>
                          <td>
                            <Link href={`/cse/shares/${encodeURIComponent(r.symbol)}`}>{r.symbol}</Link>
                            <span className="sub">{companyName(names.data?.get(r.symbol)?.name)}</span>
                          </td>
                          <td className="num">{num(r.close)}</td>
                          <td className="num">{r.traded ? <span className={`chip ${tone(r.pct)}`}>{pct(r.pct)}</span> : NONE}</td>
                          <td className="num">{lkr(r.turnover)}</td>
                          <td className="num">{r.range_pos == null ? NONE : `${num(r.range_pos * 100, 0)}%`}</td>
                          <td className="num">{ratio(r.vol_ratio)}</td>
                          <td className={`num ${tone(r.rel_1w)}`}>{pct(r.rel_1w, 1)}</td>
                          <td className={`num ${tone(r.rel_1m)}`}>{pct(r.rel_1m, 1)}</td>
                          <td className={`num ${tone(r.rel_3m)}`}>{pct(r.rel_3m, 1)}</td>
                          {showRatios && <td className="num">{r.ttm_eps != null && r.ttm_eps <= 0 ? t("share.loss") : num(r.pe, 1)}</td>}
                          {showRatios && <td className="num">{num(r.pb, 2)}</td>}
                          {showRatios && <td className="num">{r.dy == null ? NONE : percent(r.dy * 100, 1)}</td>}
                          <td title={notes.join(" ")}>{notes.length ? "⚑" : ""}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <p className="small muted">
                <Term id="range52" />: {t("shares.rangePosHelp")} <Term id="relative" />: {t("shares.relHelp")} ⚑ {t("shares.flagJump")}
                {showRatios && <>{" "}<Term id="pe" />, <Term id="pbv" />, <Term id="dividendYield" />: {t("shares.ratiosHelp")}</>}
              </p>
            </>
          );
        })()
      )}
      <ModelFooter models={["cse_security_metrics", ...(showRatios ? ["cse_fundamentals" as const] : [])]} />
    </>
  );
}
