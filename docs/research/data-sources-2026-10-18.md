# Data sources for crypto, the FD comparison, and the CSE's own terms (2026-10-18)

Research for the owner's requests of 2026-10-18. Every status is recorded with its evidence in
`config/sources.yaml`. This is not legal advice; every "silent" or "with agreement" source needs written
confirmation before paid use (decision 0009).

## The most important finding: the CSE's terms need its written permission

The CSE publishes its terms at https://www.cse.lk/disclaimer, linked from the site footer as "Terms & Conditions".
The 2026-10-11 search missed this page; it looked for /terms-of-use, which does not exist.

What the terms say:
- use is "for personal and non-commercial use";
- no part may be copied, stored, republished, adapted or exploited "for any commercial purpose and/or for profit"
  without the prior written permission of the CSE;
- requests go to the CSE's Chief Executive Officer;
- they also prohibit caching and framing.

So the CSE source is now **`permission_required`**:
- the collector may run for development and the owners' private preview;
- `sources.launch_blockers()` lists it, and the switch-on checklist stops on it until the permission or a
  market-data licence is on file.

This affects half of the product, so the enquiry to the CSE's CEO is now the first business action
(`docs/roadmap.md`).

## Crypto price and on-chain data

No free source clearly allows commercial use of deep price history. These are the usable routes:

| Source | Status | What it gives |
|---|---|---|
| **Bitstamp**, under its Data License Agreement | Commercial use and redistribution allowed once signed; fee not published | BTC/USD daily and hourly from 2011-09-14 (measured), plus ETH and other majors |
| **CoinMarketCap Startup** (USD 79/month) | Explicit commercial licence for one product (up to 100k users) | All-time daily history across coins; market caps |
| **Running our own Bitcoin node** | Allowed (MIT software, public chain) | On-chain metrics (supply, hash rate, realized cap, MVRV). Needs about 2 TB of SSD and a small server, so deferred |
| alternative.me Fear & Greed | Allowed, with attribution beside the data | Sentiment index |

Prohibited or paid-only for us:
- **Exchanges:** Kraken, Gemini, OKX, Bybit, KuCoin, Crypto.com, Deribit, Coinbase, Binance.
- **Aggregators:** CoinGecko (free plan), CoinDesk/CryptoCompare (free tier retired May 2026), Messari, Kaiko,
  CoinPaprika (redistribution only on Enterprise), CoinCap.
- **On-chain providers:** Glassnode, CryptoQuant, Blockchain.com, Blockchair, Coin Metrics (CC BY-NC).
- **General finance sites:** Yahoo Finance.
- **Unclear:** mempool.space's hosted API says nothing on commercial use; ask before relying on it.

**Sri Lanka's position on crypto** (for framing):
- CBSL (2021): virtual currencies are not legal tender, and no entity is licensed to deal in them.
- CBSL (2023): crypto is "not recognized as an asset-class". It "urges those who are engaged in promoting and
  facilitating the promotion of investing and trading in cryptocurrency to refrain from such activities".
- The Cabinet approved a virtual-asset framework under the SEC on 2026-07-27; no law has passed yet.

So crypto pages are to be framed as global market information and education, in USD:
- no exchange links, no "how to get crypto" content;
- a risk notice citing CBSL;
- a lawyer's view on the 2023 "promoting" wording before anything is published.

## The FD comparison: rates, inflation, taxes and costs

**Data**

| Item | Source | Range | Status |
|---|---|---|---|
| AWFDR, AWDR, policy rates, 3- and 12-month bill yields | CBSL table 4.04 (monthly xlsx) | Jan 2003 – Aug 2026 | silent ("All Rights Reserved" footer, no terms) |
| The same, annual | CBSL table 4.03 | 1990 – 2025 | silent |
| 91/182/364-day auction yields, weekly | CBSL auction file | 1996 – Nov 2025 (stale since) | silent; current yields from our own PDMO data |
| ASPI, total return index, S&P SL20, daily | CBSL Economic Data Library | 2012 – Dec 2024 (stale) | the figures originate at the CSE, so the CSE's terms apply |
| CCPI, NCPI | Department of Census and Statistics (PDF) | CCPI back to 1953 across bases | silent |

**Taxes and costs** (Inland Revenue, reuse allowed with acknowledgement)

| Item | Fact |
|---|---|
| Tax deducted from FD interest | 10% from 2025-04-01 (5% from 2023 to March 2025). Not final: credited against income tax; a self-declaration avoids it |
| Dividends | 15% final withholding |
| Gains on CSE-listed shares | Not taxed |
| Treasury bill and bond interest | Nothing deducted at source; taxed at the person's normal rate |
| CSE trading costs, per side (from 2025-07-28) | 1.12% up to Rs 100 mn: brokerage 0.64%, CSE 0.084%, CDS 0.012%, clearing 0.012%, SEC 0.072%, transaction levy 0.30%. This confirms the old tool's figure |
| Deposit insurance (SLDIS) | Rs 1,100,000 per depositor, per institution |

**What this means**
- An honest FD-versus-bills comparison can be built from CBSL's monthly table (2003 to date). It still needs a
  written confirmation from CBSL for paid use.
- FD versus the share market needs long index history, and every channel for it leads back to the CSE. That
  depends on the CSE permission too.
