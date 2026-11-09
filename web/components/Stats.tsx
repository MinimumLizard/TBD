import { getTranslations } from "next-intl/server";

import { savingsOverview } from "@/lib/data/savings";
import type { Viewer } from "@/lib/entitlements";
import { monthYear } from "@/lib/format";

export type StatKey = "investors" | "literacy" | "savers";

// The source of each published figure (docs/research/retail-investor-needs-2026-11.md §1).
const SOURCES: Record<Exclude<StatKey, "savers">, string> = {
  investors: "https://echelon.lk/the-cses-mission-turning-citizens-into-shareholders-in-economic-growth/",
  literacy: "https://www.themorning.lk/articles/8KLO0MiNtzYlrdsb3wOq",
};

// "You're not alone" (Janu's review): a few figures that describe where most Sri Lankans are, each with its source.
// The savers' figure is computed by this site (lk_savings_compare, free): one-year fixed deposits since 2003 that
// lost value after tax and inflation.
export default async function Stats({ viewer, keys }: { viewer: Viewer; keys: StatKey[] }) {
  const t = await getTranslations();
  let savers: { lost: number; total: number; first: string } | null = null;
  if (keys.includes("savers")) {
    const overview = await savingsOverview(viewer);
    const s = overview.data?.summary.find((r) => r.horizon_years === 1 && r.instrument === "fd" && r.basis === "real_after_tax");
    if (s && s.n_periods) savers = { lost: s.n_periods - s.n_above_start, total: s.n_periods, first: s.first_start };
  }
  const shown = keys.filter((k) => k !== "savers" || savers);
  if (shown.length === 0) return null;
  return (
    <section className="stats" aria-label={t("start.stats.title")}>
      <h2>{t("start.stats.title")}</h2>
      <div className="stats-row">
        {shown.map((k) => (
          <div key={k} className="stat-card">
            <span className="s-value">
              {k === "savers" && savers ? t("start.stats.savers.value", { lost: savers.lost, total: savers.total }) : t(`start.stats.${k}.value` as never)}
            </span>
            <span className="s-label">
              {k === "savers" && savers ? t("start.stats.savers.label", { first: monthYear(savers.first) }) : t(`start.stats.${k}.label` as never)}
            </span>
            <span className="s-source">
              {k === "savers"
                ? <a href="/learn/savings">{t("start.stats.savers.source")}</a>
                : <a href={SOURCES[k as Exclude<StatKey, "savers">]} rel="noopener noreferrer">{t(`start.stats.${k}.source` as never)}</a>}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}
