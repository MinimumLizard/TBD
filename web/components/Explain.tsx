import Link from "next/link";
import { getTranslations } from "next-intl/server";

import type { RelatedLink } from "./Section";

// "Why it matters" and "How to read it" at the top of a short page (long pages put them inside each Section), with
// links to the guide that explains the page in full.
export default async function Explain({ why, how, related }: { why: React.ReactNode; how?: React.ReactNode; related?: RelatedLink[] }) {
  const t = await getTranslations();
  return (
    <div className="explain">
      <p>
        <strong>{t("ui.whyItMatters")}</strong> {why}
      </p>
      {how && (
        <details>
          <summary>{t("ui.howToRead")}</summary>
          {how}
        </details>
      )}
      {related && related.length > 0 && (
        <p className="related" style={{ marginTop: 8 }}>
          <span className="r-label">{t("ui.related")}</span>
          {related.map((r) => (
            <Link key={r.href} href={r.href}>{r.label}</Link>
          ))}
        </p>
      )}
    </div>
  );
}
