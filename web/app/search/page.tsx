import Link from "next/link";
import { getTranslations } from "next-intl/server";

import FilterBar from "@/components/FilterBar";
import PageHead from "@/components/PageHead";
import { bondHref, bondName, isSynthetic } from "@/lib/bond-display";
import { companyName, sectorGroup } from "@/lib/cse-display";
import { bondReference } from "@/lib/data/bonds";
import { securityNames } from "@/lib/data/cse";
import { matchesQuery, param, searchText } from "@/lib/filter";
import { date } from "@/lib/format";
import { GLOSSARY } from "@/lib/glossary";
import { GUIDES } from "@/lib/guides";
import { MENUS } from "@/lib/menu";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";

export async function generateMetadata() {
  const t = await getTranslations();
  return { title: t("search.title") };
}

interface Item {
  href: string;
  title: string;
  sub: string;
  text: string;
}

// One place to find anything on the site: every share, every government bond, every guide, glossary term and page.
// Everything is listed; the query hides what does not match (on the server, and as the visitor types).
export default async function SearchPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const query = param((await searchParams).q);
  const [t, viewer] = await Promise.all([getTranslations(), getViewer()]);
  const [names, bonds] = await Promise.all([securityNames(viewer), bondReference(viewer)]);
  const item = (href: string, title: string, sub: string, ...extra: (string | null | undefined)[]): Item =>
    ({ href, title, sub, text: searchText(title, sub, ...extra) });

  const groups: { key: string; items: Item[] }[] = [
    {
      key: "shares",
      items: [...(names.data?.values() ?? [])]
        .filter((r) => /\.(N|X)0000$/.test(r.symbol))
        .map((r) => {
          const name = companyName(r.name) ?? r.symbol;
          const sector = sectorGroup(r.symbol, r.sector_label) ?? "";
          return item(`/cse/shares/${encodeURIComponent(r.symbol)}`, name, [r.symbol, sector].filter(Boolean).join(" · "), r.symbol.split(".")[0]);
        })
        .sort((a, b) => a.title.localeCompare(b.title, "en")),
    },
    {
      key: "bonds",
      items: [...(bonds.data?.values() ?? [])]
        .sort((a, b) => (a.maturity_date ?? "").localeCompare(b.maturity_date ?? ""))
        .map((b) => item(bondHref(b.isin), bondName(b.isin, bonds.data),
          [isSynthetic(b.isin) ? null : b.isin, b.maturity_date ? t("search.matures", { date: date(b.maturity_date) }) : null].filter(Boolean).join(" · "),
          b.series_label, b.maturity_date?.slice(0, 4))),
    },
    {
      key: "guides",
      items: GUIDES.map((g) => item(`/learn/${g.slug}`, t(`guides.${g.slug}.title` as never), t(`guides.${g.slug}.summary` as never))),
    },
    {
      key: "glossary",
      items: GLOSSARY.map((id) => item(`/learn/glossary#${id}`, t(`learn.terms.${id}.name` as never), t(`learn.terms.${id}.short` as never))),
    },
    {
      key: "pages",
      items: MENUS.flatMap((m) => m.items.map((i) =>
        item(i.href, t(`menu.${m.key}.${i.key}.title` as never), t(`menu.${m.key}.${i.key}.desc` as never)))),
    },
  ];
  const all = groups.flatMap((g) => g.items);
  const shown = all.filter((i) => matchesQuery(i.text, query)).length;
  return (
    <>
      <PageHead eyebrow={t("search.eyebrow")} title={t("search.title")} lead={t("search.lead")} />
      <FilterBar scope="search-results" action="/search" placeholder={t("search.placeholder")} query={query} shown={shown} total={all.length} />
      <div id="search-results" className="search-results" data-idle-list="" data-idle={query ? undefined : ""}>
        {groups.map((g) => {
          const any = g.items.some((i) => matchesQuery(i.text, query));
          return (
            <section key={g.key} data-group="" hidden={!any}>
              <h2>{t(`search.groups.${g.key}` as never)}</h2>
              <ul>
                {g.items.map((i) => (
                  <li key={i.href} data-search={i.text} hidden={!matchesQuery(i.text, query)}>
                    <Link href={i.href}>{i.title}</Link>
                    <span className="small muted">{i.sub}</span>
                  </li>
                ))}
              </ul>
              {g.items.length > 8 && <p className="small muted idle-more">{t("search.more", { count: g.items.length - 8 })}</p>}
            </section>
          );
        })}
        {shown === 0 && <p className="muted">{t("search.none")}</p>}
      </div>
    </>
  );
}
