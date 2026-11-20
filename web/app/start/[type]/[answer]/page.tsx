import Link from "next/link";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";

import PageHead from "@/components/PageHead";
import SignupBox from "@/components/SignupBox";
import Stats from "@/components/Stats";
import YourMoney from "@/components/YourMoney";
import { guide } from "@/lib/guides";
import { decodeSegment } from "@/lib/params";
import { cookies } from "next/headers";

import { SKIPPED, START_COOKIE, TOOL_KEYS, answer, isAmount, isHorizon, readStart } from "@/lib/paths";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";

export async function generateMetadata() {
  const t = await getTranslations();
  return { title: t("start.result.title") };
}

// A starting path: three steps, each a guide and the page it explains (lib/paths.ts). It chooses what to read; it
// says nothing about what to do with money (hard rule 4). Opening it makes it the visitor's answer: web/proxy.ts sets
// the cookie that opens the front door on their own home page (the hidden link below does the same job in the
// static preview, which has no server).
export default async function StartPathPage({ params, searchParams }: {
  params: Promise<{ type: string; answer: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const [raw, query, jar] = await Promise.all([params, searchParams, cookies()]);
  const type = decodeSegment(raw.type);
  const key = decodeSegment(raw.answer);
  const a = answer(type, key);
  if (!a) notFound();
  const [t, viewer] = await Promise.all([getTranslations(), getViewer()]);
  // questions 3 and 4: from the form just sent, or else what this visitor said before on this same path
  const saved = readStart(jar.get(START_COOKIE)?.value);
  const before = saved && saved !== SKIPPED && saved.type === type && saved.answer === key ? saved : null;
  const asked = "amount" in query || "horizon" in query;
  const amount = asked ? (isAmount(query.amount) ? query.amount : null) : before?.amount ?? null;
  const horizon = asked ? (isHorizon(query.horizon) ? query.horizon : null) : before?.horizon ?? null;
  const tool = (href: string) => t(`start.tools.${TOOL_KEYS[href]}` as never);
  const label = `${t(`start.types.${type}.short` as never)} · ${t(`start.questions.${type}.${key}` as never)}`;
  return (
    <div className="onboarding">
      <PageHead eyebrow={t("start.result.eyebrow")} title={t("start.result.title")}
                lead={t(`start.result.intro.${type}` as never)}
                meta={<p className="small muted">{t("start.result.youSaid")}: {label}</p>} />
      <a data-remember-path="" href={`/start/${type}/${key}`} hidden>{label}</a>
      <ol className="path-steps">
        {a.steps.map((s, i) => {
          const g = s.guide ? guide(s.guide) : null;
          const title = g ? t(`guides.${g.slug}.title` as never) : tool(s.page!);
          const body = g ? t(`guides.${g.slug}.summary` as never) : t("savings.lead");
          return (
            <li key={i} className={i === 0 ? "first" : undefined}>
              <span className="p-step">{t("start.result.step", { n: i + 1 })}</span>
              <h2>{title}</h2>
              {i === 0 && <p className="p-why">{t(`start.result.why.${key}` as never)}</p>}
              <p className="muted">{body}</p>
              <p className="p-actions">
                <Link className={i === 0 ? "button" : "button secondary"} href={g ? `/learn/${g.slug}` : s.page!}>
                  {g ? t("start.result.readGuide") : t("start.result.openPage")}
                </Link>
                {s.tool && (
                  <span className="small">
                    {t("start.result.thenUse")}: <Link href={s.tool}>{tool(s.tool)} →</Link>
                  </span>
                )}
              </p>
            </li>
          );
        })}
      </ol>
      <YourMoney viewer={viewer} amount={amount} horizon={horizon} more={`/start/${type}/${key}/more`} />
      <div className="path-next">
        <Link className="button" href={`/home/${type}/${key}`}>{t("start.result.homeButton")} →</Link>
        <span className="small muted">{t("start.result.homeNote")}</span>
      </div>
      <SignupBox page={`/start/${type}/${key}`} type={type} answer={key} />
      {a.stat && <Stats viewer={viewer} keys={[a.stat]} />}
      <p className="small muted">{t("start.result.note")}</p>
      <p className="small"><Link href="/start">{t("start.again")}</Link></p>
    </div>
  );
}
