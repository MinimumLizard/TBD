"""CSE parity: the market summary and per-share metrics against the old CSE terminal's own code.

    python -m data_platform.migration.parity cse --old-code <CSE clone> --report docs/migration/parity-cse.json

The old terminal computed Panels A and B for its latest session only, at build time, and stored no history of
them. So for every session it kept raw files for (data/raw/<session>/), the old code is imported from a read-only
clone and run on its own history files, cut off at that session, exactly as build_context() did; and the new models
are run in memory on the migrated facts. 2026-10-05 is left out on the new side, because the old terminal never
had it (its daily job missed that session; Phase 2 restored it).

Percentages the CSE publishes rounded (the per-share and per-index percentage change) are compared to that
rounding, 0.005 percentage points; everything else to 1e-9.
"""
from __future__ import annotations

from pathlib import Path

from .parity import _keyed, compare, old_code, run_chain

MISSED_SESSION = "2026-10-05"
ROUNDED = 5e-5           # the CSE's percentages carry two decimals of a percent


def cse_parity(conn, old_code_dir: Path) -> dict:
    root = Path(old_code_dir)
    new = run_chain(conn, ["cse_market_tape", "cse_security_metrics"],
                    {"cse_market_tape": {"exclude_sessions": [MISSED_SESSION]},
                     "cse_security_metrics": {"exclude_sessions": [MISSED_SESSION]}})
    sessions = sorted(p.name for p in (root / "data" / "raw").iterdir()
                      if p.is_dir() and (p / "tradeSummary.json").exists() and (p / "allSectors.json").exists())

    idx_exact, idx_rounded, market, secs, sec_pct = {}, {}, {}, {}, {}
    with old_code(root) as load:
        metrics, config = load("cse.metrics"), load("cse.config")
        universe = config.load_universe(root / "config" / "universe.yaml")
        all_prices = metrics.load_prices(root / "data" / "history" / "prices.csv")
        all_indices = metrics.load_indices(root / "data" / "history" / "indices.csv")
        all_market = metrics.load_market(root / "data" / "history" / "market.csv")
        for s in sessions:
            prices = all_prices[all_prices["date"] <= s]
            indices = all_indices[all_indices["date"] <= s]
            market_df = all_market[all_market["date"] <= s].reset_index(drop=True)
            sess = metrics.load_session(root / "data" / "raw" / s)
            calendar = metrics.session_calendar(indices)
            aspi = indices[indices["index"] == metrics.ASPI].set_index("date")["value"].sort_index()

            # Panel A: indices (build_context's headline, TRI and sector rows)
            for sec in sess.sectors.root:
                idx_exact[(s, sec.symbol)] = {"value": sec.indexValue, "change": sec.change}
                idx_rounded[(s, sec.symbol)] = {"pct": sec.percentage / 100}
            for name in ("ASTRI", "S&P SL20 TRI"):
                df = indices[(indices["index"] == name) & (indices["date"] == s)]
                if not df.empty:
                    r = df.iloc[-1]
                    ch = None if r["change"] != r["change"] else float(r["change"])
                    prev = float(r["value"]) - ch if ch is not None else None
                    idx_exact[(s, name)] = {"value": float(r["value"]), "change": ch,
                                            "pct": (ch / prev) if ch is not None and prev else None}

            # Panel A: market activity, foreign flows, valuation, breadth
            row = {}
            for k in ("turnover", "volume", "trades"):
                st = metrics.market_vs_average(market_df, k)
                row[k], row[f"{k}_avg20"] = st["value"], st["avg"]
                row["sessions_needed"] = st["needed"] or 0
            mrow = market_df[market_df["date"] == s].iloc[-1].to_dict() if (market_df["date"] == s).any() else {}
            row.update(foreign_buy=mrow.get("foreign_buy"), foreign_sell=mrow.get("foreign_sell"),
                       foreign_net=(mrow["foreign_buy"] - mrow["foreign_sell"]) if mrow else None,
                       per=mrow.get("per"), pbv=mrow.get("pbv"), dy=mrow.get("dy"),
                       market_cap=mrow.get("market_cap"), listed=mrow.get("listed"), traded_all=mrow.get("traded"))
            equities = [r for r in sess.trade.reqTradeSummery if r.symbol.endswith((".N0000", ".X0000"))]
            row.update(equities_up=sum(r.change > 0 for r in equities), equities_down=sum(r.change < 0 for r in equities),
                       equities_flat=sum(r.change == 0 for r in equities), equities_traded=len(equities))
            market[(s,)] = row

            # Panel B: every watchlist share
            by_sym = {r.symbol: r for r in sess.trade.reqTradeSummery}
            year_ago = calendar[-min(len(calendar), 240)] if calendar else s
            for sym in dict.fromkeys(x for group in universe.groups.values() for x in group):
                info = sess.infos.get(sym)
                si = info.reqSymbolInfo if info else None
                t = by_sym.get(sym)
                hist = prices[prices["symbol"] == sym].set_index("date").sort_index()
                closes = hist["close"].astype(float) if not hist.empty else metrics.pd.Series(dtype=float)
                volumes = hist["volume"].astype(float) if not hist.empty else metrics.pd.Series(dtype=float)
                price = t.closingPrice if t else (si.lastTradedPrice if si else None)
                if price is None and t is None and si is None:
                    continue
                lo, hi = (si.p12LowPrice, si.p12HiPrice) if si else (None, None)
                vol = metrics.volume_vs_average(volumes, calendar, t.sharevolume if t else 0)
                rel = metrics.relative_returns(closes, aspi, calendar)
                out = {"traded": t is not None, "close": price, "change": t.change if t else None,
                       "low_52w": lo, "high_52w": hi, "range_pos": metrics.range_position(price, lo, hi),
                       "range_flag": metrics.has_jump(closes, year_ago),
                       "vol_ratio": vol.get("value"), "vol_avg20": vol.get("avg"),
                       "market_cap": t.marketCap if t and t.marketCap else (si.marketCap if si else None),
                       "beta": info.reqSymbolBetaInfo.triASIBetaValue if info and info.reqSymbolBetaInfo else None,
                       "turnover": t.turnover if t else None}
                for label in metrics.WINDOWS:
                    out[f"rel_{label}"] = rel[label]["value"]
                    out[f"ret_{label}"] = rel[label].get("stock")
                    out[f"flag_{label}"] = rel[label]["flag"]
                secs[(s, sym)] = out
                sec_pct[(s, sym)] = {"pct": (t.percentageChange / 100) if t else None}

    new_idx = _keyed(new["models.cse_index_session"], ["session_date", "index_code"])
    new_mkt = _keyed(new["models.cse_market_session"], ["session_date"])
    new_sec = _keyed(new["models.cse_security_session"], ["session_date", "symbol"])
    in_old = {k: new_idx[k] for k in idx_exact if k in new_idx}
    in_old_rounded = {k: new_idx[k] for k in idx_rounded if k in new_idx}
    sessions_set = set(sessions)
    checks = [
        compare("cse_market_tape: index level and change", idx_exact, in_old, ["value", "change"]),
        compare("cse_market_tape: TRI percentage change",
                {k: v for k, v in idx_exact.items() if "pct" in v}, {k: in_old[k] for k in idx_exact
                                                                     if "pct" in idx_exact[k] and k in in_old},
                ["pct"]),
        compare("cse_market_tape: index percentage change (CSE-rounded)", idx_rounded, in_old_rounded, ["pct"],
                tol=ROUNDED),
        compare("cse_market_tape: market activity, flows, valuation, breadth", market,
                {k: v for k, v in new_mkt.items() if k[0] in sessions_set},
                ["turnover", "turnover_avg20", "volume", "volume_avg20", "trades", "trades_avg20", "sessions_needed",
                 "foreign_buy", "foreign_sell", "foreign_net", "per", "pbv", "dy", "market_cap", "listed",
                 "traded_all", "equities_up", "equities_down", "equities_flat", "equities_traded"]),
        compare("cse_security_metrics: watchlist shares", secs, {k: new_sec[k] for k in secs if k in new_sec},
                ["traded", "close", "change", "low_52w", "high_52w", "range_pos", "range_flag", "vol_ratio",
                 "vol_avg20", "market_cap", "beta", "turnover", "rel_1w", "rel_1m", "rel_3m", "ret_1w", "ret_1m",
                 "ret_3m", "flag_1w", "flag_1m", "flag_3m"]),
        compare("cse_security_metrics: percentage change (CSE-rounded)", sec_pct,
                {k: new_sec[k] for k in sec_pct if k in new_sec}, ["pct"], tol=ROUNDED),
    ]
    return {"checks": checks, "sessions": sessions, "ok": all(c["ok"] for c in checks), "old_code_compared": True}
