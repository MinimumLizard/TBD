import { getTranslations } from "next-intl/server";

import type { Denied } from "@/lib/entitlements";

// Shown instead of a model's data when the visitor's tier does not include it. The data was never read.
export default async function Locked({ access }: { access: Denied }) {
  const t = await getTranslations();
  const tier = t(`tiers.${access.requiredTier}`);
  return (
    <div className="notice lock" data-locked={access.model}>
      <strong>{t("locked.title", { tier })}</strong>
      {t("locked.body", { tier })}
    </div>
  );
}
