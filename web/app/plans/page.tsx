import Link from "next/link";
import { getTranslations } from "next-intl/server";

import PageHead from "@/components/PageHead";
import Section from "@/components/Section";
import { LEVEL_OF_TIER } from "@/lib/guides";
import { MODEL_NAMES, TIERS, modelEntry } from "@/lib/registry";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";

export async function generateMetadata() {
  const t = await getTranslations();
  return { title: t("plans.title") };
}

const FAQ = ["free", "preview", "advice", "data"] as const;

// The planned tiers: who each is for, what it adds, and its guides. The lists of calculations come from the same
// registry the tier check reads, so this page cannot promise something the server does not enforce.
export default async function PlansPage() {
  const [t, viewer] = await Promise.all([getTranslations(), getViewer()]);
  return (
    <>
      <PageHead eyebrow={t("plans.eyebrow")} title={t("plans.title")} lead={t("plans.intro")}
                meta={<p className="small muted">{t("plans.current", { tier: t(`tiers.${viewer.tier}`) })}</p>} />
      <div className="plans">
        {TIERS.map((tier) => {
          const models = MODEL_NAMES.filter((m) => modelEntry(m).minimum_tier === tier);
          const features = t.raw(`plans.${tier}.features`) as string[];
          const level = LEVEL_OF_TIER[tier];
          return (
            <section key={tier} className={`plan${tier === "plus" ? " featured" : ""}`}>
              <span className={`tier-pill ${tier}`}>{t(`tiers.${tier}`)}</span>
              <h2>{t(`plans.${tier}.tagline`)}</h2>
              <span className="small muted">{tier === "free" ? t("tiers.free") : t("plans.soon")}</span>
              <p className="who">
                <strong>{t("plans.whoTitle")}: </strong>
                {t(`plans.${tier}.who`)}
              </p>
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
              {level && <Link className="more" href={`/learn#${level}`}>{t("plans.guidesLink")} →</Link>}
            </section>
          );
        })}
      </div>
      <div className="section-head">
        <h2>{t("plans.faqTitle")}</h2>
      </div>
      {FAQ.map((q) => (
        <Section key={q} id={`faq-${q}`} title={t(`plans.faq.${q}Q`)}>
          <p style={{ marginBottom: 0 }}>{t(`plans.faq.${q}A`)}</p>
        </Section>
      ))}
    </>
  );
}
