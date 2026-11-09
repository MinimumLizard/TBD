import { getTranslations } from "next-intl/server";

import PageHead from "@/components/PageHead";
import StartChooser from "@/components/StartChooser";
import Stats from "@/components/Stats";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";

export async function generateMetadata() {
  const t = await getTranslations();
  return { title: t("start.title") };
}

// The first question of the starting paths (lib/paths.ts).
export default async function StartPage() {
  const [t, viewer] = await Promise.all([getTranslations(), getViewer()]);
  return (
    <>
      <PageHead eyebrow={t("start.eyebrow")} title={t("start.title")} lead={t("start.lead")}
                meta={<p className="small muted">{t("start.stepOf", { n: 1 })}</p>} />
      <StartChooser />
      <Stats viewer={viewer} keys={["investors", "literacy", "savers"]} />
    </>
  );
}
