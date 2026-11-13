import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { sitePath } from "@/lib/feedback";
import { SIGNUP_OUTCOMES, type SignupOutcome } from "@/lib/signup";

export const dynamic = "force-dynamic";

export async function generateMetadata() {
  const t = await getTranslations();
  return { title: t("signup.thanks.failTitle") };
}

// What happened to a sign-up. It never says whether the address was already on the list.
export default async function SignupThanksPage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const [t, params] = await Promise.all([getTranslations(), searchParams]);
  const outcome: SignupOutcome = (SIGNUP_OUTCOMES as readonly string[]).includes(params.r ?? "") ? (params.r as SignupOutcome) : "invalid";
  const from = sitePath(params.from) ?? "/markets";
  return (
    <>
      <h1>{outcome === "ok" ? t("signup.thanks.title") : t("signup.thanks.failTitle")}</h1>
      <p className="lead">{t(`signup.thanks.${outcome}`)}</p>
      <p style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
        <Link href={from}>{t("signup.thanks.back")}</Link>
        <Link href="/markets">{t("signup.thanks.home")}</Link>
      </p>
    </>
  );
}
