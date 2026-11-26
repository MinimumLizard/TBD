import Link from "next/link";
import { getTranslations } from "next-intl/server";

import Bolt from "./Bolt";
import { CODES } from "@/lib/codes";

// One slim row of glowing pointers to the cheat codes: compact, scrolls sideways on a phone, never in the way.
export default async function CheatStrip({ only }: { only?: string[] }) {
  const t = await getTranslations();
  const codes = only ? CODES.filter((c) => only.includes(c.key)) : CODES.slice(0, 5);
  return (
    <nav className="cheat-strip" aria-label={t("codes.title")}>
      <Link href="/codes" className="cheat-label"><Bolt />{t("codes.title")}</Link>
      <div className="cheat-row">
        {codes.map((c) => (
          <Link key={c.key} href={c.href} className="glow-chip">{t(`codes.${c.key}.title` as never)}</Link>
        ))}
      </div>
    </nav>
  );
}
