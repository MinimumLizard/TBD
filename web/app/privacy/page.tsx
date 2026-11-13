import { getTranslations } from "next-intl/server";

import PageHead from "@/components/PageHead";

export async function generateMetadata() {
  const t = await getTranslations();
  return { title: t("privacy.title") };
}

interface Part {
  h: string;
  p: string[];
}

// What the site keeps about a visitor, in plain words (decision 0025). A lawyer's view of this text is on the
// switch-on checklist (docs/plan-janu-review.md §5).
export default async function PrivacyPage() {
  const t = await getTranslations();
  const parts = t.raw("privacy.sections") as Part[];
  return (
    <article className="guide">
      <PageHead eyebrow={t("privacy.eyebrow")} title={t("privacy.title")} lead={t("privacy.lead")} />
      {parts.map((part) => (
        <section key={part.h}>
          <h2>{part.h}</h2>
          {part.p.map((para) => <p key={para}>{para}</p>)}
        </section>
      ))}
    </article>
  );
}
