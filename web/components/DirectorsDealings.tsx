import Link from "next/link";
import { getTranslations } from "next-intl/server";

import DealingsTable from "./DealingsTable";
import Locked from "./Locked";
import ModelFooter from "./ModelFooter";
import Term from "./Term";
import { companyDealings } from "@/lib/data/dealings";
import type { Viewer } from "@/lib/entitlements";

const SHOWN = 10;

// The share page's "Directors' dealings" panel: the company's disclosed dealings, newest first, without names. It
// reads its own data (cse_dealings, through the one tier check), so the share page only places it.
export default async function DirectorsDealings({ viewer, symbol }: { viewer: Viewer; symbol: string }) {
  const [t, result] = await Promise.all([getTranslations(), companyDealings(viewer, symbol)]);
  const rows = result.data ?? [];
  return (
    <section aria-labelledby="dealings">
      <h2 id="dealings"><Term id="directorsDealings">{t("dealings.panel.title")}</Term></h2>
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
    </section>
  );
}
