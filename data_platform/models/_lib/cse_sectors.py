"""Sector of each CSE share: the CSE's company-profile label mapped onto the 20 S&P/CSE industry-group indices (audit
C4). A line-for-line port of MinimumLizard/CSE@e05c6f3 cse/sectors.py; the owner's per-share assignments
(config/sector_overrides.yaml) arrive as data (cse.sector_overrides, stored by data_platform/jobs/reviews.py before
each run) instead of being read from the file here.

The CSE's labels are inconsistent: case, commas and spacing vary, some labels are GICS sub-industries or raw GICS codes,
and a few are legacy CSE sector names. Resolution order:
  1. the owner's assignment for the share (config/sector_overrides.yaml);
  2. an exact match to an industry-group index name after normalising case, punctuation and spacing;
  3. LABEL_ALIASES: a GICS sub-industry mapped to its industry group (objective, per GICS).
Anything else is unclassified (the portfolio lab leaves such a share out of its universe, naming the reason).
"""
from __future__ import annotations

import re

INDUSTRY_GROUPS = (
    "Energy", "Materials", "Capital Goods", "Commercial & Professional Services", "Transportation",
    "Automobiles & Components", "Consumer Durables & Apparel", "Consumer Services", "Retailing",
    "Food & Staples Retailing", "Food, Beverage & Tobacco", "Household & Personal Products",
    "Health Care Equipment & Services", "Banks", "Diversified Financials", "Insurance",
    "Software & Services", "Telecommunication Services", "Utilities",
    "Real Estate Management & Development",
)


def key(label: str) -> str:
    return re.sub(r"[^A-Z]", "", re.sub(r"^\s*[\d\s-]+", "", label or "").upper())


_BY_KEY = {key(g): g for g in INDUSTRY_GROUPS}

# GICS sub-industry (or sector-level code) -> GICS industry group. Only unambiguous cases.
LABEL_ALIASES = {
    key("Diversified Financial"): "Diversified Financials",
    key("Diversified Financial Services"): "Diversified Financials",
    key("Investment Banking & Brokerage"): "Diversified Financials",
    key("Consumer Finance"): "Diversified Financials",
    key("Property & Casualty Insurance"): "Insurance",
    key("Multi-line Insurance"): "Insurance",
    key("Application Software"): "Software & Services",
    key("Independent Power Producers & Energy Traders"): "Utilities",
    key("Real Estate Development"): "Real Estate Management & Development",
    key("Real Estate (6010)"): "Real Estate Management & Development",
    key("Real Estate Management&Development"): "Real Estate Management & Development",
}


def load_overrides(data: dict | None) -> dict[str, str]:
    """{"overrides": {symbol: industry group}} (the YAML file's content) -> symbol -> industry group. Old
    load_overrides, given the parsed file instead of its path. A group that is not one of the 20 is an error."""
    out = {}
    for sym, group in ((data or {}).get("overrides") or {}).items():
        if group not in INDUSTRY_GROUPS:
            raise ValueError(f"sector overrides: {sym} -> {group!r} is not one of the 20 industry groups")
        out[sym] = group
    return out


def classify(symbol: str, label: str | None, overrides: dict[str, str]) -> str | None:
    if symbol in overrides:
        return overrides[symbol]
    k = key(label or "")
    return _BY_KEY.get(k) or LABEL_ALIASES.get(k)
