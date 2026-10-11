import type { BondRef } from "./data/bonds";

export function bondName(isin: string, ref: Map<string, BondRef> | null | undefined): string {
  const r = ref?.get(isin);
  return r?.notes && r.notes !== r.series_label ? r.notes : r?.series_label ?? isin;
}

export function isSynthetic(isin: string): boolean {
  return isin.startsWith("SYN:");
}

export function bondHref(isin: string): string {
  return `/bonds/${encodeURIComponent(isin)}`;
}
