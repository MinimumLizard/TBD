import Link from "next/link";
import { getTranslations } from "next-intl/server";

import Term from "./Term";
import type { Dealing } from "@/lib/data/dealings";
import { date, int, lkr, num } from "@/lib/format";

// Directors' dealings as disclosed, without names: one row per transaction. The side and value come first, so a
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
            <th>{t("dealings.role")}</th>
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
              <td className="small">{t(`dealings.roles.${r.role}` as never)}</td>
              <td className="small">
                {r.account_type === "related" ? <Term id="relatedParty">{t("dealings.accounts.related")}</Term> : t("dealings.accounts.own")}
              </td>
              <td className="small">
                {date(r.announced_date)}
                {r.lag_days != null && <span className="sub">{t("dealings.lagValue", { n: r.lag_days })}</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
