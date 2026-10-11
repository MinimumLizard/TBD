# 0015 — Phase 3 implementation choices (models)

- **Date:** 2026-10-11
- **Status:** Proposed (part of the Phase 3 approval)

## Decisions

1. **Model outputs are recomputed, not appended, and every change is kept.** Models run in full each time from
   the facts (all history takes under a minute locally: 42 s for bonds, 7 s for the CSE), so a rule change can never leave half the history under old
   rules. The writer only touches rows whose value changed (to 1e-9, the parity tolerance) and first copies the old
   row to `models.revisions`, which the database keeps append-only. A run that saw the same inputs as the last one
   but produced different outputs is flagged as non-deterministic.
2. **One table per output shape**, each keyed by `method_version` (architecture §5). Versions never mix: the site
   reads only a model's current version.
3. **A manifest lists several versions at once.** Exactly one is `current` (shown on the site). Others can be
   `reference` (kept running beside it for comparison) or `retired` (no longer computed; rows kept). Version 1 of
   every bond model is the old tool, kept as the reference series for the parallel run.
4. **Tiers live only in `config/entitlements.yaml`**, not in each manifest as the architecture's example showed.
   Which feature is in which tier is the owner's business decision, so it sits in one file the owner edits; the
   registry refuses a model with no tier.
5. **Version 1 ports run on the old tool's own schema.** The old bond methods were SQL against SQLite; version 1
   rebuilds that schema in memory from the platform's facts and runs the ported code against it. This is why
   parity is exact rather than approximate. Comments and names in ported code are reworded to neutral language
   (hard rule 4); the arithmetic is unchanged.
6. **`bond_identity` version 1 starts from the old tool's bond list**, migrated as a fact
   (`bonds.legacy_reference`, from the database at the audited commit). Some of the old tool's labels and coupons
   were learned by earlier versions of its parsers and exist nowhere else; without them version 1 cannot reproduce
   the old quotes (finding P1). The list is pinned by its SHA-256 in the manifest.
7. **Parity runs in memory and compares against the old tool itself.** The models run on the migrated facts
   without writing anything; their outputs are compared with the old database's tables, and, for calculations the
   old tool never stored (liquidity, execution gap, carry, the CSE panels), with the old code imported from a
   read-only clone and run on the old data. No golden files are committed: the repo is public and data stays out
   of git (decision 0012). The reports (counts and differences only) are in `docs/migration/parity-*.json`.
8. **Decision 0014 is implemented as `bond_identity` 2.0.0 and `bond_ns_curve` 2.0.0**, with the downstream bond
   models at 1.1.0 (same method, reading the new curve). They are the current versions; version 1 runs beside them.
9. **The CSE models are computed for every share and every session**, where the old terminal computed them for
   its watchlist on its latest session. Percentages are computed from the published prices rather than taken from
   the CSE's rounded figures (they agree to the CSE's rounding).
10. **Scope of this phase:** all bond models (B1, B3–B11) and the CSE market summary and share metrics (C1, C2).
    The remaining CSE models (corporate actions and total returns, ownership, directors' dealings and flows,
    fundamentals, the risk and portfolio estimates) need facts the platform does not collect yet and owner
    confirmations kept in the old repo; they are listed as the next model work (roadmap). The old terminal's
    personal trade list and live portfolio record are not ported (audit §8).

## Consequences

- The database holds both versions of every bond model while the reference series runs: about 120 MB of model
  outputs today, most of it pair z-scores (measured with `pg_total_relation_size` on the local database, 2026-10-11).
- Retiring version 1 after the parallel run is a one-line manifest change (`status: retired`).
