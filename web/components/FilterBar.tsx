import { getTranslations } from "next-intl/server";

export interface FilterSelect {
  name: string; // filters items by their data-<name> attribute
  label: string;
  all: string; // the label of "no filter"
  options: { value: string; label: string }[];
  value: string;
}

// A search box (and optional drop-downs) over a list. It is a plain GET form, so it works without JavaScript; with
// it, the list filters as the visitor types (components/PageScripts.tsx). `scope` is the id of the element holding
// the items (each with data-search, and data-<select name> for each drop-down).
export default async function FilterBar({ scope, action, placeholder, query, selects = [], shown, total }: {
  scope: string;
  action: string;
  placeholder: string;
  query: string;
  selects?: FilterSelect[];
  shown: number;
  total: number;
}) {
  const t = await getTranslations();
  return (
    <form className="filter-bar" method="get" action={action} role="search" data-filter={scope}>
      <label className="filter-q">
        <span className="visually-hidden">{placeholder}</span>
        <input type="search" name="q" defaultValue={query} placeholder={placeholder} autoComplete="off" />
      </label>
      {selects.map((s) => (
        <label key={s.name} className="filter-select">
          <span className="visually-hidden">{s.label}</span>
          <select name={s.name} defaultValue={s.value}>
            <option value="">{s.all}</option>
            {s.options.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </label>
      ))}
      <button type="submit" className="button" data-filter-go="">{t("ui.find")}</button>
      <span className="filter-count small muted" data-filter-count="" data-template={t("ui.shownOf", { shown: "{shown}", total: "{total}" })}>
        {t("ui.shownOf", { shown, total })}
      </span>
    </form>
  );
}
