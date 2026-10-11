# 0009 — A source is used only if its terms allow commercial use or are silent

- **Date:** 2026-10-11
- **Status:** Accepted (owner rule, decision 0001)

## Rule

Every source has an entry in `config/sources.yaml`:

```yaml
cse_api:
  enabled: true
  rights:
    status: silent            # allowed | silent | prohibited
    evidence: "No published terms for cse.lk/api or cdn.cse.lk found (searched 2026-10-11)."
    url: https://www.cse.lk/
    checked: 2026-10-11
    attribution: "Source: Colombo Stock Exchange"
```

A collector whose source is `prohibited` refuses to run, and CI fails if one is enabled. Attribution text required by
a source is shown on every page that uses it. Status is re-checked every six months, a reminder the gap check also
emails.

## Status of today's sources (from audit §7)

| Source | Status | Use in product |
|---|---|---|
| CSE API and announcement PDFs | silent | **Yes** (launch). Risk noted: the CSE licenses data to vendors; an enquiry is still recommended. |
| PDMO / treasury.gov.lk | silent | **Yes** (launch). Enquiry recommended (official feed, archive). |
| alternative.me Fear & Greed | allowed (with attribution next to the data) | When crypto returns |
| GDELT | allowed (citation) | When crypto returns |
| FRED | allowed with notice, **except** series marked third-party copyright | When crypto returns, series by series |
| Hyperliquid, Deribit, GPR, EPU, Polymarket, Kalshi | silent | Possible, when crypto returns |
| CoinGecko | allowed **on paid plans** (Basic $35, Analyst $129 /month) | Paid plan required |
| CoinMetrics community | **prohibited** (CC BY-NC 4.0) | No |
| Coinbase Exchange market data | **prohibited** (personal/research only) | No |
| DefiLlama | **prohibited** without written permission | No (unless permission is obtained) |
| Binance Vision | **prohibited** (dataset terms titled "Non-Commercial") | No |

## Consequences

- The CSE and bond products are unaffected.
- The crypto product, as currently designed, loses its price history (Binance, Coinbase, CoinMetrics), protocol
  fundamentals (DefiLlama) and on-chain metrics. It is deferred until rebuilt on licensed or permitted sources.
- "Silent" is accepted risk, not permission. If a source later objects, it is switched off within one deploy and
  its history is retained internally, pending legal advice.
