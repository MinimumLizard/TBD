import { getTranslations } from "next-intl/server";

import Locked from "./Locked";
import Term from "./Term";
import type { CompanyFigures as Figures } from "@/lib/data/cse";
import type { Result } from "@/lib/data/common";
import { date, num, percent } from "@/lib/format";

// The share page's "Company figures": P/E, P/B, ROE, EPS and net assets per share, dividend yield, from the
// company's interim reports (cse_fundamentals), with the report they came from.
export default async function CompanyFigures({ result, symbol }: { result: Result<Figures | null>; symbol: string }) {
  const t = await getTranslations();
  if (!result.access.allowed) return <Locked access={result.access} />;
  const f = result.data;
  if (!f || (f.nav == null && f.ttm_eps == null)) return <p className="muted">{t("share.figuresNone")}</p>;
  const loss = f.ttm_eps != null && f.ttm_eps <= 0;
  const tile = (term: Parameters<typeof Term>[0]["id"], label: string, value: string, sub?: string | null) => (
    <div className="tile stat">
      <span className="label"><Term id={term}>{label}</Term></span>
      <span className="value">{value}</span>
      {sub && <span className="sub">{sub}</span>}
    </div>
  );
  return (
    <>
      <div className="tiles">
        {tile("pe", t("share.pe"), loss ? t("share.loss") : num(f.pe, 1))}
        {tile("pbv", t("share.pb"), num(f.pb, 2))}
        {tile("roe", t("share.roe"), f.roe == null ? num(null) : percent(f.roe * 100, 1))}
        {tile("eps", t("share.ttmEps"), f.ttm_eps == null ? num(null) : `Rs ${num(f.ttm_eps, 2)}`,
              f.ttm_to ? t("share.ttmTo", { date: date(f.ttm_to) }) : null)}
        {tile("navPerShare", t("share.nav"), f.nav == null ? num(null) : `Rs ${num(f.nav, 2)}`,
              f.nav_period ? t("share.navAt", { date: date(f.nav_period) }) : null)}
        {tile("dividendYield", t("share.dy"), f.dy == null ? num(null) : percent(f.dy * 100, 2),
              f.div_ttm ? t("share.divTtm", { amount: num(f.div_ttm, 2) }) : null)}
      </div>
      {f.ttm_eps == null && <p className="small muted">{t("share.ttmMissing")}</p>}
      <p className="small muted">
        {f.report_period && t("share.report", { date: date(f.report_period) })}
        {f.report_url && (
          <>
            {" · "}
            <a href={f.report_url} rel="noopener noreferrer">{t("share.reportLink")}</a>
          </>
        )}
        {" "}
        {t("share.figuresNote")}
        {symbol.endsWith(".X0000") ? ` ${t("share.votingPriceNote")}` : ""}
      </p>
    </>
  );
}
