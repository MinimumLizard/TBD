import { describe, expect, it } from "vitest";

import { type Digest, escape, renderHtml, renderText } from "@/lib/email/digest";

const digest: Digest = {
  subject: "ZinvestIQ weekly · Government bonds · week to 16 Oct 2026",
  preheader: "The 10-year point moved +3.0 bp.",
  eyebrow: "Weekly update · Free plan",
  heading: "Government bonds: the week to 16 Oct 2026",
  sections: [
    { title: "The yield curve", lines: [{ label: "10-year yield", value: "11.20%", note: "+3.0 bp on the week", tone: "up" }] },
    { title: "Furthest <from> the curve", table: { head: ["Bond", "From curve"], rows: [{ cells: ["13.00% 2029", "−12.0 bp"], tone: "down" }] } },
    { title: "Unusual", locked: { text: "Part of Plus.", cta: "See the plans", href: "/plans" } },
    { title: "Empty", table: { head: ["A"], rows: [] }, empty: "Nothing this week." },
  ],
  disclaimers: ["Information only."],
  footer: ["You asked for this."],
  unsubscribe: { label: "Stop these e-mails", href: "https://example.org/u?t=a&b" },
};

describe("weekly e-mail", () => {
  it("escapes everything it prints", () => {
    expect(escape(`<a href="x">'&'</a>`)).toBe("&lt;a href=&quot;x&quot;&gt;&#39;&amp;&#39;&lt;/a&gt;");
    const html = renderHtml(digest);
    expect(html).toContain("Furthest &lt;from&gt; the curve");
    expect(html).not.toContain("<from>");
    expect(html).toContain('href="https://example.org/u?t=a&amp;b"');
  });

  it("shows each kind of section, with no scripts or external styles", () => {
    const html = renderHtml(digest);
    for (const s of ["11.20%", "+3.0 bp on the week", "13.00% 2029", "Part of Plus.", "Nothing this week.", "Information only.", "Stop these e-mails"]) {
      expect(html).toContain(s);
    }
    expect(html).not.toMatch(/<script|<link|<style/);
    expect(html).toContain("max-width:600px");
  });

  it("has a plain-text body with the same content", () => {
    const text = renderText(digest);
    expect(text).toContain("10-year yield: 11.20% (+3.0 bp on the week)");
    expect(text).toContain("13.00% 2029 | −12.0 bp");
    expect(text).toContain("Part of Plus. See the plans: /plans");
    expect(text).toContain("Nothing this week.");
    expect(text).toContain("Stop these e-mails: https://example.org/u?t=a&b");
  });
});
