import Link from "next/link";
import { getTranslations } from "next-intl/server";

import AsOf from "@/components/AsOf";
import Locked from "@/components/Locked";
import ModelFooter from "@/components/ModelFooter";
import PreviewNote from "@/components/PreviewNote";
import { bondHref, bondName } from "@/lib/bond-display";
import { bondReference, bondZscores } from "@/lib/data/bonds";
import { date, num, signed } from "@/lib/format";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";

export async function generateMetadata() {
  const t = await getTranslations();
  return { title: t("zscores.title") };
}

export default async function ZscoresPage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const [t, viewer, params] = await Promise.all([getTranslations(), getViewer(), searchParams]);
  const [z, ref] = await Promise.all([bondZscores(viewer), bondReference(viewer)]);
  const name = (isin: string) => bondName(isin, ref.data);
  const maturity = (isin: string) => ref.data?.get(isin)?.maturity_date ?? "";
  // Listed by maturity, never ranked by size: this page describes each bond, it does not pick any out.
  const bonds = [...(z.data?.bonds ?? [])].sort((a, b) => maturity(a.isin).localeCompare(maturity(b.isin)));
  const chosen = bonds.find((b) => b.isin === params.bond)?.isin ?? bonds[0]?.isin;
  const pairs = (z.data?.pairs ?? [])
    .filter((p) => p.isin_a === chosen || p.isin_b === chosen)
    .map((p) => (p.isin_a === chosen ? p : { ...p, isin_a: p.isin_b, isin_b: p.isin_a, spread_bp: -p.spread_bp, deviation_bp: -p.deviation_bp, zscore: -p.zscore }))
    .sort((a, b) => maturity(a.isin_b).localeCompare(maturity(b.isin_b)));
  return (
    <>
      <h1>{t("zscores.title")}</h1>
      <p className="lead">{t("zscores.intro")}</p>
      {!z.access.allowed ? (
        <Locked access={z.access} />
      ) : (
        <>
          <PreviewNote access={z.access} />
          <AsOf day={z.data?.date ?? null} calendar="lk_bond_market" preview={Boolean(z.access.allowed && z.access.maxDate)} />
          <h2>{t("zscores.bondsTitle")}</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{t("bonds.bond")}</th>
                  <th>{t("bonds.maturity")}</th>
                  <th className="num">{t("bonds.residual")}</th>
                  <th className="num">{t("zscores.deviation")}</th>
                  <th className="num">{t("zscores.sd")}</th>
                  <th className="num">{t("zscores.zscore")}</th>
                  <th>{t("zscores.choose")}</th>
                </tr>
              </thead>
              <tbody>
                {bonds.map((r) => (
                  <tr key={r.isin}>
                    <td>
                      <Link href={bondHref(r.isin)}>{name(r.isin)}</Link>
                    </td>
                    <td>{date(maturity(r.isin))}</td>
                    <td className="num">{signed(r.residual_bp, 1)}</td>
                    <td className="num">{signed(r.deviation_bp, 1)}</td>
                    <td className="num">{num(r.sd_bp, 1)}</td>
                    <td className="num">{signed(r.zscore, 2)}</td>
                    <td>
                      <Link href={`/bonds/zscores?bond=${encodeURIComponent(r.isin)}#pairs`} aria-current={r.isin === chosen ? "true" : undefined}>
                        {t("zscores.choose")}
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {chosen && (
            <>
              <h2 id="pairs">{t("zscores.pairsTitle", { bond: name(chosen) })}</h2>
              <p className="small muted">{t("zscores.pairsNote")}</p>
              {pairs.length === 0 ? (
                <p>{t("zscores.pairsNone")}</p>
              ) : (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>{t("zscores.pair")}</th>
                        <th className="num">{t("zscores.spread")}</th>
                        <th className="num">{t("zscores.deviation")}</th>
                        <th className="num">{t("zscores.zscore")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {pairs.map((p) => (
                        <tr key={`${p.isin_a}|${p.isin_b}`}>
                          <td>
                            {name(p.isin_a)} − {name(p.isin_b)}
                          </td>
                          <td className="num">{signed(p.spread_bp, 1)}</td>
                          <td className="num">{signed(p.deviation_bp, 1)}</td>
                          <td className="num">{signed(p.zscore, 2)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
        </>
      )}
      <ModelFooter models={["bond_rv_zscores"]} />
    </>
  );
}
