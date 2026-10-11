import Link from "next/link";
import { getTranslations } from "next-intl/server";

import Disclaimer from "./Disclaimer";
import { type ModelName, modelEntry } from "@/lib/registry";

// Under every model's output: its method page, its version, and its disclaimer.
export default async function ModelFooter({ models }: { models: ModelName[] }) {
  const t = await getTranslations();
  const keys = Array.from(new Set(models.map((m) => modelEntry(m).disclaimer_key)));
  return (
    <>
      <p className="small muted">
        {models.map((m, i) => (
          <span key={m}>
            {i > 0 && " · "}
            <Link href={`/methods/${m}`}>{t(modelEntry(m).title_key as never)}</Link>{" "}
            ({t("common.version", { version: modelEntry(m).current_version })})
          </span>
        ))}
      </p>
      <Disclaimer keys={[...keys, "data_sources"]} />
    </>
  );
}
