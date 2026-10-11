# Carry, rolldown and duration (bond_carry)

## What it shows

For each quoted bond on each day, two quantities known at the outset, in basis points per year:

- **carry**: the bond's yield minus a funding rate;
- **rolldown**: the price change from the bond ageing a quarter along an unchanged curve, annualised;

plus the bond's price and modified duration, and carry plus rolldown per year of duration. Carry plus rolldown on
its own rises almost one for one with duration; per unit of duration the bonds become comparable.

## Inputs

The day's curve and quote residuals (`bond_ns_curve`), coupons (`bond_identity`), the execution gap
(`bond_execution_gap`), and executed treasury bill trades from the PDMO trade summary.

## Method (version 1.0.0)

- Entry yield = quoted yield + the day's execution gap (0 when the gap is not reported). The shift is the same for
  every bond, so it moves levels, not the ordering.
- Funding rate = the volume-weighted yield of 12-month treasury bills (240 to 380 days left) printed within the 5
  days to the latest such print in the last 30 days, plus 5 bp.
- Price and modified duration from the entry yield, semi-annual coupons dated backwards from maturity, flat yield,
  no day count.
- Rolldown = duration × (curve yield at τ − curve yield at τ − 0.25) / 0.25, with τ − 0.25 floored at 0.02 years.

## Limits

- The 5 bp spread over the bill is the old tool's personal assumption about one dealer's margin; a reader's own
  funding cost will differ.
- Tax is not modelled. Coupon income and price accretion may be taxed differently.
- The bill rate can be up to 30 days stale; staleness is stored with each day's funding rate.

## Versions

- **1.1.0 (current):** the same method, reading version 2 of the curve (every two-way quote, decision 0014).
  Step-coupon bonds, which now reach the curve, are left out here: a level-coupon formula cannot price them.
- **1.0.0 (reference):** reads version 1 of the curve and reproduces the old tool; kept running beside 1.1.0.

## Parity

Version 1 reproduces the old tool's `carry.funding_rate()` (209 days) and `carry.profile()` (10,975 bond-days) for
every curve day; the largest difference is about 1e-11. Report: `docs/migration/parity-bonds.json`.
