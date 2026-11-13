import Link from "next/link";
import { getTranslations } from "next-intl/server";

import Locked from "@/components/Locked";
import StatTile from "@/components/StatTile";
import Term from "@/components/Term";
import { savingsOverview } from "@/lib/data/savings";
import type { Viewer } from "@/lib/entitlements";
import { monthYear, pct, percent } from "@/lib/format";

// What savings earn today, next to inflation: the latest month with every figure published (lk_savings_compare).
export default async function SavingsSnapshot({ viewer }: { viewer: Viewer }) {
  const [t, overview] = await Promise.all([getTranslations(), savingsOverview(viewer)]);
  if (!overview.access.allowed) return <Locked access={overview.access} />;
  const latest = overview.data?.rates.find((r) => r.month === overview.data?.through) ?? null;
  if (!latest) return null;
  const month = monthYear(latest.month);
  return (
    <section className="card">
      <div className="card-head">
        <h2>{t("homes.savingsTitle")}</h2>
        <Link className="more" href="/learn/savings">{t("homes.savingsMore")} →</Link>
      </div>
      <div className="tiles">
        <StatTile label={t("savings.fdRateTile")} value={percent(latest.fd_rate_pct, 2)} note={<>{t("savings.fdRateNote", { month })} · <Term id="awfdr">{t("common.whatIsThis")}</Term></>} />
        <StatTile label={t("savings.billTile")} value={percent(latest.bill_rate_pct, 2)} note={<>{t("savings.billNote", { month })} · <Term id="treasuryBill" /></>} />
        <StatTile label={t("savings.inflationTile")} value={pct(latest.inflation_yoy, 1).replace(/^\+/, "")} note={<>{t("savings.inflationNote", { month })} · <Term id="inflation" /></>} />
      </div>
      <p className="small muted" style={{ marginTop: 12 }}>{t("homes.savingsWhy")}</p>
    </section>
  );
}
