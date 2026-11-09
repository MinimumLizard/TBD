import Link from "next/link";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";

import PageHead from "@/components/PageHead";
import { decodeSegment } from "@/lib/params";
import { persona } from "@/lib/paths";

export async function generateMetadata({ params }: { params: Promise<{ type: string }> }) {
  const p = persona(decodeSegment((await params).type));
  const t = await getTranslations();
  return p ? { title: t(`start.questions.${p.key}.question` as never) } : {};
}

// The second question: one that fits the first answer (lib/paths.ts).
export default async function StartQuestionPage({ params }: { params: Promise<{ type: string }> }) {
  const p = persona(decodeSegment((await params).type));
  if (!p) notFound();
  const t = await getTranslations();
  return (
    <>
      <PageHead eyebrow={`${t("start.eyebrow")} · ${t(`start.types.${p.key}.short` as never)}`}
                title={t(`start.questions.${p.key}.question` as never)}
                meta={<p className="small muted">{t("start.stepOf", { n: 2 })}</p>} />
      <div className="chooser answers">
        {p.answers.map((a) => (
          <Link key={a.key} href={`/start/${p.key}/${a.key}`}>
            <span className="c-title">{t(`start.questions.${p.key}.${a.key}` as never)}</span>
          </Link>
        ))}
      </div>
      <p className="small"><Link href="/start">← {t("start.back")}</Link></p>
    </>
  );
}
