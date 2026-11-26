import Link from "next/link";
import { getTranslations } from "next-intl/server";

import Bolt from "@/components/Bolt";
import PageHead from "@/components/PageHead";
import { CODES } from "@/lib/codes";

export const dynamic = "force-dynamic";

export async function generateMetadata() {
  const t = await getTranslations();
  return { title: t("codes.title") };
}

// Cheat codes: public data most people do not know is public (decision 0027). One line each, one tap to the page.
export default async function CodesPage() {
  const t = await getTranslations();
  return (
    <>
      <PageHead eyebrow={t("codes.eyebrow")} title={t("codes.title")} lead={t("codes.lead")} />
      <ul className="codes">
        {CODES.map((c) => (
          <li key={c.key}>
            <Link href={c.href} className="code-card">
              <span className="code-icon"><Bolt size={16} /></span>
              <span className="code-text">
                <span className="code-title">
                  {t(`codes.${c.key}.title` as never)}
                  {c.tier !== "free" && <span className={`tier-pill ${c.tier}`}>{t(`tiers.${c.tier}`)}</span>}
                </span>
                <span className="code-line">{t(`codes.${c.key}.line` as never)}</span>
              </span>
            </Link>
          </li>
        ))}
      </ul>
      <p className="small muted">{t("codes.note")}</p>
    </>
  );
}
