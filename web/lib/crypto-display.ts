// The crypto pages' assets, in the order they are listed, and how their prices are written. Names are in
// messages (crypto.assets.<slug>); the pair is Bitstamp's url_symbol, as stored by the collector.
import { num } from "./format";

export interface CryptoAsset {
  slug: string; // the page address: /crypto/<slug>
  pair: string;
  label: string; // the market as Bitstamp names it
  quote: "USD" | "BTC";
  cycle: boolean; // crypto_cycle covers it (every US-dollar pair)
}

const usd = (slug: string, label: string): CryptoAsset => ({ slug, pair: `${slug}usd`, label: `${label}/USD`, quote: "USD", cycle: true });

export const CRYPTO_ASSETS: CryptoAsset[] = [
  usd("btc", "BTC"),
  usd("eth", "ETH"),
  usd("xrp", "XRP"),
  usd("sol", "SOL"),
  usd("ada", "ADA"),
  usd("doge", "DOGE"),
  usd("link", "LINK"),
  usd("avax", "AVAX"),
  usd("ltc", "LTC"),
  usd("dot", "DOT"),
  { slug: "ethbtc", pair: "ethbtc", label: "ETH/BTC", quote: "BTC", cycle: false },
];

export function assetBySlug(slug: string): CryptoAsset | undefined {
  return CRYPTO_ASSETS.find((a) => a.slug === slug);
}

export function assetByPair(pair: string): CryptoAsset | undefined {
  return CRYPTO_ASSETS.find((a) => a.pair === pair);
}

/** A price in its quote currency: "$81,384.63", "$0.2191", "0.02946 BTC". */
export function price(v: number | null | undefined, quote: "USD" | "BTC" = "USD"): string {
  if (typeof v !== "number" || !Number.isFinite(v)) return num(v);
  if (quote === "BTC") return `${num(v, 5)} BTC`;
  const dp = v >= 1 ? 2 : v >= 0.01 ? 4 : 6;
  return `$${num(v, dp)}`;
}
