import Link from "next/link";
import { getTranslations } from "next-intl/server";

import AsOf from "@/components/AsOf";
import Locked from "@/components/Locked";
import ModelFooter from "@/components/ModelFooter";
import PreviewNote from "@/components/PreviewNote";
import { bondHref, bondName } from "@/lib/bond-display";
import { bondReference, bondZscores } from "@/lib/data/bonds";
import { num, signed, tone } from "@/lib/format";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";
const PAIRS_SHOWN = 30;

export async function generateMetadata() {
  const t = await getTranslations();
  return { title: t("zscores.title") };
}

export default async function ZscoresPage() {
  const [t, viewer] = await Promise.all([getTranslations(), getViewer()]);
  const [z, ref] = await Promise.all([bondZscores(viewer), bondReference(viewer)]);
  const name = (isin: string) => bondName(isin, ref.data);
  return (
    <>
      <h1>{t("zscores.title")}</h1>
      <p className="lead">{t("zscores.intro")}</p>
      {!z.access.allowed ? (
        <Locked access={z.access} />
      ) : (
        <>
          <PreviewNote access={z.access} />
          <AsOf day={z.data?.date ?? null} calendar="lk_bond_market" />
          <h2>{t("zscores.bondsTitle")}</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{t("bonds.bond")}</th>
                  <th className="num">{t("bonds.residual")}</th>
                  <th className="num">{t("zscores.deviation")}</th>
                  <th className="num">{t("zscores.sd")}</th>
                  <th className="num">{t("zscores.zscore")}</th>
                </tr>
              </thead>
              <tbody>
                {[...(z.data?.bonds ?? [])]
                  .sort((a, b) => Math.abs(b.zscore) - Math.abs(a.zscore))
                  .map((r) => (
                    <tr key={r.isin}>
                      <td>
                        <Link href={bondHref(r.isin)}>{name(r.isin)}</Link>
                      </td>
                      <td className="num">{signed(r.residual_bp, 1)}</td>
                      <td className={`num ${tone(r.deviation_bp)}`}>{signed(r.deviation_bp, 1)}</td>
                      <td className="num">{num(r.sd_bp, 1)}</td>
                      <td className="num">{signed(r.zscore, 2)}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
          <h2>{t("zscores.pairsTitle")}</h2>
          <p className="small muted">{t("zscores.pairsNote")}</p>
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
                {[...(z.data?.pairs ?? [])]
                  .sort((a, b) => Math.abs(b.zscore) - Math.abs(a.zscore))
                  .slice(0, PAIRS_SHOWN)
                  .map((p) => (
                    <tr key={`${p.isin_a}|${p.isin_b}`}>
                      <td>
                        {name(p.isin_a)} − {name(p.isin_b)}
                      </td>
                      <td className="num">{signed(p.spread_bp, 1)}</td>
                      <td className={`num ${tone(p.deviation_bp)}`}>{signed(p.deviation_bp, 1)}</td>
                      <td className="num">{signed(p.zscore, 2)}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      <ModelFooter models={["bond_rv_zscores"]} />
    </>
  );
}
