import Link from "next/link";
import { getTranslations } from "next-intl/server";

import type { Tier } from "@/lib/registry";

export interface RelatedLink {
  href: string;
  label: string;
}

// One part of a long page, collapsible (docs/research/retail-investor-needs-2026-11.md §4). The heading and a one-line
// summary stay visible when it is closed, so a closed section still says something; inside, the panel answers why it
// matters and how to read it, then links to what it connects to. A plain <details>: it works without JavaScript, and
// the browser's find-in-page opens it.
export default async function Section({ id, title, summary, tier, open = false, why, how, related, children }: {
  id: string;
  title: React.ReactNode;
  summary?: React.ReactNode;
  tier?: Tier;
  open?: boolean;
  why?: React.ReactNode;
  how?: React.ReactNode;
  related?: RelatedLink[];
  children: React.ReactNode;
}) {
  const t = await getTranslations();
  return (
    <details className="section" id={id} open={open}>
      <summary>
        <span className="s-title">
          {title}
          {tier && tier !== "free" && <span className={`tier-pill ${tier}`}>{t(`tiers.${tier}`)}</span>}
        </span>
        {summary && <span className="s-sum">{summary}</span>}
        <span className="s-chev" aria-hidden="true" />
      </summary>
      <div className="s-body">
        {(why || how) && (
          <div className="explain">
            {why && (
              <p>
                <strong>{t("ui.whyItMatters")}</strong> {why}
              </p>
            )}
            {how && (
              <details>
                <summary>{t("ui.howToRead")}</summary>
                {how}
              </details>
            )}
          </div>
        )}
        {children}
        {related && related.length > 0 && (
          <p className="related">
            <span className="r-label">{t("ui.related")}</span>
            {related.map((r) => (
              <Link key={r.href} href={r.href}>{r.label}</Link>
            ))}
          </p>
        )}
      </div>
    </details>
  );
}
