import Link from "next/link";
import { getTranslations } from "next-intl/server";

// Sign up with an e-mail address (lib/signup.ts; migration 0019). A plain form: it works without JavaScript. The
// consent box is not pre-ticked, and the weekly summary is a separate, optional choice.
export default async function SignupBox({ page, type, answer }: { page: string; type?: string; answer?: string }) {
  const t = await getTranslations();
  return (
    <section className="signup" aria-labelledby="signup-title">
      <h2 id="signup-title">{t("signup.title")}</h2>
      <p>{t("signup.lead")}</p>
      <form method="post" action="/api/signup">
        <input type="hidden" name="page" value={page} />
        {type && <input type="hidden" name="type" value={type} />}
        {answer && <input type="hidden" name="answer" value={answer} />}
        <input className="trap" type="text" name="website" tabIndex={-1} autoComplete="off" aria-hidden="true" />
        <div className="signup-row">
          <label htmlFor="signup-email">{t("signup.email")}</label>
          <input id="signup-email" type="email" name="email" required maxLength={254} autoComplete="email" inputMode="email" />
          <button className="button" type="submit">{t("signup.button")}</button>
        </div>
        <label className="check">
          <input type="checkbox" name="consent" value="yes" required />
          <span>{t("signup.consent")} <Link href="/privacy">{t("signup.privacyLink")}</Link></span>
        </label>
        <label className="check">
          <input type="checkbox" name="weekly" value="yes" />
          <span>{t("signup.weekly")}</span>
        </label>
      </form>
      <p className="small muted">{t("signup.note")}</p>
    </section>
  );
}
