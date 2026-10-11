import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";

import Disclaimer from "@/components/Disclaimer";
import { methodHtml } from "@/lib/markdown";
import { isModelName, modelEntry } from "@/lib/registry";

export async function generateMetadata({ params }: { params: Promise<{ name: string }> }) {
  const { name } = await params;
  if (!isModelName(name)) return {};
  const t = await getTranslations();
  return { title: t(modelEntry(name).title_key as never) };
}

export default async function MethodPage({ params }: { params: Promise<{ name: string }> }) {
  const { name } = await params;
  if (!isModelName(name)) notFound();
  const t = await getTranslations();
  const entry = modelEntry(name);
  return (
    <>
      <p className="small">
        <span className="badge">{t("methods.availableFrom", { tier: t(`tiers.${entry.minimum_tier}`) })}</span>{" "}
        <span className="badge">{t("methods.currentVersion", { version: entry.current_version })}</span>
      </p>
      <article className="method" dangerouslySetInnerHTML={{ __html: methodHtml(entry.method_md) }} />
      <h2>{t("methods.versions")}</h2>
      <ul>
        {entry.versions.map((v) => (
          <li key={v.method_version}>
            {v.method_version}: {t(`methods.status_${v.status}` as never)}
          </li>
        ))}
      </ul>
      <Disclaimer keys={[entry.disclaimer_key, "data_sources"]} />
    </>
  );
}
