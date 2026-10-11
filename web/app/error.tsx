"use client";

import { useTranslations } from "next-intl";

// Shown when a page fails, e.g. the database cannot be reached. No details of the failure reach the browser.
export default function ErrorPage() {
  const t = useTranslations("errors");
  return (
    <>
      <h1>{t("title")}</h1>
      <p>{t("body")}</p>
    </>
  );
}
