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
