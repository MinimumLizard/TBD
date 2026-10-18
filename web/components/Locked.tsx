import Link from "next/link";
import { getTranslations } from "next-intl/server";

import type { Denied } from "@/lib/entitlements";

// Shown instead of a model's data when the visitor's tier does not include it. The data was never read.
export default async function Locked({ access }: { access: Denied }) {
  const t = await getTranslations();
  const tier = t(`tiers.${access.requiredTier}`);
  return (
    <div className={`locked ${access.requiredTier}`} data-locked={access.model}>
      <span className="tier-name">
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M7 10V7a5 5 0 0 1 10 0v3" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          <rect x="5" y="10" width="14" height="10" rx="2.5" fill="currentColor" />
        </svg>
        {t("locked.title", { tier })}
      </span>
      <span>{t(`models.${access.model}.summary` as never)}</span>
      <span className="muted small">
        {t("locked.body", { tier })} <Link href="/plans">{t("locked.plans")} →</Link>
      </span>
    </div>
  );
}
