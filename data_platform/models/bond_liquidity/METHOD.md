# Bond trading activity (bond_liquidity)

## What it shows

For each bond, as of each day: its turnover and number of trades over the last 60 days, on how many of those days
it traded, when it was last auctioned, the bid-to-cover ratio at its last competitive auction, and its last
traded yield. Bonds are grouped into three tiers by trading activity:

- **core**: auctioned in the last 120 days (a current benchmark issue) and traded on at least 8 of the last 60
  days;
- **active**: traded on at least 10 of the last 60 days;
- **wider**: quoted, but traded less often than that.

## Inputs

PDMO trade summaries (bonds only), auction results and announcements; the days on which a curve was fitted.

## Method (version 1.0.0)

- Trade files are published a day or more after the quotes, so the 60-day window ends on the last day whose trade
  file had been published, unless that is more than 7 days before the day scored (then the window ends on the day
  itself, so a stopped feed cannot keep a bond looking active).
- A bond auctioned exactly 120 days ago still counts as a benchmark. `post_auction` marks the 14 days after an
  auction.
- Nothing uses information published after the day scored.

## Limits

The thresholds (60, 120, 10, 8, 14 and 7 days) are the old tool's choices, set by inspection of this market's
history, not by a formal test.

## Versions

- **1.1.0 (current):** the same method, reading version 2 of the curve (every two-way quote, decision 0014).
  Bonds that only version 2 fits (the restructuring bonds) appear here too.
- **1.0.0 (reference):** reads version 1 of the curve and reproduces the old tool; kept running beside 1.1.0.

## Parity

Version 1 reproduces the old tool's `liquidity.profile()` for every curve day (9,150 bond-days) exactly. The old
tool computed this for its latest day only, so the comparison runs the old code on the old database. Report:
`docs/migration/parity-bonds.json`.
