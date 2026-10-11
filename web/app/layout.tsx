import type { Metadata } from "next";
import { getLocale, getTranslations } from "next-intl/server";

import SiteFooter from "@/components/SiteFooter";
import SiteHeader from "@/components/SiteHeader";
import { getViewer } from "@/lib/viewer";

import "./globals.css";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations();
  return { title: { default: t("site.name"), template: `%s · ${t("site.name")}` }, description: t("site.tagline") };
}

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const [locale, t, viewer] = await Promise.all([getLocale(), getTranslations(), getViewer()]);
  return (
    <html lang={locale}>
      <body>
        <a href="#main" className="skip">
          {t("site.skip")}
        </a>
        <SiteHeader viewer={viewer} />
        <main id="main" className="container">
          {children}
        </main>
        <SiteFooter />
      </body>
    </html>
  );
}
