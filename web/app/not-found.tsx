import Link from "next/link";
import { getTranslations } from "next-intl/server";

export default async function NotFound() {
  const t = await getTranslations();
  return (
    <>
      <h1>404</h1>
      <p>
        <Link href="/">{t("nav.home")}</Link>
      </p>
    </>
  );
}
