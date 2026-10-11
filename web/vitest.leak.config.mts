import { defineConfig } from "vitest/config";
import path from "node:path";

// The tier-leak suite: needs a running server (next start) on a database seeded by tests/leak/seed.py.
export default defineConfig({
  resolve: { alias: { "@": path.resolve(import.meta.dirname), "server-only": path.resolve(import.meta.dirname, "tests/stub-server-only.ts") } },
  test: { include: ["tests/leak/**/*.test.ts"], environment: "node", testTimeout: 60_000 },
});
