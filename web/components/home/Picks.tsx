import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { guide } from "@/lib/guides";
import { MENUS } from "@/lib/menu";

const MENU_ITEMS = new Map(MENUS.flatMap((m) => m.items.map((i) => [i.href, { menu: m.key, ...i }] as const)));

// "Read next": a few guides, each with its level and reading time.
export async function GuidePicks({ slugs }: { slugs: string[] }) {
  const t = await getTranslations();
  const guides = slugs.map(guide).filter((g) => g !== undefined);
  if (guides.length === 0) return null;
  return (
    <section>
      <div className="section-head"><h2>{t("homes.guidesTitle")}</h2><Link className="more" href="/learn">{t("home.learnAll")} →</Link></div>
      <div className="picks">
        {guides.map((g) => (
          <Link key={g.slug} href={`/learn/${g.slug}`}>
            <span className="k">{t(`guides.levels.${g.level}.title`)} · {t("ui.minutes", { count: g.minutes })}</span>
            <span className="c-title">{t(`guides.${g.slug}.title` as never)}</span>
            <span className="c-desc">{t(`guides.${g.slug}.summary` as never)}</span>
          </Link>
        ))}
      </div>
    </section>
  );
}

// "Pages picked for you": pages of the site, named as in the menus, with the tier of a page whose main content is paid.
export async function ToolPicks({ hrefs }: { hrefs: string[] }) {
  const t = await getTranslations();
  const items = hrefs.map((h) => MENU_ITEMS.get(h)).filter((i) => i !== undefined);
  if (items.length === 0) return null;
  return (
    <section>
      <div className="section-head"><h2>{t("homes.toolsTitle")}</h2></div>
      <div className="picks">
        {items.map((i) => (
          <Link key={i.href} href={i.href}>
            <span className="c-title">
              {t(`menu.${i.menu}.${i.key}.title` as never)}
              {i.tier && <span className={`tier-pill ${i.tier}`}>{t(`tiers.${i.tier}`)}</span>}
            </span>
            <span className="c-desc">{t(`menu.${i.menu}.${i.key}.desc` as never)}</span>
          </Link>
        ))}
      </div>
    </section>
  );
}
