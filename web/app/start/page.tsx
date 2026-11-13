import { getTranslations } from "next-intl/server";

import Welcome from "@/components/Welcome";

export const dynamic = "force-dynamic";

export async function generateMetadata() {
  const t = await getTranslations();
  return { title: t("start.title") };
}

// The first question again, for a visitor who wants to change their answers (the front door shows it only once).
export default function StartPage() {
  return <Welcome />;
}
