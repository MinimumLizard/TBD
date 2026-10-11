# 0002 — One private monorepo, six layers

- **Date:** 2026-10-11
- **Status:** Proposed

## Context

Three repos each re-implement fetching, storage, run logs and a site builder (audit §5). The product needs one
platform that grows for years.

## Decision

- One private GitHub monorepo, holding code only.
- Python (managed with `uv`) for collectors and models, in `data_platform/`.
- TypeScript only for the website, in `web/`.
- The six layers of `docs/architecture.md`.
- Python 3.12. pandas as the default data library: it is familiar from R data frames, and the CSE and bond code
  already use it. polars is allowed inside a model where the ported code uses it (the crypto code).

## Alternatives considered

- **Separate repos per layer:** more places for config and versions to drift, for no benefit at this size.
- **All-TypeScript:** would mean rewriting every model away from the scientific Python stack the models are built on
  (cvxpy, scipy, scikit-learn).

## Consequences

- One pull request can change a collector, a model and its page together, with one CI run.
- The repo needs two toolchains (uv and npm); CLAUDE.md lists the commands.
