import { getTranslations } from "next-intl/server";

import AsOf from "@/components/AsOf";
import Chart from "@/components/Chart";
import Locked from "@/components/Locked";
import ModelFooter from "@/components/ModelFooter";
import PreviewNote from "@/components/PreviewNote";
import { lineOption } from "@/lib/charts";
import { executionGap } from "@/lib/data/bonds";
import { signed } from "@/lib/format";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";

export async function generateMetadata() {
  const t = await getTranslations();
  return { title: t("execution.title") };
}

export default async function ExecutionPage() {
  const [t, viewer] = await Promise.all([getTranslations(), getViewer()]);
  const gap = await executionGap(viewer);
  const rows = gap.data ?? [];
  const last = rows[rows.length - 1];
  return (
    <>
      <h1>{t("execution.title")}</h1>
      <p className="lead">{t("execution.intro")}</p>
      {!gap.access.allowed ? (
        <Locked access={gap.access} />
      ) : (
        <>
          <PreviewNote access={gap.access} />
          <AsOf day={last?.obs_date ?? null} calendar="lk_bond_market" preview={Boolean(gap.access.allowed && gap.access.maxDate)} />
          {last && <p>{t("execution.latest", { gap: signed(last.gap_bp, 1), n: last.n })}</p>}
          <Chart label={t("execution.chart")} option={lineOption([{ name: t("execution.chart"), points: rows.map((r) => [r.obs_date, r.gap_bp]) }], "bp")} />
        </>
      )}
      <ModelFooter models={["bond_execution_gap"]} />
    </>
  );
}
