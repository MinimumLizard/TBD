import Link from "next/link";
import { getTranslations } from "next-intl/server";

import Disclaimer from "./Disclaimer";

export default async function SiteFooter() {
  const t = await getTranslations();
  return (
    <footer className="site">
      <div className="container">
        <Disclaimer keys={["general", "data_sources"]} />
        <p>
          <Link href="/about">{t("nav.about")}</Link> · <Link href="/methods">{t("nav.methods")}</Link> · {t("footer.rights")}
        </p>
      </div>
    </footer>
  );
}
