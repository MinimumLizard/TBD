import { describe, expect, it } from "vitest";

import { isBot, parseForm, refererPath, sameOrigin, senderAddress, senderKey, sitePath, thanksPath } from "@/lib/feedback";

const form = (fields: Record<string, string | undefined>) => new Map(Object.entries(fields));

describe("feedback form", () => {
  it("accepts a page vote and a message, trimmed", () => {
    expect(parseForm(form({ kind: "page_vote", useful: "no" }), "/bonds")).toEqual({ kind: "page_vote", page: "/bonds", useful: false });
    expect(parseForm(form({ kind: "message", topic: "idea", message: "  Bill yields please \n", page: "/cse" }), null))
      .toEqual({ kind: "message", page: "/cse", topic: "idea", message: "Bill yields please" });
  });

  it("refuses anything missing or out of bounds", () => {
    for (const fields of [
      { kind: "page_vote" }, { kind: "page_vote", useful: "maybe" }, { kind: "comment" }, {},
      { kind: "message", topic: "tips", message: "hello" }, { kind: "message", message: "hello" },
      { kind: "message", topic: "idea", message: "  a " }, { kind: "message", topic: "idea", message: "x".repeat(2001) },
    ]) expect(parseForm(form(fields), "/")).toBeNull();
  });

  it("takes the page only as a path on this site", () => {
    expect(sitePath("/bonds/LK0001")).toBe("/bonds/LK0001");
    for (const bad of ["https://evil.example/", "//evil.example/x", "/a b", "/x?y=1", "bonds", 7, null]) expect(sitePath(bad)).toBeNull();
    expect(parseForm(form({ kind: "page_vote", useful: "yes", page: "https://evil.example/" }), "/cse")?.page).toBe("/cse");
    expect(refererPath("https://zinvestiq.lk/cse/shares?q=1", "zinvestiq.lk")).toBe("/cse/shares");
    expect(refererPath("https://evil.example/cse", "zinvestiq.lk")).toBeNull();
    expect(refererPath("not a url", "zinvestiq.lk")).toBeNull();
  });

  it("refuses a post from another site", () => {
    expect(sameOrigin(null, "zinvestiq.lk")).toBe(true);
    expect(sameOrigin("https://zinvestiq.lk", "zinvestiq.lk")).toBe(true);
    expect(sameOrigin("https://evil.example", "zinvestiq.lk")).toBe(false);
    expect(sameOrigin("null", "zinvestiq.lk")).toBe(false);
  });

  it("drops a bot that fills the hidden field", () => {
    expect(isBot(form({ website: "http://spam" }))).toBe(true);
    expect(isBot(form({}))).toBe(false);
  });
});

describe("sender key", () => {
  it("is a keyed hash, never the address, and switched off on a deployed site without a secret", () => {
    const key = senderKey("203.0.113.9", { FEEDBACK_KEY_SECRET: "s3" } as unknown as NodeJS.ProcessEnv);
    expect(key).toMatch(/^[0-9a-f]{32}$/);
    expect(key).not.toContain("203");
    expect(senderKey("203.0.113.9", { FEEDBACK_KEY_SECRET: "other" } as unknown as NodeJS.ProcessEnv)).not.toBe(key);
    expect(senderKey("203.0.113.9", {} as unknown as NodeJS.ProcessEnv)).toMatch(/^[0-9a-f]{32}$/);
    expect(senderKey("203.0.113.9", { VERCEL: "1" } as unknown as NodeJS.ProcessEnv)).toBeNull();
    expect(senderKey("203.0.113.9", { APP_ENV: "production" } as unknown as NodeJS.ProcessEnv)).toBeNull();
  });

  it("uses the first forwarded address", () => {
    expect(senderAddress(new Headers({ "x-forwarded-for": " 203.0.113.9 , 10.0.0.1" }))).toBe("203.0.113.9");
    expect(senderAddress(new Headers())).toBe("unknown");
  });

  it("sends the visitor back through the thank-you page", () => {
    expect(thanksPath("limited", "/bonds/x y")).toBe("/feedback/thanks?r=limited&from=%2Fbonds%2Fx%20y");
  });
});
