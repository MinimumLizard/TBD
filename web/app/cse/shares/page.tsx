import Link from "next/link";
import { getTranslations } from "next-intl/server";

import AsOf from "@/components/AsOf";
import Locked from "@/components/Locked";
import ModelFooter from "@/components/ModelFooter";
import Term from "@/components/Term";
import { companyName } from "@/lib/cse-display";
import { type ShareSession, securityNames, shares } from "@/lib/data/cse";
import { NONE, lkr, num, pct, ratio, tone } from "@/lib/format";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";

const SORTS = ["symbol", "pct", "turnover", "range_pos", "vol_ratio", "rel_1w", "rel_1m", "rel_3m"] as const;
type Sort = (typeof SORTS)[number];

export async function generateMetadata() {
  const t = await getTranslations();
  return { title: t("shares.title") };
}

function sortRows(rows: ShareSession[], sort: Sort): ShareSession[] {
  if (sort === "symbol") return rows;
  return [...rows].sort((a, b) => ((b[sort] as number | null) ?? -Infinity) - ((a[sort] as number | null) ?? -Infinity));
}

export default async function SharesPage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const params = await searchParams;
  const sort: Sort = (SORTS as readonly string[]).includes(params.sort ?? "") ? (params.sort as Sort) : "turnover";
  const onlyTraded = params.all !== "1";
  const [t, viewer] = await Promise.all([getTranslations(), getViewer()]);
  const [result, names] = await Promise.all([shares(viewer), securityNames(viewer)]);
  const flag = (r: ShareSession) => {
    const notes = [];
    if ([r.flag_1w, r.flag_1m, r.flag_3m].some((f) => f && f.startsWith("unadjusted"))) notes.push(t("shares.flagJump"));
    if (r.range_flag) notes.push(t("shares.flagRange"));
    return notes;
  };
  const header = (key: Sort, label: string) => (
    <th className={key === "symbol" ? "" : "num"}>
      <Link href={`/cse/shares?sort=${key}${onlyTraded ? "" : "&all=1"}`} aria-current={sort === key ? "true" : undefined}>
        {label}
      </Link>
    </th>
  );
  return (
    <>
      <h1>{t("shares.title")}</h1>
      <p className="lead">{t("shares.intro")}</p>
      {!result.access.allowed ? (
        <Locked access={result.access} />
      ) : (
        (() => {
          const rows = sortRows((result.data?.rows ?? []).filter((r) => !onlyTraded || r.traded), sort);
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
                          <td title={notes.join(" ")}>{notes.length ? "⚑" : ""}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <p className="small muted">
                <Term id="range52" />: {t("shares.rangePosHelp")} <Term id="relative" />: {t("shares.relHelp")} ⚑ {t("shares.flagJump")}
              </p>
            </>
          );
        })()
      )}
      <ModelFooter models={["cse_security_metrics"]} />
    </>
  );
}
