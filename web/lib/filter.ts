// Finding things in long lists (shares, bonds, search results). The same rule runs on the server, from the form's
// query string, so filtering works without JavaScript, and in the browser as the visitor types
// (components/PageScripts.tsx; the static preview's script in scripts/export-static.mjs repeats it).

/** The text an item is found by: its parts, lower case, accents and punctuation removed, single-spaced. */
export function searchText(...parts: (string | null | undefined)[]): string {
  return parts
    .filter(Boolean)
    .join(" ")
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9.%]+/g, " ")
    .replace(/^ +| +$/g, "");
}

/** Every word of the query appears somewhere in the item's text. An empty query matches everything. */
export function matchesQuery(text: string, query: string | null | undefined): boolean {
  const words = searchText(query).split(" ").filter(Boolean);
  return words.every((w) => text.includes(w));
}

/** A query-string value as one string (the first, if repeated), at most 80 characters. */
export function param(value: string | string[] | undefined): string {
  const v = Array.isArray(value) ? value[0] : value;
  return (v ?? "").slice(0, 80);
}
