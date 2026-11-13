import Link from "next/link";
import { getTranslations } from "next-intl/server";

import StartChooser from "./StartChooser";

// The first thing a new visitor sees, and nothing else (decision 0025): one question, four answers, a way to skip.
// The "onboarding" class quietens the header and footer around it (app/globals.css).
export default async function Welcome() {
  const t = await getTranslations();
  return (
    <section className="welcome onboarding">
      <p className="eyebrow">{t("start.welcomeEyebrow")}</p>
      <h1>{t("start.title")}</h1>
      <p className="lead">{t("start.homeLead")}</p>
      <StartChooser />
      <p className="welcome-foot">
        <Link href="/markets?skip=1" data-skip-start="">{t("start.skip")} →</Link>
        <span className="muted">{t("start.promise")}</span>
      </p>
    </section>
  );
}
