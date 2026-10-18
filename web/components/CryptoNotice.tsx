import { getTranslations } from "next-intl/server";

import { registry } from "@/lib/registry";

// At the top of every crypto page, before any number: the licence status, and the crypto risk notice citing the
// CBSL (its text comes only from compliance/disclaimers.yaml, through the generated registry).
export default async function CryptoNotice() {
  const t = await getTranslations();
  return (
    <div className="notice warn crypto-notice" role="note" data-disclaimer="crypto_risk">
      <p><strong>{t("crypto.prototype")}</strong></p>
      <p style={{ marginBottom: 0 }}>{registry.disclaimers.crypto_risk.en}</p>
    </div>
  );
}
