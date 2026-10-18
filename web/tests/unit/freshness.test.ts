import { expect, test } from "vitest";

import { expectedSession, isSession, sessionsBehind } from "@/lib/freshness";

const at = (iso: string) => new Date(iso); // UTC instants; Sri Lanka is UTC+5:30

test("weekends and listed closures are not sessions", () => {
  expect(isSession("cse", "2026-10-10")).toBe(false); // Saturday
  expect(isSession("cse", "2025-12-25")).toBe(false); // listed closure
  expect(isSession("cse", "2026-10-09")).toBe(true);
});

test("before the day's data is published, yesterday's session is the latest expected", () => {
  expect(expectedSession("cse", at("2026-10-09T06:00:00Z"))).toBe("2026-10-08"); // 11:30 in Colombo
  expect(expectedSession("cse", at("2026-10-09T12:00:00Z"))).toBe("2026-10-09"); // 17:30 in Colombo
  expect(expectedSession("cse", at("2026-10-11T12:00:00Z"))).toBe("2026-10-09"); // Sunday -> Friday
});

test("sessions behind", () => {
  expect(sessionsBehind("cse", "2026-10-09", at("2026-10-11T12:00:00Z"))).toBe(0);
  expect(sessionsBehind("cse", "2026-10-07", at("2026-10-09T12:00:00Z"))).toBe(2);
});

test("crypto trades every day; yesterday's UTC close is expected once it has been collected", () => {
  expect(isSession("crypto", "2026-10-18")).toBe(true); // a Sunday
  expect(expectedSession("crypto", at("2026-10-18T00:20:00Z"))).toBe("2026-10-16"); // 05:50 Colombo: not collected yet
  expect(expectedSession("crypto", at("2026-10-18T01:30:00Z"))).toBe("2026-10-17"); // 07:00 Colombo
  expect(expectedSession("crypto", at("2026-10-17T20:00:00Z"))).toBe("2026-10-16"); // 01:30 Colombo on the 18th
  expect(sessionsBehind("crypto", "2026-10-15", at("2026-10-18T01:30:00Z"))).toBe(2); // weekend days count
});
