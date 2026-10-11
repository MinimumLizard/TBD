import { getTranslations } from "next-intl/server";

import { date } from "@/lib/format";
import { sessionsBehind } from "@/lib/freshness";

// "Data for <session>", and a warning when the data is behind the market calendar. Computed on the server.
export default async function AsOf({ day, calendar }: { day: string | null; calendar: "cse" | "lk_bond_market" }) {
  const t = await getTranslations();
  if (!day) return <p className="asof">{t("common.noData")}</p>;
  const behind = sessionsBehind(calendar, day);
  return (
    <>
      <p className="asof">{t("common.asOf", { date: date(day) })}</p>
      {behind > 0 && <div className="notice warn">{t("common.behind", { count: behind })}</div>}
    </>
  );
}
