# Draft requests for data permissions (2026-10-18)

Send these from the company's own email address, once the company and its name are settled. Each request is
short and specific: what we would show, to whom, and how we would credit the source. File every reply in the
company's records, and update `config/sources.yaml` when permission arrives.

---

## 1. Colombo Stock Exchange — to the Chief Executive Officer (the most important)

**To:** the CEO, Colombo Stock Exchange (via the CSE's main office; the terms at https://www.cse.lk/disclaimer
direct permission requests to the CEO)
**Subject:** Request for permission to use CSE market data in an investor-information website

Dear Sir/Madam,

We are building ZinvestIQ, a website that helps Sri Lankan retail investors understand the market: daily index
levels, turnover, breadth and each listed company's price history, with plain-language explanations. It offers
information and education only, not investment advice.

The CSE's terms of use ask that commercial use of the data on cse.lk be approved in writing by the CEO. We would
like to:
- show end-of-day prices, indices, market statistics and company announcements from the CSE, credited
  "Source: Colombo Stock Exchange";
- keep a history of those figures and compute simple statistics from them (returns, ranges, averages);
- offer the site free, with some deeper analysis in a paid subscription.

We use end-of-day figures only: no real-time or intraday prices. Could you tell us whether the CSE can grant this
permission, or whether a market-data licence (directly or through an authorised vendor) is the right route? If it is
a licence, could you send the CSE's market-data policy and its fees for end-of-day data used on a website, including
any fee for keeping history and computing statistics from it?

Yours faithfully,
[name], [title], ZinvestIQ — [email], [phone]

---

## 2. Bitstamp — partners@bitstamp.net

**Subject:** Commercial-use Data License Agreement for an analytics website

Hello,

Your API documentation directs companies that want to use Bitstamp exchange data commercially to sign a Data
License Agreement. We are building ZinvestIQ, an information and education website. We would like to:
- use daily (and hourly) OHLC for BTC, ETH and other major pairs, including full history from 2011;
- compute and display statistics from it (moving averages, drawdowns, volatility), credited "Source: Bitstamp".

Could you send the agreement and its fees?

Thank you, [name]

---

## 3. Central Bank of Sri Lanka — Director Communications, cbslgen@cbsl.lk

**Subject:** Reuse of published interest-rate statistics in an investor-education website

Dear Sir/Madam,

We would like to show the CBSL's published interest-rate statistics (tables 4.03 and 4.04, including AWFDR and
treasury bill yields), credited "Source: Central Bank of Sri Lanka". They would appear in an educational
comparison of fixed deposits, treasury bills and other investments, on a website that will have a paid tier.

The CBSL site carries an "All Rights Reserved" notice but no reuse terms. Could you confirm whether this use is
acceptable, and how you would like the data to be credited?

Yours faithfully, [name]

---

## 4. Department of Census and Statistics — information@statistics.gov.lk

**Subject:** Reuse of published CCPI and NCPI figures

Same request as for the CBSL, for the published CCPI and NCPI series, credited "Source: Department of Census and
Statistics, Sri Lanka", to show inflation beside interest rates.

---

## Also pending from earlier

- **PDMO / Ministry of Finance:** permission for the government bond data (`docs/audit.md` §7).
- **Kraken:** permission to use its OHLCVT archive commercially, as an alternative to Bitstamp.
