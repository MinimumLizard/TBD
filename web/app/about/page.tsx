import { getTranslations } from "next-intl/server";

import Disclaimer from "@/components/Disclaimer";

export async function generateMetadata() {
  const t = await getTranslations();
  return { title: t("about.title") };
}

export default async function AboutPage() {
  const t = await getTranslations();
  const sections = [
    ["about.what", "about.whatBody"],
    ["about.sources", "about.sourcesBody"],
    ["about.tiers", "about.tiersBody"],
    ["about.corrections", "about.correctionsBody"],
  ] as const;
  return (
    <>
      <h1>{t("about.title")}</h1>
      {sections.map(([h, body]) => (
        <section key={h}>
          <h2>{t(h)}</h2>
          <p className="lead">{t(body)}</p>
        </section>
      ))}
      <Disclaimer keys={["general", "model_general", "data_sources"]} />
    </>
  );
}
