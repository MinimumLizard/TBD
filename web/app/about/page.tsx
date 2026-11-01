import { getTranslations } from "next-intl/server";

import Disclaimer from "@/components/Disclaimer";
import PageHead from "@/components/PageHead";

export async function generateMetadata() {
  const t = await getTranslations();
  return { title: t("about.title") };
}

export default async function AboutPage() {
  const t = await getTranslations();
  const sections = [
    ["about.what", "about.whatBody"],
    ["about.differ", "about.differBody"],
    ["about.sources", "about.sourcesBody"],
    ["about.tiers", "about.tiersBody"],
    ["about.corrections", "about.correctionsBody"],
  ] as const;
  return (
    <>
      <PageHead eyebrow={t("about.eyebrow")} title={t("about.title")} lead={t("about.lead")} />
      <div className="guide">
        {sections.map(([h, body]) => (
          <section key={h}>
            <h2>{t(h)}</h2>
            <p>{t(body)}</p>
          </section>
        ))}
      </div>
      <Disclaimer keys={["general", "model_general", "data_sources"]} />
    </>
  );
}
