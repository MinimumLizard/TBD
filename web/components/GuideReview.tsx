import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { usefulCount } from "@/lib/data/feedback";

// "Was this guide useful?" at the end of a guide (Janu's review, 2026-11-09). A plain form posting to the feedback
// route (one vote per reader and page, migration 0018); once enough readers have said so, how many found it useful.
export default async function GuideReview({ page }: { page: string }) {
  const [t, count] = await Promise.all([getTranslations(), usefulCount(page)]);
  return (
    <section className="guide-review" aria-label={t("guides.review.title")}>
      <form method="post" action="/api/feedback">
        <input type="hidden" name="kind" value="page_vote" />
        <input type="hidden" name="page" value={page} />
        <strong>{t("guides.review.title")}</strong>
        <button type="submit" name="useful" value="yes" className="button">{t("feedback.vote.yes")}</button>
        <button type="submit" name="useful" value="no" className="button secondary">{t("feedback.vote.no")}</button>
      </form>
      <p className="small muted">
        {count != null ? t("guides.review.count", { count }) : t("guides.review.ask")}{" "}
        <Link href="/feedback">{t("guides.review.more")}</Link>
      </p>
    </section>
  );
}
