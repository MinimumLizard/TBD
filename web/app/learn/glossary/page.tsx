import { getTranslations } from "next-intl/server";

import PageHead from "@/components/PageHead";
import { GLOSSARY } from "@/lib/glossary";

export async function generateMetadata() {
  const t = await getTranslations();
  return { title: t("learn.glossaryTitle") };
}

// Plain-language explanations of every term the site uses, in alphabetical order. Each has an anchor, so a term
// anywhere on the site (components/Term.tsx) links straight to it.
export default async function GlossaryPage() {
  const t = await getTranslations();
  const name = (id: (typeof GLOSSARY)[number]) => t(`learn.terms.${id}.name` as never);
  const terms = [...GLOSSARY].sort((a, b) => name(a).localeCompare(name(b), "en"));
  return (
    <>
      <PageHead eyebrow={t("menu.learn.label")} title={t("learn.glossaryTitle")} lead={t("learn.glossaryIntro")} />
      <div className="letters" aria-label={t("learn.glossaryTitle")}>
        {terms.map((id) => (
          <a key={id} href={`#${id}`}>{name(id)}</a>
        ))}
      </div>
      <dl className="glossary card">
        {terms.map((id) => (
          <div key={id} id={id}>
            <dt>{name(id)}</dt>
            <dd>
              <p><strong>{t(`learn.terms.${id}.short` as never)}</strong></p>
              <p className="muted">{t(`learn.terms.${id}.long` as never)}</p>
            </dd>
          </div>
        ))}
      </dl>
    </>
  );
}
