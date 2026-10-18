-- 0010 (2026-10-18): the crypto section (decision 0019).
--
-- Facts: Bitstamp's daily candles (open, high, low, close, volume) for a fixed list of pairs, in US dollars (and
-- ETH in bitcoin). Bitstamp's commercial terms need a signed Data License Agreement, which is not signed yet: the
-- source is `permission_required` in config/sources.yaml, so it may run for development and the owners' private
-- preview only, and it is a launch blocker.
--
-- Like every fact table, crypto.ohlc_daily is append-only: the database refuses UPDATE and DELETE. Only complete UTC
-- days are stored, so a stored day never needs to change. A later fetch that disagrees with a stored day is not
-- written over it; the difference goes to ops.value_conflicts for a person to look at (core.db.insert_facts).

create schema if not exists crypto;

create table crypto.ohlc_daily (
  pair         text             not null,     -- Bitstamp's url_symbol, e.g. btcusd, ethbtc
  day          date             not null,     -- the UTC day the candle covers, 00:00 to 24:00 UTC
  open         double precision not null,
  high         double precision not null,
  low          double precision not null,
  close        double precision not null,     -- the last trade price of the UTC day, in the quote currency
  volume       double precision not null,     -- in the base currency (bitcoin for btcusd)
  raw_sha256   text             not null references ops.raw_objects,
  fetch_id     bigint           not null references ops.raw_fetches,
  fetched_at   timestamptz      not null,
  ingested_at  timestamptz      not null default now(),
  primary key (pair, day),
  check (close > 0 and open > 0 and high >= low and low > 0 and volume >= 0)
);

create trigger ohlc_daily_append_only before update or delete on crypto.ohlc_daily
  for each row execute function ops.forbid_change();

-- Second line of defence (as migration 0006): no role but the owner reads the facts, even if granted.
alter table crypto.ohlc_daily enable row level security;

-- ===== Model outputs ==========================================================================================

-- crypto_market: per pair per day, price facts and their history to date.
create table models.crypto_market_daily (
  method_version  text             not null,
  pair            text             not null,
  day             date             not null,
  close           double precision not null,
  ret_1d          double precision,             -- close / close one day earlier - 1
  ret_7d          double precision,
  ret_30d         double precision,
  ret_1y          double precision,             -- 365 days
  ath_close       double precision not null,    -- highest daily close from the start of the data to this day
  ath_day         date             not null,
  drawdown        double precision not null,    -- close / ath_close - 1 (0 on a new high)
  days_since_ath  integer          not null,
  vol_30d         double precision,             -- realised volatility, annualised (365 days), from log returns
  vol_90d         double precision,
  run_id          bigint           not null references models.runs,
  primary key (method_version, pair, day)
);

-- crypto_cycle: moving averages and cycle measures per pair per day.
create table models.crypto_cycle_daily (
  method_version      text             not null,
  pair                text             not null,
  day                 date             not null,
  close               double precision not null,
  sma_50              double precision,
  sma_200             double precision,
  mayer               double precision,         -- close / sma_200
  sma_200w            double precision,         -- 200-week simple average of weekly closes
  sma_200w_chg_4w     double precision,         -- sma_200w / its value 28 days earlier - 1
  sma_20w             double precision,
  ema_21w             double precision,
  dist_20w            double precision,         -- close / sma_20w - 1
  pi_sma_111          double precision,
  pi_sma_350x2        double precision,         -- 2 x the 350-day simple average
  pi_ema_150          double precision,
  pi_sma_471x0745     double precision,         -- 0.745 x the 471-day simple average
  last_halving        date,
  days_since_halving  integer,
  roi_since_halving   double precision,
  ret_mtd             double precision,         -- close / the previous month's last close - 1
  run_id              bigint           not null references models.runs,
  primary key (method_version, pair, day)
);

-- crypto_cycle: the days a line crossed another (each is known on its own day and never changes afterwards).
create table models.crypto_cycle_event (
  method_version  text             not null,
  pair            text             not null,
  day             date             not null,
  kind            text             not null check (kind in ('pi_top_cross', 'pi_bottom_cross')),
  close           double precision not null,
  run_id          bigint           not null references models.runs,
  primary key (method_version, pair, kind, day)
);

-- crypto_cycle: each halving, cycle peak and cycle low as known on each day, and the change since it.
create table models.crypto_cycle_anchor (
  method_version   text             not null,
  pair             text             not null,
  day              date             not null,
  kind             text             not null check (kind in ('halving', 'cycle_peak', 'cycle_low')),
  epoch            integer          not null,  -- 0 before the first halving, k from halving k to halving k + 1
  anchor_day       date             not null,
  anchor_close     double precision not null,
  roi              double precision not null,  -- close on `day` / anchor_close - 1
  days_since       integer          not null,
  change_from_prior double precision,          -- anchor_close / the previous anchor's close - 1, in cycle order
  days_from_prior  integer,
  provisional      boolean          not null,  -- the epoch has not ended, so this peak or low can still move
  run_id           bigint           not null references models.runs,
  primary key (method_version, pair, day, kind, epoch)
);

-- crypto_cycle: completed calendar months.
create table models.crypto_cycle_monthly (
  method_version  text             not null,
  pair            text             not null,
  month           date             not null,  -- the first day of the month
  day             date             not null,  -- the month's last day (its close)
  close           double precision not null,
  ret_month       double precision,          -- close / the previous month's close - 1
  run_id          bigint           not null references models.runs,
  primary key (method_version, pair, month)
);

-- crypto_trend_bands: the two long-run trend fits, re-fitted every day on the data to that day.
create table models.crypto_trend_band (
  method_version  text             not null,
  pair            text             not null,
  day             date             not null,
  fit             text             not null check (fit in ('log_regression', 'power_law')),
  intercept       double precision not null,  -- in the fit's own units (METHOD.md)
  slope           double precision not null,
  n_obs           integer          not null,
  resid_sd        double precision not null,  -- standard deviation of the residuals, in the fit's log units
  close           double precision not null,
  fitted          double precision not null,  -- USD
  lower_1         double precision not null,  -- fitted line moved by -1 and +1 residual standard deviations, USD
  upper_1         double precision not null,
  lower_2         double precision not null,  -- -2 and +2
  upper_2         double precision not null,
  position        double precision not null,  -- (log close - log lower_2) / (log upper_2 - log lower_2); 0..1 inside
  run_id          bigint           not null references models.runs,
  primary key (method_version, pair, day, fit)
);

do $$
declare t text;
begin
  foreach t in array array['crypto_market_daily', 'crypto_cycle_daily', 'crypto_cycle_event', 'crypto_cycle_anchor',
                           'crypto_cycle_monthly', 'crypto_trend_band'] loop
    execute format('alter table models.%I enable row level security', t);
    execute format('create policy web_read on models.%I for select to web_reader using (true)', t);
    execute format('grant select on models.%I to web_reader', t);
  end loop;
end $$;
