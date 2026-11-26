import Link from "next/link";
import { getTranslations } from "next-intl/server";

import type { Denied } from "@/lib/entitlements";

// A one-line lock for a column or detail a page leaves out below its tier (e.g. P/E on the share lists): what it is
// and which tier shows it, as a glowing chip to the plans. The data was never read.
export default async function LockedLine({ access, what }: { access: Denied; what: string }) {
  const t = await getTranslations();
  return (
    <p className="unlock" data-locked={access.model}>
      <Link href="/plans" className="glow-chip small">{t("locked.line", { what, tier: t(`tiers.${access.requiredTier}`) })} →</Link>
    </p>
  );
}
