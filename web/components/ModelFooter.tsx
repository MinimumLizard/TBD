import Link from "next/link";
import { getTranslations } from "next-intl/server";

import Disclaimer, { SITE_WIDE_DISCLAIMERS } from "./Disclaimer";
import { type ModelName, modelEntry } from "@/lib/registry";

// Under every model's output: its method page, its version, and its own disclaimer (the site-wide ones are in the
// footer of every page, so they are not repeated here).
// shownAbove: disclaimers the page already shows prominently (the crypto pages show theirs at the top).
export default async function ModelFooter({ models, shownAbove = [] }: { models: ModelName[]; shownAbove?: string[] }) {
  const t = await getTranslations();
  const keys = Array.from(new Set(models.map((m) => modelEntry(m).disclaimer_key))).filter(
    (k) => !SITE_WIDE_DISCLAIMERS.includes(k) && !shownAbove.includes(k),
  );
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
      <Disclaimer keys={keys} />
    </>
  );
}
