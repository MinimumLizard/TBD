import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { guide } from "@/lib/guides";
import { type Answer, TOOL_KEYS } from "@/lib/paths";

// The visitor's three steps, compact, at the top of their home page.
export default async function PathStrip({ steps }: { steps: Answer["steps"] }) {
  const t = await getTranslations();
  return (
    <section className="path-strip" aria-labelledby="path-title">
      <h2 id="path-title">{t("homes.pathTitle")}</h2>
      <ol>
        {steps.map((s, i) => {
          const g = s.guide ? guide(s.guide) : null;
          const href = g ? `/learn/${g.slug}` : s.page!;
          return (
            <li key={i}>
              <span className="p-step">{t("homes.pathStep", { n: i + 1 })}</span>
              <Link className="p-title" href={href}>{g ? t(`guides.${g.slug}.title` as never) : t(`start.tools.${TOOL_KEYS[s.page!]}` as never)}</Link>
              {s.tool && <Link className="p-tool" href={s.tool}>{t(`start.tools.${TOOL_KEYS[s.tool]}` as never)} →</Link>}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
