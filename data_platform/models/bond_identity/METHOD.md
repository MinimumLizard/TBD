# Government bond list and daily quotes (bond_identity)

## What it shows

The PDMO's daily summary lists the dealers' average bid and offer for each treasury bond, but names each bond only
by a series label such as `10.00%2030A`, never by its ISIN. This model ties each quoted row to a bond, so that a
bond's quotes, trades, volumes and auction results can be followed over time under one identifier.

## Inputs

- Daily summaries (dealer quotes), volume files, trade summaries, auction results and auction announcements, as
  published by the PDMO and stored unchanged (`bonds.*` tables).
- Version 1 only: the old tool's own bond list (`bonds.legacy_reference`), taken from its database at commit
  1c33084.

## Method (version 1.0.0)

Files are read in this order: auction announcements, auction results, volume files, trade summaries, then daily
summaries; within each kind, oldest posted first, so an amended report replaces its original. The first four
teach the model each bond's ISIN, maturity, coupon and series label. Each quote row is then matched:

1. by its series label, where an auction document printed that label beside an ISIN;
2. by the label without its series letter, if that names exactly one bond (the letter is printed inconsistently);
3. by maturity date, if exactly one bond matures that day with a coupon within 0.005 of the quoted one;
4. otherwise, if it is a single-coupon bond with a two-way quote between 0 and 50 bp wide, under a key built from
   its own cash flows: `SYN:<maturity>:<coupon>`. Such a key can split one bond into two, but never merges two.

Rows that match none of these are left out. In practice these are the 2023 restructuring bonds (step coupons,
posted at 13.00/12.00 every day, 100 bp wide) and one-way quotes.

## Method (version 2.0.0, current; decision 0014)

The same order and the same matching, with two changes:

- **No quote is left out.** A row that matches no released ISIN, including the restructuring bonds and one-way
  quotes, is keyed on its own cash flows: `SYN:<maturity>:<coupon>`, or for a step-coupon bond every rate in turn
  (`SYN:2027-12-15:12.000%9.000`). Version 2 holds about 92 quotes a day against version 1's 52.5.
- **No quote overwrites another.** When two rows resolve to the same bond on the same day, the row identified most
  directly keeps it (exact label, then label without its letter, then maturity and coupon), and the other is keyed
  on its own cash flows. This keeps the 13.00%2029A quote that version 1 loses every day.

One-way quotes are kept with their bid or offer and no mid; the curve cannot fit them (see `bond_ns_curve`).

Version 1 keeps running beside version 2 as the reference series that matches the old tool.

## Limits

- The old tool learned some labels and coupons from earlier versions of its parsers. Those survive only in its
  database, which is why version 1 starts from its bond list.
- A quote for a bond whose coupon is not yet known can be matched by maturity alone. With the old bond list this
  never happens in the history to date.
- Two quote rows that resolve to the same bond on the same day overwrite each other; the last one in the file is
  kept. On every day so far this has lost the 13.00%2029A quote, which the old matcher filed under the 2029B bond
  (Phase 2 finding V1).

## Parity

Version 1 reproduces the old tool's `bonds` table (59 bonds) and every quote in its `observations` table (11,146)
exactly. Measured by `python -m data_platform.migration.parity bonds` (report: `docs/migration/parity-bonds.json`).
