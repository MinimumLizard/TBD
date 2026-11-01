import { getTranslations } from "next-intl/server";

// A page's opening: where you are (eyebrow), what it is, what it is for, and links to its collapsible parts. The
// "open all" button is hidden until the page's script runs (components/PageScripts.tsx), since it needs JavaScript.
export default async function PageHead({ eyebrow, title, lead, meta, parts }: {
  eyebrow?: React.ReactNode;
  title: React.ReactNode;
  lead?: React.ReactNode;
  meta?: React.ReactNode;
  parts?: { id: string; label: string }[];
}) {
  const t = await getTranslations();
  return (
    <header className="page-head">
      {eyebrow && <p className="eyebrow">{eyebrow}</p>}
      <h1>{title}</h1>
      {lead && <p className="lead">{lead}</p>}
      {meta}
      {parts && parts.length > 1 && (
        <nav className="onpage" aria-label={t("ui.onThisPage")}>
          <span className="onpage-label">{t("ui.onThisPage")}</span>
          {parts.map((p) => (
            <a key={p.id} href={`#${p.id}`}>{p.label}</a>
          ))}
          <button type="button" data-toggle-all="" data-open={t("ui.openAll")} data-close={t("ui.closeAll")} hidden>
            {t("ui.openAll")}
          </button>
        </nav>
      )}
    </header>
  );
}
