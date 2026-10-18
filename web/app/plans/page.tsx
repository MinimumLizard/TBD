import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { MODEL_NAMES, TIERS, modelEntry } from "@/lib/registry";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";

export async function generateMetadata() {
  const t = await getTranslations();
  return { title: t("plans.title") };
}

// The planned tiers. The lists of calculations come from the same registry the tier check reads, so this page
// cannot promise something the server does not enforce.
export default async function PlansPage() {
  const [t, viewer] = await Promise.all([getTranslations(), getViewer()]);
  return (
    <>
      <h1>{t("plans.title")}</h1>
      <p className="lead">{t("plans.intro")}</p>
      <p className="small muted">{t("plans.current", { tier: t(`tiers.${viewer.tier}`) })}</p>
      <div className="plans">
        {TIERS.map((tier) => {
          const models = MODEL_NAMES.filter((m) => modelEntry(m).minimum_tier === tier);
          const features = t.raw(`plans.${tier}.features`) as string[];
          return (
            <section key={tier} className={`plan${tier === "plus" ? " featured" : ""}`}>
              <span className={`tier-pill ${tier}`}>{t(`tiers.${tier}`)}</span>
              <h2>{t(`plans.${tier}.tagline`)}</h2>
              <span className="small muted">{tier === "free" ? t("tiers.free") : t("plans.soon")}</span>
              <strong className="small">{t("plans.includes")}</strong>
              <ul>
                {features.map((f) => <li key={f}>{f}</li>)}
              </ul>
              {models.length > 0 && (
                <>
                  <strong className="small">{t("plans.models")}</strong>
                  <ul className="small">
                    {models.map((m) => (
                      <li key={m}><Link href={`/methods/${m}`}>{t(modelEntry(m).title_key as never)}</Link></li>
                    ))}
                  </ul>
                </>
              )}
            </section>
          );
        })}
      </div>
    </>
  );
}
