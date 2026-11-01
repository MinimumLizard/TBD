import Link from "next/link";
import { getTranslations } from "next-intl/server";

import DealingsTable from "./DealingsTable";
import Locked from "./Locked";
import ModelFooter from "./ModelFooter";
import type { Result } from "@/lib/data/common";
import type { Dealing } from "@/lib/data/dealings";

const SHOWN = 10;

// The share page's "Directors' dealings" panel body: the company's disclosed dealings, newest first, with the names
// the company filed. The page reads them (cse_dealings, through the one tier check) and places this inside its section.
export default async function DirectorsDealings({ result }: { result: Result<Dealing[]> }) {
  const t = await getTranslations();
  const rows = result.data ?? [];
  return (
    <>
      {!result.access.allowed ? (
        <Locked access={result.access} />
      ) : rows.length === 0 ? (
        <p className="muted">{t("dealings.panel.none")}</p>
      ) : (
        <>
          <DealingsTable rows={rows.slice(0, SHOWN)} />
          <p className="small muted">
            {rows.length > SHOWN && <>{t("dealings.panel.more", { shown: SHOWN, count: rows.length })} </>}
            {t("dealings.panel.note")}
          </p>
        </>
      )}
      <p className="small">
        <Link href="/cse/dealings">{t("dealings.linkAll")} →</Link>
      </p>
      {result.access.allowed && <ModelFooter models={["cse_dealings"]} />}
    </>
  );
}
