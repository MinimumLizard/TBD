# CLAUDE.md — read this first

Handover notes between sessions. Keep this file current: future sessions rely on it.

## What this is

A tiered retail market-information portal, mainly for Sri Lankan investors. It is being built by consolidating
three existing personal tools (CSE equities, LKR government bonds, crypto) into one platform. Working name: TBD
(no brand yet).

Owner background: finance, fluent in R, learning Python, not a professional engineer. Explain decisions in plain
language. Prefer boring, well-documented, managed services over clever or self-hosted ones.

## Current phase

**Phase 0 (audit) is done; awaiting the owner's approval before Phase 1.** See `docs/roadmap.md`.

- Audit: `docs/audit.md` (findings, fragility register, data rights, questions).
- Architecture: not yet decided. Phase 1 will write `docs/architecture.md` and `docs/decisions/`.

## Source repositories (read-only until a migration plan is approved)

| Tool | Repo | Live site |
|---|---|---|
| CSE terminal | github.com/MinimumLizard/CSE (`main`) | minimumlizard.github.io/CSE/ |
| Bonds (Nelson-Siegel) | github.com/MinimumLizard/Nelson-Siegel (`main`) | minimumlizard.github.io/Nelson-Siegel/ |
| Crypto terminal | github.com/MinimumLizard/Crypto (code: `claude/minilizard-crypto-terminal-e6g100`; data: `data`) | minimumlizard.github.io/Crypto/ |

They are public, so they can be cloned without credentials:
`GIT_LFS_SKIP_SMUDGE=1 git clone https://github.com/MinimumLizard/<repo>`. Clone into a scratch folder, never inside
this repo.

## Hard rules (from the owner's brief; do not relax without written approval)

1. **Do not modify, move or delete anything in the existing repos or their data** until the owner approves a migration
   plan. The current sites must keep running and collecting throughout.
2. **Never lose or rewrite historical data.** Every migration is verified by row counts and checksums against the
   source, and must be repeatable. (Baselines: `docs/audit.md` Appendix A.)
3. **No secrets in the repo.** Use environment variables and `.env.example`.
4. **Information, tools and education only.** No buy/sell/hold language, no price targets, no "picks", no personalised
   recommendations anywhere: code, copy or model output labels. Sri Lanka's SEC penalises unlicensed investment advice.
   One place for disclaimers; a copy-lint check fails the build on banned phrases.
5. **Paid data never reaches an unentitled browser.** Tier checks happen on the server, not by hiding things in the
   front end.
6. **Stop at the end of each phase and wait for approval.**
7. When unsure, or when a choice is costly to reverse, ask the owner first.

## Conventions

- Small commits on feature branches, with plain-language messages.
- Tests for every collector and model. Nothing merges with failing tests.
- Update `docs/roadmap.md` and `CHANGELOG.md` at the end of every session.
- Numbers in docs are measured by a command, not typed in; cite the command.

## Commands

None yet: no code exists. Phase 1 will define them.
