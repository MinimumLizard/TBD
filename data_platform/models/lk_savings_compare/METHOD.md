# Fixed deposits, treasury bills and inflation (lk_savings_compare)

## What it shows

What Rs 100,000 would have grown to in two ways of saving in rupees, for every start month since January 2003 and
for periods of one to ten years:

- a **12-month fixed deposit**, renewed every year at the average rate for new deposits that month;
- **12-month treasury bills**, rolled into a new bill every year at that month's primary market yield.

Each is shown before tax, after the tax deducted from deposit interest, and in **real terms**: after inflation, in
the rupees of the start month. Across all start months it counts how often each came out ahead of the other, how
often each kept ahead of inflation, and the best, median and worst outcomes.

It describes the past. It is not a forecast, and it says nothing about what any person should do with their savings.

## Inputs

- **Central Bank of Sri Lanka, table 4.04 "Interest Rates - Monthly"** (2003 to date), as published
  (`rates.cbsl_monthly_current`). Source: Central Bank of Sri Lanka.
- **Department of Census and Statistics, "Movements of the CCPI"**, the Colombo Consumer Price Index, base years 2002,
  2006/07, 2013 and 2021 (`rates.cpi_monthly_current`). Source: Department of Census and Statistics, Sri Lanka.

## Method (version 1.0.0)

**The deposit rate.** For a deposit placed in month *m*, the rate is the CBSL's **AWNFDR** (average weighted new fixed
deposit rate: all new rupee time deposits taken by licensed commercial banks during the month) where it is
published, from April 2014. Before that the CBSL publishes only the **AWFDR** (the average over all *outstanding*
time deposits), which is used instead and flagged on every row that uses it (`fd_series` = AWFDR, or AWFDR+AWNFDR for
a period that spans both). Two cautions:

- both are averages across banks and across all deposit terms, not the rate for a 12-month deposit at any one bank.
  The CBSL also publishes the range of banks' 12-month rates (stored as FD_12M_MIN and FD_12M_MAX); it is wide (for
  August 2026, 2.50% to 12.00%), so an actual deposit may have earned well above or below the average;
- the AWFDR moves more slowly than rates on new deposits, because it includes deposits placed months or years
  earlier. Results that start before April 2014 are therefore smoother than a new depositor would have seen.

**The bill yield.** For a bill bought in month *m*, the 12-month primary market yield in table 4.04 (end of month).
From May 2002 to March 2018 a 10% withholding tax was deducted from treasury bill interest (CBSL, note to the weekly
auction file). Table 4.04 prints the yields of those years **after** that tax. The evidence, measured by joining
table 4.04 with the last 364-day auction of each month in the CBSL's weekly auction file:

- from 2013 to March 2018, table 4.04 is 0.900 of the auction file's "before tax" yield (median of 63 months), and
  for the two weeks in 2015 when the auction file also prints a "without tax" yield, table 4.04 equals it;
- in April 2018, when the tax ended, the auction file's "before tax" yield fell by 8% in a week while table 4.04
  continued without a break;
- from 2003 to 2012 the two tables agree (median ratio 1.000). In the first auction of 2013 the auction file's
  yields for all three tenors rose by 8% to 10% in one week while table 4.04 continued without a break: that is
  when the auction file began adding the tax back.

So the model divides table 4.04's yields for May 2002 to March 2018 by 0.9, and both instruments are compared
**before tax**. This is an inference from the published tables, not a statement by the CBSL, and is to be confirmed
with it. Without the adjustment, the bills' before-tax growth in those years would be understated by about a tenth
of their interest.

**Growth.** Interest is added once a year, at maturity, and reinvested in full:

    value after h years = 100,000 × (1 + r₀)(1 + r₁)…(1 + r_{h−1})

where r_j is the rate (as a fraction) for the deposit or bill placed j years after the start. A bill's 364 days are
treated as one year (the difference is under 0.03 percentage points a year at a 10% yield).

**Tax.** Since 1 January 2023 an advance income tax is deducted from deposit interest: 5%, and 10% from 1 April 2025
(Inland Revenue). The rate applied is the one in force in the month the interest is paid, when the deposit matures.
It is not a final tax: it counts towards the person's income tax, and a person whose income is below the tax-free
allowance can avoid it with a self-declaration. Earlier withholding rules on deposit interest are not modelled, so
before 2023 the after-tax and before-tax figures are the same. Treasury bill interest has had nothing deducted since
April 2018 and is taxed at each person's own income tax rate, so no after-tax figure is computed for bills.

**Inflation.** Real value = nominal value × CCPI(start month) / CCPI(end month). The DCS publishes the CCPI on four
base years since 2003, each covering a different span. They are linked into one series: each month uses the newest
base that covers it, and each newer base is joined at its **first month**, scaled so the series is continuous there
(older index ÷ newer index in that month). Each base's own month-to-month changes are kept exactly. The series is
expressed on the oldest base (2002), so a future base year changes nothing already published. The links:

| Newer base | Joined at | Factor |
|---|---|---|
| 2006/07 | January 2008 | 1.5459 (183.5 ÷ 118.7) |
| 2013 | January 2014 | 1.7035 (177.5 ÷ 104.2) |
| 2021 | January 2022 | 1.2743 (158.4 ÷ 124.3) |

(Measured with `psql "$DATABASE_URL" -f data_platform/models/lk_savings_compare/checks.sql`, which also measures the
overlap figures below and the bill-yield ratios above.)
The choice matters where the bases disagree. Over January 2022 to January 2023, when both the 2013 and 2021 bases
were published, the 2013 base rose 54.2% and the 2021 base 51.7%. Joining at January 2022 uses the 2021 base for
the whole of that year.

**Which months.** A result for a start month and period exists only when every rate it needs and the CCPI for both
its start and end month are published. The latest end month is the last month for which the deposit rate, the bill
yield and the CCPI are all published.

**The summary.** For periods of 1, 3, 5 and 10 years, over every start month: the number of periods; in how many the
instrument ended above the other (before tax only, nominal and real give the same count); in how many it ended
above Rs 100,000 (in real terms: kept ahead of inflation); and the best, median and worst outcome, with the start
month of the best and worst. Periods that start a month apart overlap almost entirely, so they are not independent
observations: 164 ten-year periods contain about 24 years of history, not 164 separate decades.

## What it leaves out

- **The share market.** A comparison with shares needs long index history (ASPI, S&P SL20, total return), and every
  source of it leads back to the Colombo Stock Exchange, whose terms require its written permission. It is added
  only once that permission is given.
- **Deposit insurance and the risk of default.** Deposits at licensed commercial banks, licensed specialised banks
  and licensed finance companies are insured by the Sri Lanka Deposit Insurance Scheme up to Rs 1,100,000 per
  depositor at each institution (CBSL); above that, a deposit depends on the institution. Treasury bills are
  obligations of the Government of Sri Lanka, whose debt carries its own risk: the government suspended payments
  on its external debt in 2022 and restructured part of its domestic debt in 2023. Neither risk is modelled.
- **Costs and early withdrawal.** No fees, penalties or bid-offer spreads; every deposit and bill runs to maturity.
- **Personal circumstances.** One rate per month for everyone: actual rates differ by bank, amount, term and
  customer, and tax depends on each person's income.

## Point in time

A row for a start month and period uses only rates and prices dated on or before its end month, so it does not change
when later months are published. It changes only if the CBSL or DCS revise a figure it used; the change is then
recorded in `models.revisions`. The summary is recomputed each month as new periods complete. A test checks both.

## Outputs

- `models.savings_rates`: per month, the deposit rate used and which series it is, the bill yield as published and
  before tax, the linked CCPI and its base, inflation over the previous 12 months, and the advance income tax rate.
- `models.savings_growth`: per start month, period (1 to 10 years), instrument and basis (nominal,
  nominal_after_tax, real, real_after_tax): the end month, the value of Rs 100,000 and the equivalent annual rate.
- `models.savings_summary`: per period (1, 3, 5, 10 years), instrument and basis: the counts and the range above.
