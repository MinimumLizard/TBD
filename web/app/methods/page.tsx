import Link from "next/link";
import { getTranslations } from "next-intl/server";

import PageHead from "@/components/PageHead";

import { MODEL_NAMES, modelEntry } from "@/lib/registry";

export async function generateMetadata() {
  const t = await getTranslations();
  return { title: t("methods.title") };
}

export default async function MethodsPage() {
  const t = await getTranslations();
  const markets = ["cse", "lk_bonds", "lk_savings"] as const;
  return (
    <>
      <PageHead eyebrow={t("methods.eyebrow")} title={t("methods.title")} lead={t("methods.intro")} />
      {markets.map((market) => (
        <section key={market}>
          <h2>{t(`methods.market_${market}`)}</h2>
          <ul>
            {MODEL_NAMES.filter((m) => modelEntry(m).market === market).map((m) => (
              <li key={m}>
                <Link href={`/methods/${m}`}>{t(modelEntry(m).title_key as never)}</Link>{" "}
                <span className="badge">{t("methods.availableFrom", { tier: t(`tiers.${modelEntry(m).minimum_tier}`) })}</span>
                <br />
                <span className="small muted">{t(modelEntry(m).summary_key as never)}</span>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </>
  );
}
