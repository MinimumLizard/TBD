import { getTranslations } from "next-intl/server";

import Brief from "@/components/Brief";
import { date } from "@/lib/format";
import type { Overview } from "@/lib/overview";

// "Today in brief": the day in a few plain sentences.
export default async function MarketBrief({ o }: { o: Overview }) {
  const t = await getTranslations();
  const when = o.session || o.fit ? t("home.when", { cse: date(o.session?.session_date), bonds: date(o.fit?.obs_date) }) : null;
  return <Brief title={t("home.briefTitle")} lines={o.summary.map((line) => t(line.key as never, line.values as never))} when={when} />;
}
