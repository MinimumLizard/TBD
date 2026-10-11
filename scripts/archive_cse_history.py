"""Save the CSE's one-year price history for every ordinary share and every index, untouched, with fingerprints.

Why: the CSE terminal missed the 2026-10-05 session (docs/audit.md, F4). The CSE's chart endpoints still serve that
day's close, high, low and volume, but only for a rolling ~240 sessions. Archiving the raw responses now means the
day can be restored in Phase 2 even if the endpoint changes. It also gives an independent copy of the year the old
repo backfilled, to reconcile against.

Read-only towards cse.lk, polite like the original (one request at a time, 1 s apart, honest User-Agent).

    python scripts/archive_cse_history.py --out path/to/archive/cse_chart_<date>

Output: <out>/<endpoint>/<name>.json (raw bytes as served), and <out>/manifest.csv (url, params, sha256, bytes,
first/last bar date, rows, status).
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import sys
import time
from pathlib import Path

import requests

BASE = "https://www.cse.lk/api/"
USER_AGENT = "tbd-archive/0.1 (one-off archive of public CSE chart history)"
SLT = dt.timezone(dt.timedelta(hours=5, minutes=30))
EQUITY_SUFFIXES = (".N0000", ".X0000")


def call(session: requests.Session, method: str, endpoint: str, **params) -> bytes:
    last = None
    for attempt in range(4):
        time.sleep(1.0 if attempt == 0 else 2 ** attempt)
        try:
            r = (session.get(BASE + endpoint, timeout=30) if method == "GET"
                 else session.post(BASE + endpoint, data=params, timeout=30))
            if r.status_code == 200:
                return r.content
            last = f"HTTP {r.status_code}"
        except requests.RequestException as exc:
            last = str(exc)
    raise RuntimeError(f"{endpoint} {params}: {last}")


def day(ms: int) -> str:
    return dt.datetime.fromtimestamp(ms / 1000, SLT).date().isoformat()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    rows = []

    def save(endpoint: str, name: str, body: bytes, params: dict, series_key: str, t_key: str) -> None:
        path = args.out / endpoint / f"{name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        data = json.loads(body)
        bars = data.get(series_key, []) if isinstance(data, dict) else data
        dates = sorted(day(b[t_key]) for b in bars if b.get(t_key))
        rows.append({"endpoint": endpoint, "name": name, "params": json.dumps(params),
                     "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body), "rows": len(dates),
                     "first": dates[0] if dates else "", "last": dates[-1] if dates else "",
                     "has_2026_10_05": "2026-10-05" in dates,
                     "fetched_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")})

    args.out.mkdir(parents=True, exist_ok=True)
    securities_raw = call(s, "GET", "allSecurityCode")
    (args.out / "allSecurityCode.json").write_bytes(securities_raw)
    securities = json.loads(securities_raw)
    sectors_raw = call(s, "POST", "allSectors")
    (args.out / "allSectors.json").write_bytes(sectors_raw)

    equities = [x for x in securities if x["symbol"].endswith(EQUITY_SUFFIXES)]
    for i, sec in enumerate(equities, 1):
        params = {"stockId": sec["id"], "period": 5}
        try:
            save("companyChartDataByStock", sec["symbol"], call(s, "POST", "companyChartDataByStock", **params),
                 params, "chartData", "t")
        except Exception as exc:  # noqa: BLE001 - recorded, run continues
            rows.append({"endpoint": "companyChartDataByStock", "name": sec["symbol"], "params": json.dumps(params),
                         "sha256": "", "bytes": "", "rows": "", "first": "", "last": "", "has_2026_10_05": "",
                         "fetched_at_utc": f"FAILED: {exc}"[:200]})
        if i % 50 == 0:
            print(f"{i}/{len(equities)}", file=sys.stderr, flush=True)
    for sec in json.loads(sectors_raw):
        params = {"chartId": sec["sectorId"], "period": 5}
        save("chartData", f"{sec['sectorId']}_{sec['symbol']}".replace("/", "-"),
             call(s, "POST", "chartData", **params), params, "", "d")

    with (args.out / "manifest.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    failed = sum(1 for r in rows if str(r["fetched_at_utc"]).startswith("FAILED"))
    have = sum(1 for r in rows if r["has_2026_10_05"] is True)
    print(f"done: {len(rows)} series, {failed} failed, {have} include 2026-10-05")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
