// Language. Launch is English only (docs/architecture.md §9). Sinhala and Tamil are added by translating
// messages/si.json and messages/ta.json and listing them in LOCALES: no code changes.
import { getRequestConfig } from "next-intl/server";

export const LOCALES = ["en"] as const;
export const DEFAULT_LOCALE = "en";

export default getRequestConfig(async () => {
  const locale = DEFAULT_LOCALE;
  return { locale, timeZone: "Asia/Colombo", messages: (await import(`../messages/${locale}.json`)).default };
});
