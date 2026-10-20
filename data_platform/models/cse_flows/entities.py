"""Who dealt: the rules that turn a dealing notice's account name into one account (an "actor"), and its ownership
group.

The name rules (normalisation, custodian and margin accounts, classification, the owner's confirmed aliases) are the
ownership tracker's, shared with cse_ownership (data_platform/models/_lib/cse_names.py, a line-for-line port of
MinimumLizard/CSE@e05c6f3 cse/ownership/names.py). This file ports what cse/flows.py adds on top: actor_entity (the
phrases around a company's name in a notice), GENERIC_ACCOUNT and the account fallback, and the groups the old
dealings_rows() looked up (cse/ownership/groups.py group_of, read here from cse_ownership's output).
Individuals are never merged unless their normalised names match exactly, or the owner's aliases say so (old rule 5
and rule 6).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .._lib.cse_names import Entity, listed_index, resolve

EQUITY_SUFFIXES = (".N0000", ".X0000")


@dataclass
class Market:
    """What the name rules need from one CSE security list (old analyse.load_market's names and listed index)."""
    names: dict[str, str]           # company code -> company name
    listed: dict[str, str]          # name key -> company code


def market(securities: list[dict]) -> Market:
    equities = [s for s in securities if s["symbol"].endswith(EQUITY_SUFFIXES)]
    return Market({s["symbol"].split(".")[0]: s["name"] for s in sorted(equities, key=lambda s: s["symbol"])},
                  listed_index(equities))


def entity_for(name_as_filed: str, m: Market, aliases: dict | None = None) -> Entity:
    """Old analyse.entity_for: the owner's aliases first; a listed company is keyed by its code and shown under the
    CSE's name for it."""
    e = resolve(name_as_filed, m.listed, aliases or {})
    if e.type == "listed" and e.symbol:
        return Entity("LISTED:" + e.symbol, m.names.get(e.symbol, e.name), "listed", e.symbol, e.via, e.rule)
    return e


# --- old cse/flows.py ---------------------------------------------------------------------------------------------

def actor_entity(account: str, m: Market, aliases: dict | None = None) -> Entity:
    """The entity behind a dealing's account name ('CT Holdings PLC - Common Directors' -> C T Holdings PLC;
    'Mr X (Spouse)': the spouse is not Mr X, so only the suffix forms that name the account holder itself are
    stripped)."""
    # 'Disposal of shares by X', 'Directors of X', 'Nominee Directors of X', 'Shares held by X' -> X
    account = re.sub(r"^\s*(?:(?:purchase|disposal|sale|acquisition)\s+of\s+shares\s+by|(?:nominee\s+)?directors?\s+of|"
                     r"shares?\s+held\s+by|on\s+behalf\s+of)\s+", "", account, flags=re.I)
    # '... are directors of X', 'The said Directors also serve as Directors of X' -> X
    match = re.search(r"\bdirectors?\s+of\s+(?:the\s+)?(.+)$", account, flags=re.I)
    if match and not re.match(r"^\s*(?:nominee\s+)?directors?\s+of", account, re.I):
        account = match.group(1)
    account = re.sub(r"\.\s+(?:Mr|Mrs|Ms|Miss|Dr)\b.*$", "", account)          # 'X Ltd. Mr. Y ...' -> X Ltd
    account = re.sub(r"\s+(?:in\s+which|where|which\s+is)\b.*$", "", account, flags=re.I)
    # 'X, privately held company owned by ...', 'X, a company in which ...' -> X
    account = re.sub(r",\s*(?:a\s+)?(?:privately|private|public|wholly|company|which|in\s+which|where)\b.*$", "",
                     account, flags=re.I)
    # '<company> - Directors', '<company>- Directors / Shareholders', '<company> - Common Directors'
    name = re.sub(r"\s*[-–(]\s*(?:common\s+)?(?:directors?|shareholders?)"
                  r"\b.*$", "", account, flags=re.I)
    name = re.sub(r",\s*(?:a\s+|the\s+)?(?:major|substantial|controlling)\s+shareholders?\b.*$", "", name, flags=re.I)
    return entity_for(name.strip(" -,"), m, aliases)


GENERIC_ACCOUNT = re.compile(r"^\W*(?:shareholders?|n/?a|nil|none|-+|(?:please\s+)?(?:refer|see)\b.*|as per\b.*|attached|"
                             r"related part(?:y|ies)|as mentioned\b.*)\W*$", re.I)


def account_name(account: str, director: str, company: str) -> str:
    """The account that dealt (old flows.dealings_rows): the notice's account, or the director when the account is
    generic ("Shareholders", "N/A", "Please refer attachment"), or "<company> – directors (see notice)" when both
    are generic."""
    name = account if account and not GENERIC_ACCOUNT.match(account) else director
    if not name or GENERIC_ACCOUNT.match(name):
        name = f"{company} – directors (see notice)"
    return name


# --- ownership groups (old cse/ownership/groups.py, as the old dealings_rows() used them) ---------------------------

@dataclass
class Groups:
    """One session's ownership groups: company code -> group key, group key -> its name (cse_ownership's
    models.cse_ownership_detail, the old companies.csv's groups)."""
    of: dict[str, str] = field(default_factory=dict)
    label: dict[str, str] = field(default_factory=dict)

    def target(self, code: str) -> str:
        """The group of the company whose shares were dealt in (a company with no row is its own group)."""
        return self.of.get(code, "LISTED:" + code)

    def actor(self, e: Entity) -> str:
        """The group of the account that dealt: a listed company's group, otherwise the account itself (an unlisted
        holder heads its own group, so a holding company at the top of a group matches it)."""
        return self.of.get(e.symbol, "LISTED:" + e.symbol) if e.type == "listed" else e.key

    def name(self, key: str, default: str) -> str:
        return self.label.get(key, default)
