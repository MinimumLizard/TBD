import Link from "next/link";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";

import GuideReview from "@/components/GuideReview";
import PageHead from "@/components/PageHead";
import { guide, neighbours } from "@/lib/guides";
import { decodeSegment } from "@/lib/params";

interface Part {
  h: string;
  p: string[];
}

export async function generateMetadata({ params }: { params: Promise<{ guide: string }> }) {
  const slug = decodeSegment((await params).guide);
  const t = await getTranslations();
  return guide(slug) ? { title: t(`guides.${slug}.title` as never) } : {};
}

// One guide: the short version first, then the explanation, what it cannot tell you, and the pages it explains.
// Education only (hard rule 4): guides describe and explain; none says what to do.
export default async function GuidePage({ params }: { params: Promise<{ guide: string }> }) {
  const slug = decodeSegment((await params).guide);
  const g = guide(slug);
  if (!g) notFound();
  const t = await getTranslations();
  const key = (k: string) => `guides.${slug}.${k}` as never;
  const keypoints = t.raw(key("keypoints")) as string[];
  const parts = t.raw(key("sections")) as Part[];
  const limits = t.raw(key("limits")) as string[];
  const { prev, next } = neighbours(slug);
  return (
    <article className="guide">
      <PageHead
        eyebrow={<><Link href={`/learn#${g.level}`}>{t(`guides.levels.${g.level}.title`)}</Link> · {t("ui.minutes", { count: g.minutes })}</>}
        title={t(key("title"))}
        lead={t(key("summary"))}
      />
      <section className="keypoints">
        <h2>{t("guides.inShort")}</h2>
        <ul>
          {keypoints.map((k) => <li key={k}>{k}</li>)}
        </ul>
      </section>
      {parts.map((part) => (
        <section key={part.h}>
          <h2>{part.h}</h2>
          {part.p.map((para) => <p key={para}>{para}</p>)}
        </section>
      ))}
      <section className="limits">
        <h2>{t("guides.limitsTitle")}</h2>
        <ul>
          {limits.map((l) => <li key={l}>{l}</li>)}
        </ul>
      </section>
      <h2>{t("ui.seeItLive")}</h2>
      <p className="related">
        {g.tools.map((tool) => (
          <Link key={tool.href} href={tool.href}>{t(`guides.tools.${tool.key}` as never)} →</Link>
        ))}
      </p>
      <GuideReview page={`/learn/${slug}`} />
      <nav className="guide-nav" aria-label={t("menu.learn.guides.title")}>
        {prev ? <Link href={`/learn/${prev.slug}`}>← {t(`guides.${prev.slug}.title` as never)}</Link> : <span />}
        {next ? <Link href={`/learn/${next.slug}`}>{t(`guides.${next.slug}.title` as never)} →</Link> : <span />}
      </nav>
    </article>
  );
}
