// The weekly e-mail's layout (docs/plan-retail-features.md §2). Pure: it turns an already tier-checked digest into
// the HTML and plain-text bodies an e-mail service sends. Every number in a digest was read through the site's
// single tier check (lib/email/weekly.ts), once per market and tier, so one subscriber's e-mail is the same as every
// other subscriber's on that tier: never personalised.
export type Tone = "up" | "down" | "flat";

export interface Line {
  label: string;
  value: string;
  note?: string;
  tone?: Tone;
}

export interface Table {
  head: string[];
  rows: { cells: string[]; tone?: Tone }[];
}

export interface Section {
  title: string;
  intro?: string;
  lines?: Line[];
  table?: Table;
  empty?: string; // shown instead of lines/table when there is nothing to show
  locked?: { text: string; cta: string; href: string };
  link?: { label: string; href: string };
}

export interface Digest {
  subject: string;
  preheader: string; // the one line an inbox shows after the subject
  heading: string;
  eyebrow: string;
  sections: Section[];
  disclaimers: string[];
  footer: string[];
  unsubscribe: { label: string; href: string };
}

const COLOURS = { navy: "#0b2545", accent: "#0f7c86", gold: "#e09f3e", text: "#0f1b2d", muted: "#5a6a80",
                  border: "#dfe5ee", soft: "#f4f7fb", up: "#12805c", down: "#c2412d" };

export function escape(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function colour(tone: Tone | undefined): string {
  return tone === "up" ? COLOURS.up : tone === "down" ? COLOURS.down : COLOURS.text;
}

function sectionHtml(s: Section): string {
  const parts: string[] = [];
  parts.push(`<h2 style="margin:0 0 8px;font-size:17px;color:${COLOURS.navy}">${escape(s.title)}</h2>`);
  if (s.intro) parts.push(`<p style="margin:0 0 12px;color:${COLOURS.muted};font-size:14px">${escape(s.intro)}</p>`);
  if (s.locked) {
    parts.push(`<div style="background:${COLOURS.soft};border:1px dashed ${COLOURS.border};border-radius:8px;padding:12px 14px;font-size:14px">` +
      `${escape(s.locked.text)} <a href="${escape(s.locked.href)}" style="color:${COLOURS.accent};font-weight:700">${escape(s.locked.cta)}</a></div>`);
  } else if (s.empty && !(s.lines?.length || s.table?.rows.length)) {
    parts.push(`<p style="margin:0;color:${COLOURS.muted};font-size:14px">${escape(s.empty)}</p>`);
  } else {
    if (s.lines?.length) {
      const rows = s.lines.map((l) =>
        `<tr><td style="padding:6px 0;border-bottom:1px solid ${COLOURS.border};font-size:14px">${escape(l.label)}` +
        (l.note ? `<br><span style="color:${COLOURS.muted};font-size:12px">${escape(l.note)}</span>` : "") +
        `</td><td align="right" style="padding:6px 0;border-bottom:1px solid ${COLOURS.border};font-size:15px;font-weight:700;color:${colour(l.tone)};white-space:nowrap">${escape(l.value)}</td></tr>`);
      parts.push(`<table role="presentation" width="100%" cellpadding="0" cellspacing="0">${rows.join("")}</table>`);
    }
    if (s.table?.rows.length) {
      const head = s.table.head.map((h, i) =>
        `<th align="${i === 0 ? "left" : "right"}" style="padding:6px 4px;font-size:12px;color:${COLOURS.muted};border-bottom:1px solid ${COLOURS.border}">${escape(h)}</th>`).join("");
      const body = s.table.rows.map((r) => `<tr>${r.cells.map((c, i) =>
        `<td align="${i === 0 ? "left" : "right"}" style="padding:6px 4px;font-size:14px;border-bottom:1px solid ${COLOURS.border};${i === r.cells.length - 1 ? `font-weight:700;color:${colour(r.tone)};` : ""}">${escape(c)}</td>`).join("")}</tr>`).join("");
      parts.push(`<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:4px"><tr>${head}</tr>${body}</table>`);
    }
  }
  if (s.link) parts.push(`<p style="margin:12px 0 0;font-size:14px"><a href="${escape(s.link.href)}" style="color:${COLOURS.accent};font-weight:700">${escape(s.link.label)} →</a></p>`);
  return `<tr><td style="padding:20px 24px;border-top:1px solid ${COLOURS.border}">${parts.join("")}</td></tr>`;
}

/** The e-mail's HTML: tables and inline styles only, which is what e-mail programs display reliably. */
export function renderHtml(d: Digest): string {
  const font = "Manrope,'Segoe UI',Helvetica,Arial,sans-serif";
  return [
    `<div style="background:${COLOURS.soft};padding:24px 8px;font-family:${font};color:${COLOURS.text}">`,
    `<span style="display:none;max-height:0;overflow:hidden">${escape(d.preheader)}</span>`,
    `<table role="presentation" align="center" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:0 auto;background:#ffffff;border:1px solid ${COLOURS.border};border-radius:12px;overflow:hidden">`,
    `<tr><td style="background:${COLOURS.navy};padding:20px 24px;color:#ffffff">`,
    `<div style="font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#b9d6e6;font-weight:600">${escape(d.eyebrow)}</div>`,
    `<div style="font-size:22px;font-weight:800;margin-top:4px">${escape(d.heading)}</div></td></tr>`,
    ...d.sections.map(sectionHtml),
    `<tr><td style="padding:16px 24px;background:${COLOURS.soft};font-size:12px;color:${COLOURS.muted}">`,
    ...d.disclaimers.map((x) => `<p style="margin:0 0 8px">${escape(x)}</p>`),
    ...d.footer.map((x) => `<p style="margin:0 0 8px">${escape(x)}</p>`),
    `<p style="margin:0"><a href="${escape(d.unsubscribe.href)}" style="color:${COLOURS.muted}">${escape(d.unsubscribe.label)}</a></p>`,
    `</td></tr></table></div>`,
  ].join("\n");
}

/** The plain-text body, for e-mail programs that show no HTML (and for spam filters, which expect one). */
export function renderText(d: Digest): string {
  const out: string[] = [d.heading.toUpperCase(), d.eyebrow, ""];
  for (const s of d.sections) {
    out.push(s.title, "-".repeat(Math.min(60, s.title.length)));
    if (s.intro) out.push(s.intro);
    if (s.locked) out.push(`${s.locked.text} ${s.locked.cta}: ${s.locked.href}`);
    else if (s.empty && !(s.lines?.length || s.table?.rows.length)) out.push(s.empty);
    else {
      for (const l of s.lines ?? []) out.push(`  ${l.label}: ${l.value}${l.note ? ` (${l.note})` : ""}`);
      if (s.table?.rows.length) {
        out.push(`  ${s.table.head.join(" | ")}`);
        for (const r of s.table.rows) out.push(`  ${r.cells.join(" | ")}`);
      }
    }
    if (s.link) out.push(`${s.link.label}: ${s.link.href}`);
    out.push("");
  }
  out.push(...d.disclaimers, "", ...d.footer, `${d.unsubscribe.label}: ${d.unsubscribe.href}`);
  return out.join("\n");
}
