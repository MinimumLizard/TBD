import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { GLOSSARY, type GlossaryTerm } from "@/lib/glossary";

// A word a new investor may not know: underlined, with its one-line meaning on hover, linking to its explanation.
export default async function Term({ id, children }: { id: GlossaryTerm; children?: React.ReactNode }) {
  const t = await getTranslations();
  return (
    <Link href={`/learn#${id}`} className="term" title={t(`learn.terms.${id}.short` as never)}>
      {children ?? t(`learn.terms.${id}.name` as never)}
    </Link>
  );
}

export { GLOSSARY };
