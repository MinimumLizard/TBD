"""Find the current file links on the CBSL's statistical-tables pages. Pure: page bytes in, links out.

The CBSL renames a file each time it updates it (table4.04_20261012.xlsx is table 4.04 as updated on 12 October
2026), so the address can never be typed in; it is read from the page every run. A link is recognised by BOTH its
file name and its link text, and each wanted table must be found exactly once: a page that lists none, or two,
has changed and the run fails rather than guessing.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from urllib.parse import urljoin

from bs4 import BeautifulSoup

BASE = "https://www.cbsl.gov.lk"
PAGES = {
    "monetary-sector": BASE + "/en/statistics/statistical-tables/monetary-sector",
    "fiscal-sector": BASE + "/en/statistics/statistical-tables/fiscal-sector",
}


@dataclass(frozen=True)
class Wanted:
    dataset: str
    page: str
    file: re.Pattern          # the file name, with its date as group 1 (YYYYMMDD)
    text: re.Pattern          # the link text


WANTED = [
    Wanted("cbsl_4.04", "monetary-sector", re.compile(r"/table4\.04_(\d{8})\.xlsx$", re.I),
           re.compile(r"interest rates\s*-\s*monthly", re.I)),
    Wanted("cbsl_4.03", "monetary-sector", re.compile(r"/table4\.03_(\d{8})\.xlsx$", re.I),
           re.compile(r"interest rates\s*-\s*annual", re.I)),
    Wanted("cbsl_tbill_auctions", "fiscal-sector", re.compile(r"/Treasury_Bill_Auctions_(\d{8})_e\.xlsx$", re.I),
           re.compile(r"treasury bill auctions\s*-\s*weekly", re.I)),
]


@dataclass(frozen=True)
class FileLink:
    dataset: str
    url: str
    file_date: dt.date
    label: str


class IndexChanged(RuntimeError):
    """A statistical-tables page no longer lists a wanted file exactly once."""


def parse_index(html: bytes | str, page: str) -> list[FileLink]:
    """Every wanted file on one page (`page` is a key of PAGES)."""
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for want in (w for w in WANTED if w.page == page):
        found = {}
        for a in soup.find_all("a", href=True):
            href = urljoin(BASE + "/", a["href"].strip())
            m = want.file.search(href)
            text = " ".join(a.get_text(" ", strip=True).split())
            if m and want.text.search(text):
                found[href] = FileLink(want.dataset, href, dt.datetime.strptime(m.group(1), "%Y%m%d").date(), text)
        if len(found) != 1:
            raise IndexChanged(f"{page}: expected one link for {want.dataset}, found {len(found)}: {sorted(found)}")
        out.extend(found.values())
    return out
