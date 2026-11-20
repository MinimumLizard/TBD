import Link from "next/link";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";

import PageHead from "@/components/PageHead";
import { decodeSegment } from "@/lib/params";
import { AMOUNTS, HORIZONS, answer } from "@/lib/paths";

export async function generateMetadata() {
  const t = await getTranslations();
  return { title: t("start.more.title") };
}

// Questions 3 and 4, both optional: roughly how much, and when it might be needed. A plain GET form to the path's page
// (web/proxy.ts keeps the answers in the starting cookie). The answers change information shown, never advice.
export default async function StartMorePage({ params }: { params: Promise<{ type: string; answer: string }> }) {
  const raw = await params;
  const type = decodeSegment(raw.type);
  const key = decodeSegment(raw.answer);
  if (!answer(type, key)) notFound();
  const t = await getTranslations();
  const next = `/start/${type}/${key}`;
  return (
    <div className="onboarding">
      <PageHead eyebrow={`${t("start.eyebrow")} · ${t(`start.types.${type}.short` as never)}`} title={t("start.more.title")}
                lead={t("start.more.lead")} meta={<p className="small muted">{t("start.more.stepOf")}</p>} />
      <form className="more-form" method="get" action={next} data-start-more="">
        <a data-start-next="" href={next} hidden>{next}</a>
        <fieldset>
          <legend>{t("start.more.amountQuestion")}</legend>
          <div className="choice-row">
            {AMOUNTS.map((a) => (
              <label key={a} className="choice"><input type="radio" name="amount" value={a} /><span>{t(`start.amounts.${a}` as never)}</span></label>
            ))}
            <label className="choice quiet"><input type="radio" name="amount" value="" defaultChecked /><span>{t("start.more.preferNot")}</span></label>
          </div>
        </fieldset>
        <fieldset>
          <legend>{t("start.more.horizonQuestion")}</legend>
          <div className="choice-row">
            {HORIZONS.map((h) => (
              <label key={h} className="choice"><input type="radio" name="horizon" value={h} /><span>{t(`start.horizons.${h}` as never)}</span></label>
            ))}
            <label className="choice quiet"><input type="radio" name="horizon" value="" defaultChecked /><span>{t("start.more.notSure")}</span></label>
          </div>
        </fieldset>
        <p className="small muted">{t("start.more.why")}</p>
        <div className="more-actions">
          <button className="button" type="submit">{t("start.more.submit")} →</button>
          <Link href={next}>{t("start.more.skip")}</Link>
        </div>
      </form>
      <p className="small"><Link href={`/start/${type}`}>← {t("start.back")}</Link></p>
    </div>
  );
}
