import { getTranslations } from "next-intl/server";

import type { Granted } from "@/lib/entitlements";
import { date } from "@/lib/format";
import { modelEntry } from "@/lib/registry";

// A free preview: the same outputs, but only up to a date some days back (config/entitlements.yaml).
export default async function PreviewNote({ access }: { access: Granted }) {
  if (!access.maxDate) return null;
  const t = await getTranslations();
  const tier = t(`tiers.${modelEntry(access.model).minimum_tier}`);
  return (
    <div className="notice lock" data-preview={access.model}>
      {t("locked.preview", { days: access.delayDays, date: date(access.maxDate), tier })}
    </div>
  );
}
