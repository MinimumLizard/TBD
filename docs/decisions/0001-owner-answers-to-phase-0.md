# 0001 — Owner's answers to the Phase 0 audit

- **Date:** 2026-10-11
- **Status:** Accepted (owner)

## Context

`docs/audit.md` ended with questions and a list of risks. The owner answered in one message:

> "the live pages are for my personal use, what you're building is a product"
> "only use the sources that allow for it or dont make mention of it"
> "Will make it private dw, is there anywhere you'd suggest storing it apart from Github"
> "just do whatever you need to do to give me the best, most accurate, compliant product/website/portal"

## Decisions

1. **The existing sites stay personal tools.** Their advice-like language (buy/sell switch candidates, trade lists,
   GET IN/GET OUT) is the owner's own business and is not to be "fixed" there. None of it is carried into the product;
   the product gets its own wording under the compliance rules (decision 0010).
2. **Data-source rule:** the product uses a source only if its published terms **allow commercial use, or say nothing
   about it**. A source whose terms prohibit commercial use or redistribution is not used. Every source's status is
   recorded with evidence and a check date (decision 0009).
3. **The three existing repositories will be made private by the owner.** History must also live outside GitHub
   (decision 0003).
4. **Mandate:** proceed in the owner's interest towards an accurate, compliant product. The phase gates in the brief
   still apply: stop after each phase. Choices that are costly to reverse, or that need the owner's accounts or
   money, still go to the owner.

## Consequences

- **Crypto launches later.** Its free sources mostly fall under the "prohibited" rule (audit section 7). It needs
  licensed sources first (see architecture "Not building yet").
- **Open risk:** "silent" terms are not permission, so the CSE and PDMO data may still need a licence. The owner has
  accepted that risk. The product can switch off any source per source, by config, within one deploy.
- **Not done:** fixing the old bond repo's 2027 rollover. This session is not permitted to change the existing
  repositories, so the owner applies a two-line change (documented in `docs/roadmap.md`).
