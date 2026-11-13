// Sign-ups (lib/signup.ts): what the form accepts before anything reaches the database.
import { describe, expect, it } from "vitest";

import { CONSENT_VERSION, cleanEmail, parseSignup, signupThanksPath } from "@/lib/signup";

const form = (fields: Record<string, string>) => ({ get: (k: string) => fields[k] ?? null });

describe("sign-up form", () => {
  it("accepts an address with the consent box ticked, lower-cased and without spaces around it", () => {
    expect(parseSignup(form({ email: "  Nimal@Example.COM ", consent: "yes", weekly: "yes", type: "new", answer: "cash" })))
      .toEqual({ email: "nimal@example.com", type: "new", answer: "cash", weekly: true });
    expect(parseSignup(form({ email: "a.b+c@mail.example.lk", consent: "yes" })))
      .toEqual({ email: "a.b+c@mail.example.lk", type: null, answer: null, weekly: false });
  });

  it("stores nothing without consent: the box is never assumed", () => {
    expect(parseSignup(form({ email: "nimal@example.com" }))).toBeNull();
    expect(parseSignup(form({ email: "nimal@example.com", consent: "no" }))).toBeNull();
    expect(parseSignup(form({ email: "nimal@example.com", consent: "on" }))).toBeNull();
  });

  it("refuses what is not an address", () => {
    for (const bad of ["", "nimal", "nimal@", "@example.com", "nimal@example", "ni mal@example.com", "nimal@@example.com",
                       "nimal@example..com", "<nimal@example.com>", "nimal@example.com,other@example.com",
                       "nimal@-example.com", `${"x".repeat(250)}@example.com`]) {
      expect(cleanEmail(bad), bad).toBeNull();
    }
    expect(cleanEmail(undefined)).toBeNull();
    expect(cleanEmail(42)).toBeNull();
  });

  it("keeps a starting path only when it is a real one", () => {
    const r = parseSignup(form({ email: "a@example.com", consent: "yes", type: "new", answer: "bonds" }));
    expect(r).toEqual({ email: "a@example.com", type: null, answer: null, weekly: false });
  });

  it("names the consent wording by date, and builds the thank-you address safely", () => {
    expect(CONSENT_VERSION).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(signupThanksPath("ok", "/start/new/cash")).toBe("/signup/thanks?r=ok&from=%2Fstart%2Fnew%2Fcash");
  });
});
