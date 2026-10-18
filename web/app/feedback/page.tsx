import { headers } from "next/headers";
import { getTranslations } from "next-intl/server";

import { MAX_MESSAGE, MIN_MESSAGE, TOPICS, refererPath, sitePath } from "@/lib/feedback";

export const dynamic = "force-dynamic";

export async function generateMetadata() {
  const t = await getTranslations();
  return { title: t("feedback.title") };
}

// The full feedback form. A plain HTML form posted to /api/feedback; the page it is about comes from ?from= or from
// the page the visitor came from.
export default async function FeedbackPage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const [t, params, h] = await Promise.all([getTranslations(), searchParams, headers()]);
  const page = sitePath(params.from) ?? refererPath(h.get("referer"), h.get("host")) ?? "/";
  return (
    <>
      <h1>{t("feedback.title")}</h1>
      <p className="lead">{t("feedback.intro")}</p>
      <form className="card feedback-form" method="post" action="/api/feedback">
        <input type="hidden" name="kind" value="message" />
        <input type="hidden" name="page" value={page} />
        <input className="trap" type="text" name="website" tabIndex={-1} autoComplete="off" aria-hidden="true" />
        <fieldset>
          <legend>{t("feedback.topic")}</legend>
          {TOPICS.map((topic, i) => (
            <label key={topic} className="choice">
              <input type="radio" name="topic" value={topic} required defaultChecked={i === 0} /> {t(`feedback.topics.${topic}`)}
            </label>
          ))}
        </fieldset>
        <label className="field">
          <span>{t("feedback.message")}</span>
          <textarea name="message" rows={6} required minLength={MIN_MESSAGE} maxLength={MAX_MESSAGE} />
          <span className="small muted">{t("feedback.messageHelp", { min: MIN_MESSAGE, max: MAX_MESSAGE })}</span>
        </label>
        <p className="small muted">{t("feedback.about")}: <code>{page}</code></p>
        <button type="submit" className="button">{t("feedback.send")}</button>
        <p className="small muted">{t("feedback.privacy")}</p>
        <p className="small muted">{t("feedback.notAdvice")}</p>
      </form>
    </>
  );
}
