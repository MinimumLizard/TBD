import type { Metadata } from "next";
import { NextIntlClientProvider } from "next-intl";
import { getLocale, getMessages, getTranslations } from "next-intl/server";

import SiteFooter from "@/components/SiteFooter";
import SiteHeader from "@/components/SiteHeader";
import { getViewer } from "@/lib/viewer";

import "./globals.css";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations();
  return { title: { default: t("site.name"), template: `%s · ${t("site.name")}` }, description: t("site.tagline") };
}

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const [locale, t, viewer, messages] = await Promise.all([getLocale(), getTranslations(), getViewer(), getMessages()]);
  return (
    <html lang={locale}>
      <body>
        <a href="#main" className="skip">
          {t("site.skip")}
        </a>
        <SiteHeader viewer={viewer} />
        <main id="main" className="container">
          {/* Only the error page's text goes to the browser; everything else is rendered on the server. */}
          <NextIntlClientProvider locale={locale} messages={{ errors: messages.errors }}>
            {children}
          </NextIntlClientProvider>
        </main>
        <SiteFooter />
      </body>
    </html>
  );
}
