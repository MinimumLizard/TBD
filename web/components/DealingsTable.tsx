import Link from "next/link";
import { getTranslations } from "next-intl/server";

import Term from "./Term";
import type { Dealing } from "@/lib/data/dealings";
import { date, int, lkr, num } from "@/lib/format";

// Directors' dealings as disclosed, with the names the company filed: one row per transaction. The side and value come first, so a
// phone shows them without scrolling the table sideways.
export default async function DealingsTable({ rows, showCompany = false }: { rows: Dealing[]; showCompany?: boolean }) {
  const t = await getTranslations();
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>{t("dealings.date")}</th>
            {showCompany && <th>{t("dealings.company")}</th>}
            <th>{t("dealings.side")}</th>
            <th className="num">{t("dealings.value")}</th>
            <th className="num">{t("dealings.shares")}</th>
            <th className="num">{t("dealings.price")}</th>
            <th>{t("dealings.director")}</th>
            <th>{t("dealings.account")}</th>
            <th>{t("dealings.disclosed")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.transaction_id}>
              <td>{date(r.deal_date)}</td>
              {showCompany && (
                <td>
                  <Link href={`/cse/shares/${encodeURIComponent(`${r.symbol}.N0000`)}`}>{r.symbol}</Link>
                  <span className="sub">{r.company}</span>
                </td>
              )}
              <td>{t(`dealings.sides.${r.side}` as never)}</td>
              <td className="num">{lkr(r.value)}</td>
              <td className="num">{int(r.quantity)}</td>
              <td className="num">{num(r.price)}</td>
              <td className="small names">
                {r.director ?? ""}
                <span className="sub">{t(`dealings.roles.${r.role}` as never)}</span>
              </td>
              <td className="small names">
                {r.account_type === "related" ? (
                  <>
                    {r.account ?? ""}
                    <span className="sub"><Term id="relatedParty">{t("dealings.accounts.related")}</Term></span>
                  </>
                ) : t("dealings.accounts.own")}
              </td>
              <td className="small">
                {date(r.announced_date)}
                {r.lag_days != null && <span className="sub">{t("dealings.lagValue", { n: r.lag_days })}</span>}
                {r.source_url && <span className="sub"><a href={r.source_url} rel="noopener noreferrer" target="_blank">{t("dealings.notice")}</a></span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
