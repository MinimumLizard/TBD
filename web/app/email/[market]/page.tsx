import Link from "next/link";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { renderHtml } from "@/lib/email/digest";
import { MARKETS, isMarket, weeklyDigest } from "@/lib/email/weekly";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";

export async function generateMetadata() {
  const t = await getTranslations();
  return { title: t("email.preview.title") };
}

// What this week's e-mail looks like for the visitor's own plan. It is built exactly as a sent e-mail will be, so
// this page is also how the tier-leak tests check that e-mails never carry another tier's numbers.
export default async function EmailPreview({ params }: { params: Promise<{ market: string }> }) {
  const [{ market }, t, viewer] = await Promise.all([params, getTranslations(), getViewer()]);
  if (!isMarket(market)) notFound();
  const digest = await weeklyDigest(viewer, market, { site: "", unsubscribe: "#" });
  return (
    <>
      <h1>{t("email.preview.title")}</h1>
      <p className="lead">{t("email.preview.intro", { tier: t(`tiers.${viewer.tier}`) })}</p>
      <p className="small muted">{t("email.preview.notSent")}</p>
      <nav className="tabs" aria-label={t("email.preview.markets")}>
        {MARKETS.map((m) => (
          <Link key={m} href={`/email/${m}`} aria-current={m === market ? "page" : undefined}>{t(`email.markets.${m}`)}</Link>
        ))}
      </nav>
      <p className="small"><strong>{t("email.preview.subject")}:</strong> {digest.subject}</p>
      <div className="email-frame" dangerouslySetInnerHTML={{ __html: renderHtml(digest) }} />
    </>
  );
}
