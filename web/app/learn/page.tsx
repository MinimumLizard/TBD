import { getTranslations } from "next-intl/server";

import { GLOSSARY } from "@/lib/glossary";

export async function generateMetadata() {
  const t = await getTranslations();
  return { title: t("learn.title") };
}

// Plain-language explanations of every term the site uses. Each has an anchor, so a term anywhere links here.
export default async function LearnPage() {
  const t = await getTranslations();
  return (
    <>
      <h1>{t("learn.title")}</h1>
      <p className="lead">{t("learn.intro")}</p>
      <div className="letters" aria-label={t("learn.title")}>
        {GLOSSARY.map((id) => (
          <a key={id} href={`#${id}`}>{t(`learn.terms.${id}.name` as never)}</a>
        ))}
      </div>
      <div className="learn-grid">
        {GLOSSARY.map((id) => (
          <section key={id} id={id} className="card">
            <h2 style={{ fontSize: "1.05rem" }}>{t(`learn.terms.${id}.name` as never)}</h2>
            <p><strong>{t(`learn.terms.${id}.short` as never)}</strong></p>
            <p className="muted" style={{ marginBottom: 0 }}>{t(`learn.terms.${id}.long` as never)}</p>
          </section>
        ))}
      </div>
    </>
  );
}
