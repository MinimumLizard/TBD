// Structural rules that keep the tier check impossible to bypass.
import fs from "node:fs";
import path from "node:path";
import { expect, test } from "vitest";

import { ALL_PAGES, DETAIL_PAGES, MODEL_ROUTES } from "@/lib/routes";
import { MODEL_NAMES } from "@/lib/registry";

const ROOT = path.join(__dirname, "..", "..");

function sources(dir: string): string[] {
  const out: string[] = [];
  for (const e of fs.readdirSync(path.join(ROOT, dir), { withFileTypes: true })) {
    const rel = path.join(dir, e.name);
    if (e.isDirectory()) out.push(...sources(rel));
    else if (/\.(ts|tsx)$/.test(e.name)) out.push(rel);
  }
  return out;
}

const files = [...sources("app"), ...sources("components"), ...sources("lib")];
const text = (f: string) => fs.readFileSync(path.join(ROOT, f), "utf8");

test("only lib/db.ts talks to the database", () => {
  const offenders = files.filter((f) => f !== path.join("lib", "db.ts") && /from "pg"/.test(text(f)));
  expect(offenders).toEqual([]);
});

test("only the data layer reads model outputs, and it always goes through the tier check", () => {
  // any import of the db module, however the path is written
  const importsDb = (f: string) => /from ["'][^"']*(\/|^)db["']/.test(text(f)) || /from ["']@\/lib\/db["']/.test(text(f));
  for (const f of files.filter((f) => importsDb(f) && f !== path.join("lib", "db.ts"))) {
    expect(f.startsWith(path.join("lib", "data")), `${f} imports the database module`).toBe(true);
  }
  for (const f of sources(path.join("lib", "data"))) {
    if (f.endsWith("common.ts")) continue;
    if (f.endsWith("feedback.ts")) {
      // the one write: it may call submitFeedback and nothing that reads
      expect(text(f), f).not.toMatch(/readOutput|buildQuery/);
      continue;
    }
    // every exported value is a function that returns through withModel(), which calls authorize()
    const exported = (text(f).match(/^export (async )?function \w+|^export const \w+/gm) ?? []).length;
    const guarded = (text(f).match(/return withModel\(/g) ?? []).length;
    expect(guarded, f).toBe(exported);
  }
});

test("browser components never import server code", () => {
  for (const f of files.filter((f) => text(f).startsWith('"use client"'))) {
    expect(text(f), f).not.toMatch(/@\/lib\/(db|data|entitlements|viewer)/);
  }
});

test("every model has its routes listed, and every listed page is checked", () => {
  expect(Object.keys(MODEL_ROUTES).sort()).toEqual([...MODEL_NAMES].sort());
  for (const r of Object.values(MODEL_ROUTES)) for (const p of r.pages) expect([...ALL_PAGES, ...DETAIL_PAGES]).toContain(p);
});

test("no user-facing text is written in pages and components (it lives in messages/)", () => {
  // JSX text nodes of three or more letters in a row are a sign of copy written in code.
  for (const f of files.filter((f) => f.endsWith(".tsx"))) {
    const jsxText = text(f).match(/>\s*[A-Za-z][A-Za-z ,.'-]{6,}\s*</g) ?? [];
    expect(jsxText, f).toEqual([]);
  }
});
