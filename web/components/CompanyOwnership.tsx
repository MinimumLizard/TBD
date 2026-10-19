import Link from "next/link";
import { getTranslations } from "next-intl/server";

import Locked from "./Locked";
import Term from "./Term";
import type { CompanyOwnership as Ownership } from "@/lib/data/cse";
import type { Result } from "@/lib/data/common";
import { date, percent } from "@/lib/format";

const TYPES = ["listed", "company", "institution", "individual", "joint", "estate", "trust", "nominee", "own_shares"] as const;

// The share page's "Who owns it" (cse_ownership): company-level figures only. The model names a holder only when it is
// a company, a fund or the state; otherwise this panel shows its type ("an individual"), never a name.
export default async function CompanyOwnership({ result }: { result: Result<Ownership | null> }) {
  const t = await getTranslations();
  if (!result.access.allowed) return <Locked access={result.access} />;
  const o = result.data;
  if (!o) return <p className="muted">{t("share.ownersNone")}</p>;
  if (o.top20_pct == null) {
    const key = o.report_status === "ok" || !["no_report", "no_text", "no_table", "download_failed"].includes(o.report_status)
      ? "unverified" : o.report_status;
    return <p className="muted">{t(`share.ownersStatus.${key}` as never)}</p>;
  }
  const typeName = (type: string | null) => (type ? t(`share.ownerTypeOne.${type}` as never) : "");
  const byType = TYPES.map((type) => [type, (o as unknown as Record<string, number | null>)[`pct_${type}`]] as const)
    .filter(([, v]) => v != null && v > 0)
    .sort((a, b) => (b[1] ?? 0) - (a[1] ?? 0));
  const owner = o.controller_name ?? typeName(o.controller_type);
  return (
    <>
      <div className="tiles">
        <div className="tile stat">
          <span className="label">{t("share.top20")}</span>
          <span className="value">{percent(o.top20_pct, 1)}</span>
        </div>
        <div className="tile stat">
          <span className="label"><Term id="freeFloat">{t("share.freeFloat")}</Term></span>
          <span className="value">{percent(o.free_float_pct, 1)}</span>
        </div>
      </div>
      <h3>{t("share.byType")}</h3>
      <div className="table-wrap">
        <table>
          <tbody>
            {byType.map(([type, v]) => (
              <tr key={type}>
                <td>{t(`share.ownerTypes.${type}` as never)}</td>
                <td className="num">{percent(v, 2)}</td>
                <td style={{ width: "40%" }} aria-hidden="true">
                  <div className="breadth"><span className="b-flat" style={{ width: `${Math.min(100, v ?? 0)}%` }} /></div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <dl className="facts" style={{ marginTop: 16 }}>
        <dt>{t("share.control")}</dt>
        <dd>
          {o.control_level === "controlled" || o.control_level === "influence"
            ? t(`share.${o.control_level}`, { owner, pct: percent(o.control_pct, 2) })
            : t("share.noControl")}
        </dd>
        <dt><Term id="ownershipGroup">{t("share.group")}</Term></dt>
        <dd>
          {o.group_size > 1
            ? o.group_head_name
              ? t("share.groupNamed", { name: o.group_head_name, count: o.group_size })
              : t("share.groupUnnamed", { owner: typeName(o.group_head_type), count: o.group_size })
            : t("share.groupAlone")}
          {o.group_members.length > 0 && (
            <span className="sub">
              {t("share.groupMembers")}:{" "}
              {o.group_members.map((code, i) => (
                <span key={code}>
                  {i > 0 && ", "}
                  <Link href={`/cse/shares/${encodeURIComponent(`${code}.N0000`)}`}>{code}</Link>
                </span>
              ))}
            </span>
          )}
        </dd>
      </dl>
      <p className="small muted">
        {o.period_date && t("share.ownersNote", { date: date(o.period_date) })}
        {o.source_url && (
          <>
            {" · "}
            <a href={o.source_url} rel="noopener noreferrer">{t("share.reportLink")}</a>
          </>
        )}
        {" "}
        {t("share.freeFloatNote")}
      </p>
    </>
  );
}
