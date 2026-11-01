import Link from "next/link";
import { getTranslations } from "next-intl/server";

import PageHead from "@/components/PageHead";
import { GUIDES, LEVELS } from "@/lib/guides";

export async function generateMetadata() {
  const t = await getTranslations();
  return { title: t("learn.title") };
}

const TIER_OF_LEVEL = { basics: "free", deeper: "plus", advanced: "pro" } as const;

// The Learn hub: guides at three levels, each level matching a tier's tools. Every guide is free to read.
export default async function LearnPage() {
  const t = await getTranslations();
  return (
    <>
      <PageHead eyebrow={t("menu.learn.label")} title={t("learn.title")} lead={t("learn.intro")} />
      {LEVELS.map((level) => (
        <section key={level} id={level} style={{ scrollMarginTop: 90 }}>
          <div className="level-head">
            <h2>{t(`guides.levels.${level}.title`)}</h2>
            <span className={`tier-pill ${TIER_OF_LEVEL[level]}`}>{t(`guides.levels.${level}.tools`)}</span>
          </div>
          <p className="muted" style={{ marginTop: -4 }}>{t(`guides.levels.${level}.desc`)}</p>
          <div className="learn-cards">
            {GUIDES.filter((g) => g.level === level).map((g) => (
              <Link key={g.slug} href={`/learn/${g.slug}`} className="card">
                <span className="kicker">{t("ui.minutes", { count: g.minutes })}</span>
                <strong className="display">{t(`guides.${g.slug}.title` as never)}</strong>
                <span className="muted small">{t(`guides.${g.slug}.summary` as never)}</span>
              </Link>
            ))}
            {level === "basics" && (
              <Link href="/learn/savings" className="card">
                <span className="kicker">{t("learn.savingsKicker")}</span>
                <strong className="display">{t("learn.savingsGuide")}</strong>
                <span className="muted small">{t("learn.savingsGuideBody")}</span>
              </Link>
            )}
          </div>
        </section>
      ))}
      <div className="section-head">
        <h2>{t("learn.moreTitle")}</h2>
      </div>
      <div className="tier-strip">
        <div>
          <Link href="/learn/glossary" className="display" style={{ fontSize: "1.1rem", fontWeight: 600 }}>{t("menu.learn.glossary.title")}</Link>
          <p>{t("menu.learn.glossary.desc")}</p>
        </div>
        <div>
          <Link href="/methods" className="display" style={{ fontSize: "1.1rem", fontWeight: 600 }}>{t("menu.learn.methods.title")}</Link>
          <p>{t("menu.learn.methods.desc")}</p>
        </div>
        <div>
          <Link href="/about" className="display" style={{ fontSize: "1.1rem", fontWeight: 600 }}>{t("menu.learn.about.title")}</Link>
          <p>{t("menu.learn.about.desc")}</p>
        </div>
      </div>
    </>
  );
}
