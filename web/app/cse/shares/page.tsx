import Link from "next/link";
import { getTranslations } from "next-intl/server";

import AsOf from "@/components/AsOf";
import Explain from "@/components/Explain";
import FilterBar from "@/components/FilterBar";
import Locked from "@/components/Locked";
import ModelFooter from "@/components/ModelFooter";
import PageHead from "@/components/PageHead";
import Section from "@/components/Section";
import { companyName, sectorGroup } from "@/lib/cse-display";
import { type CompanyRatios, type ShareSession, ratiosByCompany, securityNames, shares } from "@/lib/data/cse";
import { matchesQuery, param, searchText } from "@/lib/filter";
import { NONE, num, pct, percent, tone } from "@/lib/format";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";

export async function generateMetadata() {
  const t = await getTranslations();
  return { title: t("shares.title") };
}

type Row = ShareSession & Partial<CompanyRatios> & { company: string; sector: string; text: string; show: boolean };

// Finding a share: a search box, a sector filter, and every listed share grouped by its industry group (the 20
// S&P/CSE groups, the same rules as the portfolio lab). The sortable comparison table is /cse/shares/compare.
export default async function SharesPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = await searchParams;
  const query = param(params.q);
  const sectorParam = param(params.sector);
  const [t, viewer] = await Promise.all([getTranslations(), getViewer()]);
  const [result, names, ratios] = await Promise.all([shares(viewer), securityNames(viewer), ratiosByCompany(viewer)]);
  const other = t("shares.otherSector");
  const showRatios = ratios.access.allowed;
  const rows: Row[] = (result.data?.rows ?? []).map((r) => {
    const ref = names.data?.get(r.symbol);
    const company = companyName(ref?.name) ?? r.symbol;
    const sector = sectorGroup(r.symbol, ref?.sector_label) ?? other;
    const text = searchText(r.symbol, r.symbol.split(".")[0], company, sector);
    const own = showRatios && r.symbol.endsWith(".N0000") ? ratios.data?.byCode.get(r.symbol.split(".")[0]) ?? {} : {};
    return { ...r, ...own, company, sector, text, show: matchesQuery(text, query) && (!sectorParam || sector === sectorParam) };
  }).sort((a, b) => a.company.localeCompare(b.company, "en") || a.symbol.localeCompare(b.symbol));
  const sectors = Array.from(new Set(rows.map((r) => r.sector))).sort((a, b) => (a === other ? 1 : b === other ? -1 : a.localeCompare(b)));
  const filtering = query !== "" || sectorParam !== "";
  const median = (xs: number[]) => {
    const s = [...xs].sort((a, b) => a - b);
    return s.length ? (s.length % 2 ? s[(s.length - 1) / 2] : (s[s.length / 2 - 1] + s[s.length / 2]) / 2) : null;
  };
  return (
    <>
      <PageHead eyebrow={t("cse.eyebrow")} title={t("shares.title")} lead={t("shares.introBySector")}
                meta={result.access.allowed ? <AsOf day={result.data?.date ?? null} calendar="cse" /> : null} />
      {!result.access.allowed ? (
        <Locked access={result.access} />
      ) : (
        <>
          <FilterBar scope="share-list" action="/cse/shares" placeholder={t("shares.searchPlaceholder")} query={query}
                     selects={[{ name: "sector", label: t("shares.sector"), all: t("shares.allSectors"), value: sectorParam,
                                 options: sectors.map((x) => ({ value: x, label: x })) }]}
                     shown={rows.filter((r) => r.show).length} total={rows.length} />
          <p className="small">
            <Link href="/cse/shares/compare">{t("shares.compareLink")} →</Link>
          </p>
          <div id="share-list">
            {sectors.map((sector) => {
              const inSector = rows.filter((r) => r.sector === sector);
              const traded = inSector.filter((r) => r.traded && r.pct != null);
              const up = traded.filter((r) => (r.pct ?? 0) > 0).length;
              const down = traded.filter((r) => (r.pct ?? 0) < 0).length;
              const med = median(traded.map((r) => r.pct as number));
              const any = inSector.some((r) => r.show);
              const slug = searchText(sector).replace(/ /g, "-");
              return (
                <Section key={sector} id={`sector-${slug}`} group hidden={!any} open={filtering && any}
                         title={sector}
                         summary={t("shares.sectorSum", { count: inSector.length, up, down, median: med == null ? NONE : pct(med) })}>
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>{t("shares.company")}</th>
                          <th className="num">{t("shares.close")}</th>
                          <th className="num">{t("shares.changePct")}</th>
                          <th className="num">{t("shares.ret3m")}</th>
                          {showRatios && <th className="num">{t("shares.pe")}</th>}
                          {showRatios && <th className="num">{t("shares.dy")}</th>}
                        </tr>
                      </thead>
                      <tbody>
                        {inSector.map((r) => (
                          <tr key={r.symbol} data-search={r.text} data-sector={r.sector} hidden={!r.show}>
                            <td className="names">
                              <Link href={`/cse/shares/${encodeURIComponent(r.symbol)}`}>{r.company}</Link>
                              <span className="sub">{r.symbol}</span>
                            </td>
                            <td className="num">{num(r.close)}</td>
                            <td className="num">{r.traded ? <span className={`chip ${tone(r.pct)}`}>{pct(r.pct)}</span> : <span className="small muted">{t("common.notTraded")}</span>}</td>
                            <td className={`num ${tone(r.ret_3m)}`}>{pct(r.ret_3m, 1)}</td>
                            {showRatios && <td className="num">{r.ttm_eps != null && r.ttm_eps <= 0 ? t("share.loss") : num(r.pe, 1)}</td>}
                            {showRatios && <td className="num">{r.dy == null ? NONE : percent(r.dy * 100, 1)}</td>}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Section>
              );
            })}
            {rows.length > 0 && !rows.some((r) => r.show) && <p className="muted">{t("shares.noMatch")}</p>}
          </div>
          <Explain why={t("shares.why")} how={<p>{t("shares.howBySector")}</p>}
                   related={[{ href: "/learn/shares-basics", label: t("share.guideShares") }, { href: "/learn/company-figures", label: t("share.guideFigures") }]} />
        </>
      )}
      <ModelFooter models={["cse_security_metrics", ...(showRatios ? ["cse_fundamentals" as const] : [])]} />
    </>
  );
}
