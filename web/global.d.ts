import type messages from "./messages/en.json";

// Every message key used in code is checked against messages/en.json at compile time.
declare module "next-intl" {
  interface AppConfig {
    Messages: typeof messages;
    Locale: "en";
  }
}
