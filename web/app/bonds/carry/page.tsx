import Link from "next/link";
import { getTranslations } from "next-intl/server";

import AsOf from "@/components/AsOf";
import Locked from "@/components/Locked";
import ModelFooter from "@/components/ModelFooter";
import PreviewNote from "@/components/PreviewNote";
import { bondHref, bondName } from "@/lib/bond-display";
import { bondCarry, bondReference } from "@/lib/data/bonds";
import { date, num, percent, signed, tone } from "@/lib/format";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";

export async function generateMetadata() {
  const t = await getTranslations();
  return { title: t("carry.title") };
}

export default async function CarryPage() {
  const [t, viewer] = await Promise.all([getTranslations(), getViewer()]);
  const [carry, ref] = await Promise.all([bondCarry(viewer), bondReference(viewer)]);
  const f = carry.data?.funding;
  return (
    <>
      <h1>{t("carry.title")}</h1>
      <p className="lead">{t("carry.intro")}</p>
      {!carry.access.allowed ? (
        <Locked access={carry.access} />
      ) : (
        <>
          <PreviewNote access={carry.access} />
          <AsOf day={carry.data?.date ?? null} calendar="lk_bond_market" />
          {f && <p className="small">{t("carry.funding", { rate: percent(f.rate_pct, 3), bill: percent(f.bill_pct, 3), date: date(f.bill_as_of) })}</p>}
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{t("bonds.bond")}</th>
                  <th className="num">{t("carry.entry")}</th>
                  <th className="num">{t("carry.price")}</th>
                  <th className="num">{t("carry.duration")}</th>
                  <th className="num">{t("carry.carry")}</th>
                  <th className="num">{t("carry.roll")}</th>
                  <th className="num">{t("carry.total")}</th>
                  <th className="num">{t("carry.perDuration")}</th>
                </tr>
              </thead>
              <tbody>
                {[...(carry.data?.rows ?? [])]
                  .sort((a, b) => a.duration - b.duration)
                  .map((r) => (
                    <tr key={r.isin}>
                      <td>
                        <Link href={bondHref(r.isin)}>{bondName(r.isin, ref.data)}</Link>
                      </td>
                      <td className="num">{percent(r.entry_yield, 3)}</td>
                      <td className="num">{num(r.price, 2)}</td>
                      <td className="num">{num(r.duration, 2)}</td>
                      <td className={`num ${tone(r.carry_bp)}`}>{signed(r.carry_bp, 0)}</td>
                      <td className={`num ${tone(r.roll_bp)}`}>{signed(r.roll_bp, 0)}</td>
                      <td className={`num ${tone(r.total_bp)}`}>{signed(r.total_bp, 0)}</td>
                      <td className={`num ${tone(r.per_duration_bp)}`}>{signed(r.per_duration_bp, 1)}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      <ModelFooter models={["bond_carry"]} />
    </>
  );
}
