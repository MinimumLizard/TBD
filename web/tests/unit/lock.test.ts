import { describe, expect, test } from "vitest";

import { locked } from "@/lib/lock";

const basic = (user: string, pass: string) => `Basic ${btoa(`${user}:${pass}`)}`;

describe("the optional site password (lib/lock.ts)", () => {
  test("no password set: the site is open", () => {
    expect(locked(null, undefined)).toBe(false);
    expect(locked(null, "")).toBe(false);
  });
  test("a password set: only the right one opens it, with any user name", () => {
    expect(locked(null, "s3cret-long")).toBe(true);
    expect(locked("Bearer abc", "s3cret-long")).toBe(true);
    expect(locked(basic("janu", "wrong"), "s3cret-long")).toBe(true);
    expect(locked(basic("janu", "s3cret-lon"), "s3cret-long")).toBe(true);
    expect(locked("Basic not-base64!", "s3cret-long")).toBe(true);
    expect(locked(basic("janu", "s3cret-long"), "s3cret-long")).toBe(false);
    expect(locked(basic("", "s3cret-long"), "s3cret-long")).toBe(false);
    expect(locked(basic("a", "pass:with:colons"), "pass:with:colons")).toBe(false);
  });
});
