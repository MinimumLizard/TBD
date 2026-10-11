"""Migrate the CSE history: replay the old terminal's raw API responses through the new parsers, then reconcile.

    python -m data_platform.migration.cse --old-repo <CSE clone> --chart-archive <archive>/cse_chart_2026-10-11 \\
        --report docs/migration/cse-reconciliation.json

The old repo kept every daily response under data/raw/<session>/, plus the one-year backfill. So, as for the
bonds, the old CSV tables are not copied: they are rebuilt by the new collectors' parse functions and stores, in
the order the old jobs ran, and then compared row by row with the CSVs at the pinned commit.

Then the chart history archived on 2026-10-11 is replayed exactly as the weekly history job would. It fills
the 2026-10-05 session the old daily job missed (audit F4) and nothing else.

Every other old raw file (announcement and dealing caches, interim-report text, annual-report extracts) is
archived as-is, catalogued under source 'legacy_cse', for the models that read them in Phase 3.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

from ..collectors.cse import parse
from ..collectors.cse.collector import API, GET_ENDPOINTS, store, store_indices, store_prices
from ..core import db, rawstore, settings as settings_mod

LEGACY = "legacy_cse"


def _ts(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def run_times(repo: Path) -> dict[str, dt.datetime]:
    """When each old raw session folder was written: the old run log's successful fetch for that session."""
    times = {}
    for r in csv.DictReader((repo / "data" / "runs.csv").open()):
        if r["command"] == "fetch" and r["status"] == "ok":
            times.setdefault(r["session"], _ts(r["run_at_utc"]))
        if r["command"] == "backfill" and r["status"] == "ok":
            times.setdefault("backfill", _ts(r["run_at_utc"]))
    return times


class Replay:
    def __init__(self, conn, store_, repo: Path, commit: str):
        self.conn, self.store, self.repo, self.commit = conn, store_, repo, commit
        self.stats = Counter()

    def fetch(self, path: Path, endpoint: str, params: dict | None, at: dt.datetime) -> tuple[int, bytes]:
        body = path.read_bytes()
        method = "GET" if endpoint in GET_ENDPOINTS else "POST"
        fetch_id, _ = db.record_fetch(
            self.conn, self.store, source_id="cse_api", method=method, url=API + endpoint, params=params,
            http_status=200, body=body, content_type="application/json", fetched_at=at, origin="migration",
            note=f"MinimumLizard/CSE@{self.commit}:{path.relative_to(self.repo)} (fetched_at from old runs.csv)")
        self.stats["raw_files_replayed"] += 1
        return fetch_id, body

    def session(self, d: Path, at: dt.datetime) -> None:
        f_dms, b = self.fetch(d / "dailyMarketSummery.json", "dailyMarketSummery", None, at)
        session, market, tri = parse.session_and_market(b)
        assert session.isoformat() == d.name, f"{d.name}: dailyMarketSummery says {session}"
        f_secs, b_secs = self.fetch(d / "allSecurityCode.json", "allSecurityCode", None, at)
        securities = parse.security_list(b_secs, session)
        f_tr, b_tr = self.fetch(d / "tradeSummary.json", "tradeSummary", None, at)
        f_sec, b_sec = self.fetch(d / "allSectors.json", "allSectors", None, at)
        c = self.conn
        self.stats["security_list"] += store(c, "cse.security_list", securities, ["session_date", "symbol"], f_secs, at)
        self.stats["prices_daily"] += store_prices(c, parse.trade_summary(b_tr, session), f_tr, at)
        self.stats["indices_daily"] += store_indices(c, parse.sectors(b_sec, session), f_sec, at)
        self.stats["indices_daily"] += store_indices(c, tri, f_dms, at)
        self.stats["market_daily"] += store(c, "cse.market_daily", market, ["session_date", "source"], f_dms, at)
        for name in ("aspiData", "snpData", "marketSummery", "marketStatus"):
            if (d / f"{name}.json").exists():
                self.fetch(d / f"{name}.json", name, None, at)
        for p in sorted((d / "companyInfoSummery").glob("*.json")):
            fid, body = self.fetch(p, "companyInfoSummery", {"symbol": p.stem}, at)
            self.stats["company_info_daily"] += store(c, "cse.company_info_daily",
                                                      [parse.company_info(body, p.stem, session)],
                                                      ["session_date", "symbol"], fid, at)
        for p in sorted((d / "companyProfile").glob("*.json")):
            fid, body = self.fetch(p, "companyProfile", {"symbol": p.stem}, at)
            sha = rawstore.sha256_of(body)
            self.stats["company_profiles"] += store(c, "cse.company_profiles",
                                                    [dict(parse.company_profile(body, p.stem), raw_sha256=sha)],
                                                    ["symbol", "raw_sha256"], fid, at)
        self.announcements(d, securities, at)
        c.commit()

    def announcements(self, d: Path, securities: list[dict], at: dt.datetime) -> None:
        by_name = parse.company_codes(securities)
        known = {r["announcement_id"] for r in self.conn.execute("select announcement_id from cse.announcements")}
        f_list, body = self.fetch(d / "approvedAnnouncement.json", "approvedAnnouncement", None, at)
        rows = []
        for a in parse.approved_announcements(body):
            aid = str(a.announcementId)
            if aid in known:
                continue
            detail, detail_fid, endpoint = None, None, None
            for ep in ("getAnnouncementById", "getGeneralAnnouncementById"):
                p = d / ep / f"{aid}.json"
                if p.exists():
                    detail_fid, raw = self.fetch(p, ep, {"announcementId": a.announcementId}, at)
                    detail, endpoint = parse.announcement_detail(raw, ep, aid), ep
                    break
            rows.append(dict(parse.announcement_row(a, detail, by_name), detail_endpoint=endpoint,
                             list_fetch_id=f_list, detail_fetch_id=detail_fid, fetched_at=at))
            known.add(aid)
        f_fin, body = self.fetch(d / "getFinancialAnnouncement.json", "getFinancialAnnouncement", None, at)
        for row in parse.financial_announcements(body, by_name):
            if row["announcement_id"] not in known:
                rows.append(dict(row, detail_endpoint=None, list_fetch_id=f_fin, detail_fetch_id=None, fetched_at=at))
        self.stats["announcements"] += db.insert_facts(self.conn, "cse.announcements", rows, key=["announcement_id"])[0]

    def backfill(self, d: Path, at: dt.datetime) -> None:
        """The old one-off backfill (2026-10-04): saved chart responses for every equity and index."""
        secs = {s["symbol"]: s for s in parse.security_list((d / "allSecurityCode.json").read_bytes(),
                                                             dt.date.fromisoformat(d.name))}
        for p in sorted((d / "companyChartDataByStock").glob("*.json")):
            fid, body = self.fetch(p, "companyChartDataByStock", {"stockId": secs[p.stem]["stock_id"], "period": 5}, at)
            self.stats["prices_backfill"] += store_prices(self.conn, parse.stock_chart(body, p.stem), fid, at)
        codes = dict(parse.sector_ids((d / "allSectors.json").read_bytes()))
        for p in sorted((d / "chartData").glob("*_p5.json")):
            sector_id = int(p.stem.split("_")[0])
            fid, body = self.fetch(p, "chartData", {"chartId": sector_id, "period": 5}, at)
            self.stats["indices_backfill"] += store_indices(self.conn, parse.index_chart(body, codes[sector_id]), fid, at)
        self.conn.commit()

    def chart_archive(self, archive: Path) -> None:
        """Replay the 2026-10-11 chart archive as the weekly history job would: fills only missing sessions."""
        at = dt.datetime(2026, 10, 11, 10, 0, tzinfo=dt.timezone.utc)
        manifest = {(r["endpoint"], r["name"]): r for r in csv.DictReader((archive / "manifest.csv").open())}
        secs = {s["symbol"]: s for s in parse.security_list((archive / "allSecurityCode.json").read_bytes(), at.date())}
        before = self.stats["prices_backfill"]
        for p in sorted((archive / "companyChartDataByStock").glob("*.json")):
            m = manifest[("companyChartDataByStock", p.stem)]
            at_p = dt.datetime.fromisoformat(m["fetched_at_utc"])
            fid, _ = db.record_fetch(self.conn, self.store, source_id="cse_api", method="POST",
                                     url=API + "companyChartDataByStock", params=json.loads(m["params"]),
                                     http_status=200, body=p.read_bytes(), content_type="application/json",
                                     fetched_at=at_p, origin="re-download", note="chart archive 2026-10-11")
            self.stats["prices_backfill_2026_10_11"] += store_prices(self.conn, parse.stock_chart(p.read_bytes(), p.stem),
                                                                     fid, at_p)
        for p in sorted((archive / "chartData").glob("*.json")):
            m = manifest[("chartData", p.stem)]
            at_p = dt.datetime.fromisoformat(m["fetched_at_utc"])
            fid, _ = db.record_fetch(self.conn, self.store, source_id="cse_api", method="POST", url=API + "chartData",
                                     params=json.loads(m["params"]), http_status=200, body=p.read_bytes(),
                                     content_type="application/json", fetched_at=at_p, origin="re-download",
                                     note="chart archive 2026-10-11")
            code = p.stem.split("_", 1)[1]
            self.stats["indices_backfill_2026_10_11"] += store_indices(self.conn, parse.index_chart(p.read_bytes(), code),
                                                                       fid, at_p)
        assert self.stats["prices_backfill"] == before
        self.conn.commit()

    def archive_other(self) -> None:
        """Every other raw file in the old repo, archived untouched (inputs to Phase 3 models)."""
        session_dirs = {p for p in (self.repo / "data" / "raw").iterdir() if p.name[:4].isdigit()}
        for p in sorted((self.repo / "data" / "raw").rglob("*")):
            if p.is_file() and not any(sd in p.parents for sd in session_dirs):
                rel = p.relative_to(self.repo)
                db.record_fetch(self.conn, self.store, source_id=LEGACY, method="GIT",
                                url=f"git://github.com/MinimumLizard/CSE@{self.commit}/{rel}", params={},
                                http_status=200, body=p.read_bytes(), content_type=None,
                                fetched_at=dt.datetime.now(dt.timezone.utc), origin="migration",
                                note="old repo raw file, archived as-is")
                self.stats["legacy_files_archived"] += 1
        # session-folder files that the replay does not parse (e.g. Step 0 screen responses) are archived too
        for sd in sorted(session_dirs):
            for p in sorted(sd.rglob("*")):
                if p.is_file():
                    body = p.read_bytes()
                    if not self.conn.execute("select 1 from ops.raw_objects where sha256 = %s",
                                             (rawstore.sha256_of(body),)).fetchone():
                        rel = p.relative_to(self.repo)
                        db.record_fetch(self.conn, self.store, source_id=LEGACY, method="GIT",
                                        url=f"git://github.com/MinimumLizard/CSE@{self.commit}/{rel}", params={},
                                        http_status=200, body=body, content_type=None,
                                        fetched_at=dt.datetime.now(dt.timezone.utc), origin="migration",
                                        note="old repo raw file not replayed by the migration, archived as-is")
                        self.stats["legacy_files_archived"] += 1
        self.conn.commit()


def load(conn, store_, repo: Path, chart_archive: Path | None) -> dict:
    commit = subprocess.run(["git", "-C", str(repo), "rev-parse", "--short", "HEAD"], capture_output=True,
                            text=True).stdout.strip() or "unknown"
    times = run_times(repo)
    r = Replay(conn, store_, repo, commit)
    sessions = sorted(p for p in (repo / "data" / "raw").iterdir() if p.name[:4].isdigit())
    for i, d in enumerate(sessions):
        r.session(d, times[d.name])
        if i == 0:                      # the old backfill ran right after the first daily fetch
            r.backfill(d, times["backfill"])
    if chart_archive:
        r.chart_archive(chart_archive)
    r.archive_other()
    return dict(r.stats)


# --- reconciliation -------------------------------------------------------------------------------------------

def _num(v):
    """Numbers as the old CSV writer stored them: floats rounded to 8 decimals (old cse/storage.py fmt())."""
    if v in (None, ""):
        return None
    return round(float(v), 8)


def _txt(v):
    return None if v in (None, "") else str(v)


def reconcile(conn, repo: Path) -> dict:
    hist = repo / "data" / "history"
    report = {}

    def compare(name, old: dict, new: dict, expected_extra=lambda k: False) -> None:
        missing = [k for k in old if k not in new]
        extra = [k for k in new if k not in old]
        unexpected = [k for k in extra if not expected_extra(k)]
        differ = [k for k in old if k in new and old[k] != new[k]]
        report[name] = {"old": len(old), "new": len(new), "missing_in_new": len(missing),
                        "extra_in_new": len(extra), "extra_expected": len(extra) - len(unexpected),
                        "extra_unexpected": len(unexpected), "values_differ": len(differ),
                        "examples": {"missing": [list(map(str, k)) for k in missing[:3]],
                                     "unexpected_extra": [list(map(str, k)) for k in unexpected[:3]],
                                     "differ": [[list(map(str, k)), list(map(str, old[k])), list(map(str, new[k]))]
                                                for k in differ[:3]]},
                        "ok": not missing and not unexpected and not differ}

    is_gap_fill = lambda k: k[0] == "2026-10-05" and k[-1] == "backfill"   # noqa: E731 - filled from the 2026-10-11 archive

    old_p = {}
    for r in csv.DictReader((hist / "prices.csv").open(newline="")):
        old_p[(r["date"], r["symbol"], r["source"])] = (
            _num(r["close"]), _num(r["previous_close"]), _num(r["high"]), _num(r["low"]), _num(r["volume"]),
            _num(r["turnover"]), _num(r["turnover_est"]))
    new_p = {}
    for r in conn.execute("select * from cse.prices_daily"):
        vol = r["volume_regular"] if r["source"] == "daily" else r["volume_total"]
        new_p[(str(r["session_date"]), r["symbol"], r["source"])] = (
            _num(r["close"]), _num(r["previous_close"]), _num(r["high"]), _num(r["low"]), _num(vol),
            _num(r["turnover"]), _num(r["turnover_est"]))
    compare("prices", old_p, new_p, is_gap_fill)

    old_i = {(r["date"], r["index"], r["source"]): (_num(r["value"]), _num(r["change"]))
             for r in csv.DictReader((hist / "indices.csv").open(newline=""))}
    new_i = {(str(r["session_date"]), r["index_code"], r["source"]): (_num(r["value"]), _num(r["change"]))
             for r in conn.execute("select * from cse.indices_daily")}
    compare("indices", old_i, new_i, is_gap_fill)

    cols = ["turnover", "volume", "trades", "foreign_buy", "foreign_sell", "listed", "traded", "market_cap", "aspi",
            "spsl20", "astri", "spsl20_tri", "per", "pbv", "dy"]
    old_m = {(r["date"], r["source"]): tuple(_num(r[c]) for c in cols) for r in csv.DictReader((hist / "market.csv").open(newline=""))}
    new_m = {(str(r["session_date"]), r["source"]): tuple(_num(r[c]) for c in cols)
             for r in conn.execute("select * from cse.market_daily")}
    compare("market", old_m, new_m)

    old_a = {(r["id"],): (r["date"], _txt(r["symbol"]), r["company"], r["title"], r["category"], _txt(r["url"]))
             for r in csv.DictReader((hist / "announcements.csv").open(newline=""))}
    new_a = {(r["announcement_id"],): (str(r["announced_date"]), _txt(r["symbol"]), r["company"], r["title"],
                                       r["category"], _txt(r["document_url"]))
             for r in conn.execute("select * from cse.announcements")}
    compare("announcements", old_a, new_a)

    gap = conn.execute("""select count(*) n from cse.prices_daily where session_date = '2026-10-05'""").fetchone()["n"]
    report["gap_2026_10_05_filled_rows"] = gap
    report["value_conflicts"] = conn.execute("select count(*) n from ops.value_conflicts").fetchone()["n"]
    report["ok"] = all(v.get("ok") for v in report.values() if isinstance(v, dict)) and report["value_conflicts"] == 0
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Migrate and reconcile the CSE history")
    ap.add_argument("--old-repo", type=Path, required=True)
    ap.add_argument("--chart-archive", type=Path)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args(argv)
    s = settings_mod.load()
    conn = db.connect(s.database_url)
    db.migrate(conn)
    loaded = load(conn, rawstore.from_settings(s), args.old_repo, args.chart_archive)
    rec = reconcile(conn, args.old_repo)
    report = {"loaded": loaded, "reconciliation": rec,
              "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, default=str) + "\n")
    print(json.dumps(report, indent=2, default=str)[:4000])
    return 0 if rec["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
