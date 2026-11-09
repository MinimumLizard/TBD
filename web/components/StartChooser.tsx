import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { PERSONAS } from "@/lib/paths";

// "Where are you starting from?": the first question of the starting paths (lib/paths.ts), on the home page and on
// /start. Four plain links, so it works without JavaScript; the one most visitors choose is marked.
export default async function StartChooser() {
  const t = await getTranslations();
  return (
    <div className="chooser">
      {PERSONAS.map((p) => (
        <Link key={p.key} href={`/start/${p.key}`} className={p.key === "curious" ? "popular" : undefined}>
          {p.key === "curious" && <span className="tag">{t("start.popular")}</span>}
          <span className="c-title">{t(`start.types.${p.key}.title` as never)}</span>
          <span className="c-desc">{t(`start.types.${p.key}.desc` as never)}</span>
        </Link>
      ))}
    </div>
  );
}
