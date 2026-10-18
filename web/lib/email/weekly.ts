// Builds the weekly e-mail for one market and one tier (docs/plan-retail-features.md §2). Every number is read
// through the site's data functions, which pass the single tier check (lib/entitlements.ts), so a free subscriber's
// e-mail cannot carry a paid number: hard rule 5 applies to e-mail exactly as to pages.
import "server-only";

import { getTranslations } from "next-intl/server";

import { SITE_WIDE_DISCLAIMERS } from "@/components/Disclaimer";
import { bondName } from "../bond-display";
import { nelsonSiegel } from "../charts";
import { MOVERS_MIN_TURNOVER, companyName } from "../cse-display";
import { bondCarry, bondCurve, bondCurveHistory, bondReference, bondZscores } from "../data/bonds";
import { indexHistory, marketSessionsSince, marketTape, securityNames, shares } from "../data/cse";
import type { Viewer } from "../entitlements";
import { date, int, lkr, num, pct, percent, signed, tone } from "../format";
import { registry } from "../registry";
import { addDays } from "../time";
import type { Digest, Section } from "./digest";

export const MARKETS = ["cse", "bonds"] as const;
export type Market = (typeof MARKETS)[number];
export function isMarket(v: unknown): v is Market {
  return typeof v === "string" && (MARKETS as readonly string[]).includes(v);
}

export interface Links {
  site: string; // "" for links within the site (the preview); the full address in a sent e-mail
  unsubscribe: string; // filled in per subscriber by the sender: the only part that differs between two e-mails
}

const translator = () => getTranslations();
type T = Awaited<ReturnType<typeof translator>>;
const MOVERS = 5;
const TENORS = [1, 2, 5, 10];

/** The value on the last day on or before `day`, from rows sorted oldest first. */
function onOrBefore<R extends { session_date: string }>(rows: R[], day: string): R | null {
  let found: R | null = null;
  for (const r of rows) if (r.session_date <= day) found = r;
  return found;
}

async function cseSections(t: T, viewer: Viewer, links: Links): Promise<{ day: string | null; sections: Section[]; preheader: string }> {
  const tape = await marketTape(viewer);
  const session = tape.data?.session ?? null;
  if (!session) return { day: null, sections: [], preheader: "" };
  const day = session.session_date;
  const weekAgo = addDays(day, -7);
  const [aspi, sp, week, rows, names] = await Promise.all([
    indexHistory(viewer, "ASI"), indexHistory(viewer, "S&P SL20"), marketSessionsSince(viewer, weekAgo),
    shares(viewer, day), securityNames(viewer),
  ]);
  const weekly = (history: typeof aspi) => {
    const now = onOrBefore(history.data ?? [], day);
    const then = onOrBefore(history.data ?? [], weekAgo);
    return { now, change: now && then && then.value ? now.value / then.value - 1 : null };
  };
  const a = weekly(aspi);
  const s = weekly(sp);
  const sessions = week.data ?? [];
  const sum = (k: "turnover" | "foreign_net") => sessions.every((x) => x[k] !== null) ? sessions.reduce((n, x) => n + (x[k] ?? 0), 0) : null;
  const turnover = sum("turnover");
  const foreign = sum("foreign_net");
  const numbers: Section = {
    title: t("email.cse.numbers"),
    lines: [
      { label: t("email.cse.index", { name: "ASPI" }), value: pct(a.change), note: t("email.cse.level", { value: num(a.now?.value) }), tone: tone(a.change) },
      { label: t("email.cse.index", { name: "S&P SL20" }), value: pct(s.change), note: t("email.cse.level", { value: num(s.now?.value) }), tone: tone(s.change) },
      { label: t("email.cse.turnover"), value: lkr(turnover), note: t("email.cse.turnoverNote", { sessions: sessions.length }) },
      { label: t("email.cse.foreign"), value: lkr(foreign), note: t("email.cse.foreignNote"), tone: tone(foreign) },
      { label: t("email.cse.breadth"), value: `${int(session.equities_up)} / ${int(session.equities_down)}` },
    ],
  };
  const eligible = (rows.data?.rows ?? []).filter((r) => r.traded && r.ret_1w !== null && !r.flag_1w && (r.turnover ?? 0) >= MOVERS_MIN_TURNOVER);
  const label = (symbol: string) => {
    const name = companyName(names.data?.get(symbol)?.name);
    return name ? `${symbol} · ${name}` : symbol;
  };
  const movers = (list: typeof eligible) => ({
    head: [t("email.cse.share"), t("email.cse.close"), t("email.cse.week")],
    rows: list.map((r) => ({ cells: [label(r.symbol), num(r.close), pct(r.ret_1w, 1)], tone: tone(r.ret_1w) })),
  });
  const up = [...eligible].filter((r) => (r.ret_1w ?? 0) > 0).sort((x, y) => (y.ret_1w ?? 0) - (x.ret_1w ?? 0)).slice(0, MOVERS);
  const down = [...eligible].filter((r) => (r.ret_1w ?? 0) < 0).sort((x, y) => (x.ret_1w ?? 0) - (y.ret_1w ?? 0)).slice(0, MOVERS);
  return {
    day,
    preheader: t("email.cse.preheader", { aspi: pct(a.change), sessions: sessions.length, turnover: lkr(turnover) }),
    sections: [
      numbers,
      { title: t("email.cse.rises"), intro: t("email.cse.moversIntro"), table: movers(up), empty: t("email.cse.none") },
      { title: t("email.cse.falls"), table: movers(down), empty: t("email.cse.none"), link: { label: t("email.cse.link"), href: `${links.site}/cse` } },
    ],
  };
}

async function bondSections(t: T, viewer: Viewer, links: Links): Promise<{ day: string | null; sections: Section[]; preheader: string }> {
  const [curve, fits, ref, z, carry] = await Promise.all([
    bondCurve(viewer), bondCurveHistory(viewer), bondReference(viewer), bondZscores(viewer), bondCarry(viewer),
  ]);
  const fit = curve.data?.fit ?? null;
  if (!fit) return { day: null, sections: [], preheader: "" };
  const day = fit.obs_date;
  const before = (fits.data ?? []).filter((f) => f.obs_date <= addDays(day, -7)).pop() ?? null;
  const y = (f: typeof fit, years: number) => nelsonSiegel(years, f.beta0, f.beta1, f.beta2, f.lambda_years);
  const bp = (years: number) => (before ? (y(fit, years) - y(before, years)) * 100 : null);
  const plans = `${links.site}/plans`;
  const sections: Section[] = [{
    title: t("email.bonds.curve"),
    intro: t("email.bonds.curveIntro"),
    lines: TENORS.map((years) => ({
      label: t("email.bonds.tenor", { years }), value: percent(y(fit, years)), tone: tone(bp(years)),
      note: before ? `${t("email.bonds.change", { change: `${signed(bp(years), 1)} bp` })}, ${t("email.bonds.sinceNote", { date: date(before.obs_date) })}` : undefined,
    })),
  }];

  const quotes = (curve.data?.points ?? []).filter((p) => p.source === "quote");
  const far = [...quotes].sort((a, b) => Math.abs(b.residual_bp) - Math.abs(a.residual_bp)).slice(0, 5);
  sections.push({
    title: t("email.bonds.residuals"), intro: t("email.bonds.residualsIntro"),
    table: { head: [t("email.bonds.bond"), t("email.bonds.yield"), t("email.bonds.distance")],
             rows: far.map((p) => ({ cells: [bondName(p.isin, ref.data), percent(p.observed_yield), `${signed(p.residual_bp, 1)} bp`], tone: tone(p.residual_bp) })) },
    empty: t("email.noData"),
  });

  // Plus: a free subscriber gets the invitation, never the figures (and not the delayed free preview either: an
  // e-mail dated this week should not carry last week's numbers as if they were this week's).
  if (z.access.allowed && !z.access.maxDate && z.data) {
    const unusual = z.data.bonds.filter((b) => Math.abs(b.zscore) >= 2).sort((a, b) => Math.abs(b.zscore) - Math.abs(a.zscore));
    sections.push({
      title: t("email.bonds.zscores"), intro: `${t("email.bonds.zscoresIntro")} ${t("email.bonds.zscoresCount", { count: unusual.length })}`,
      table: { head: [t("email.bonds.bond"), t("email.bonds.distance"), t("email.bonds.zscore")],
               rows: unusual.slice(0, 5).map((b) => ({ cells: [bondName(b.isin, ref.data), `${signed(b.residual_bp, 1)} bp`, signed(b.zscore, 2)], tone: tone(b.zscore) })) },
    });
  } else {
    sections.push({ title: t("email.bonds.zscores"), locked: { text: t("email.bonds.zLocked"), cta: t("email.bonds.seePlans"), href: plans } });
  }

  if (carry.access.allowed && carry.data && carry.data.rows.length) {
    const totals = carry.data.rows.map((r) => r.total_bp);
    sections.push({
      title: t("email.bonds.carry"), intro: t("email.bonds.carryIntro"),
      lines: [
        { label: t("email.bonds.carryRange", { count: totals.length }), value: t("email.bonds.carryRangeValue", { low: signed(Math.min(...totals), 0), high: signed(Math.max(...totals), 0) }) },
        { label: t("email.bonds.carryFunding"), value: percent(carry.data.funding?.rate_pct) },
      ],
    });
  } else if (!carry.access.allowed) {
    sections.push({ title: t("email.bonds.carry"), locked: { text: t("email.bonds.carryLocked"), cta: t("email.bonds.seePlans"), href: plans } });
  }
  sections[sections.length - 1].link = { label: t("email.bonds.link"), href: `${links.site}/bonds` };
  return { day, sections, preheader: t("email.bonds.preheader", { change: `${signed(bp(10), 1)} bp` }) };
}

/** The e-mail one tier's subscribers get for one market this week. */
export async function weeklyDigest(viewer: Viewer, market: Market, links: Links): Promise<Digest> {
  const t = await translator();
  const name = t(`email.markets.${market}`);
  const built = market === "cse" ? await cseSections(t, viewer, links) : await bondSections(t, viewer, links);
  const when = built.day ? date(built.day) : null;
  return {
    subject: when ? t("email.subject", { market: name, date: when }) : t("email.subjectNoData", { market: name }),
    preheader: built.preheader || t("email.noData"),
    eyebrow: t("email.eyebrow", { tier: t(`tiers.${viewer.tier}`) }),
    heading: when ? t("email.heading", { market: name, date: when }) : t("email.headingNoData", { market: name }),
    sections: built.sections.length ? built.sections : [{ title: name, empty: t("email.noData") }],
    disclaimers: SITE_WIDE_DISCLAIMERS.map((k) => registry.disclaimers[k]?.en).filter((x): x is string => !!x),
    footer: [t("email.footer", { market: name })],
    unsubscribe: { label: t("email.unsubscribe"), href: links.unsubscribe },
  };
}
