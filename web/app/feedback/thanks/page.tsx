import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { OUTCOMES, type Outcome, sitePath } from "@/lib/feedback";

export const dynamic = "force-dynamic";

export async function generateMetadata() {
  const t = await getTranslations();
  return { title: t("feedback.thanks.title") };
}

export default async function ThanksPage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const [t, params] = await Promise.all([getTranslations(), searchParams]);
  const outcome: Outcome = (OUTCOMES as readonly string[]).includes(params.r ?? "") ? (params.r as Outcome) : "invalid";
  const from = sitePath(params.from) ?? "/";
  return (
    <>
      <h1>{outcome === "ok" ? t("feedback.thanks.title") : t("feedback.title")}</h1>
      <p className="lead">{t(`feedback.thanks.${outcome}`)}</p>
      <p style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
        <Link href={from}>{t("feedback.thanks.back")}</Link>
        <Link href={`/feedback?from=${encodeURIComponent(from)}`}>{t("feedback.thanks.again")}</Link>
      </p>
    </>
  );
}
