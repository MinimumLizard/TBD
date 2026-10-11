-- 0004: layer 4, model outputs (docs/architecture.md §7, decision 0015).
--
-- Models are recomputed from the facts, so their tables are NOT append-only like the fact tables. They are made
-- auditable instead:
--   * every row carries the method_version that produced it, and versions never mix: version 2 of a model is a
--     separate series beside version 1, and version 1 stays;
--   * every row carries the run that first wrote its current value (models.runs: code version, inputs fingerprint);
--   * a value that changes on a later run (because a late or amended source file changed the inputs) is not
--     silently overwritten: the old row is copied to models.revisions first, which is itself append-only. So
--     "what did the site show for this day, and when did it change?" always has an answer.

create schema if not exists models;

-- One row per model run. Updated once, to close it.
create table models.runs (
  run_id          bigserial   primary key,
  model           text        not null,
  method_version  text        not null,
  code_version    text        not null,
  as_of           date,
  inputs_sha256   text,                    -- fingerprint of every input row the model read
  started_at      timestamptz not null default now(),
  finished_at     timestamptz,
  status          text        not null default 'running'
                  check (status in ('running', 'ok', 'failed')),
  rows_inserted   integer,
  rows_updated    integer,
  rows_deleted    integer,
  rows_unchanged  integer,
  message         text
);
create index on models.runs (model, method_version, started_at);

-- The validated manifests, published by data_platform.models.registry so the database, the API and the site all
-- read the same description of each model.
create table models.registry (
  model           text        not null,
  method_version  text        not null,
  status          text        not null check (status in ('current', 'reference', 'retired')),
  manifest        jsonb       not null,
  manifest_sha256 text        not null,
  published_at    timestamptz not null default now(),
  primary key (model, method_version)
);

-- Old values of model rows that a later run changed or removed. Append-only.
create table models.revisions (
  revision_id     bigserial   primary key,
  run_id          bigint      not null references models.runs,
  table_name      text        not null,
  method_version  text        not null,
  row_key         jsonb       not null,
  old_row         jsonb       not null,
  new_row         jsonb,                   -- null: the row was removed
  revised_at      timestamptz not null default now()
);
create index on models.revisions (table_name, method_version);
create trigger revisions_append_only before update or delete on models.revisions
  for each row execute function ops.forbid_change();

-- Small named figures a model measures from its own outputs (e.g. how far pair spreads moved back after a large
-- z-score). Measured on every run, never typed in.
create table models.model_stats (
  model           text             not null,
  method_version  text             not null,
  stat_key        text             not null,
  value           double precision not null,
  n               integer,
  run_id          bigint           not null references models.runs,
  primary key (model, method_version, stat_key)
);

-- ===== LKR government bonds ===================================================================================

-- bond_identity: one row per bond (an ISIN, or a synthetic key for a bond no PDMO release names with an ISIN).
create table models.bond_reference (
  method_version  text             not null,
  isin            text             not null,   -- real ISIN, or 'SYN:<maturity>:<coupon>' (never collides: no LK)
  coupon_pct      double precision,
  maturity_date   date,
  tenor_years     integer,
  series_label    text,
  issue_date      date,
  coupon_dates    text,
  first_seen_date date,
  notes           text,                        -- printed step-coupon label, where there is one
  run_id          bigint           not null references models.runs,
  primary key (method_version, isin)
);

-- bond_identity: each day's dealer quotes, resolved to a bond.
create table models.bond_quotes (
  method_version  text             not null,
  obs_date        date             not null,
  isin            text             not null,
  bid_yield       double precision,            -- percent per annum
  offer_yield     double precision,
  mid_yield       double precision,
  bid_price       double precision,
  offer_price     double precision,
  resolved_by     text             not null,   -- label | label-no-letter | maturity+coupon | synthetic | ...
  raw_sha256      text             not null,   -- the archived file the quote came from
  run_id          bigint           not null references models.runs,
  primary key (method_version, obs_date, isin)
);

-- bond_ns_curve: one fitted Nelson-Siegel curve per day.
create table models.bond_curve_fit (
  method_version  text             not null,
  obs_date        date             not null,
  beta0           double precision not null,
  beta1           double precision not null,
  beta2           double precision not null,
  lambda_years    double precision not null,
  n_quotes        integer          not null,
  rmse_bp         double precision not null,
  n_trades        integer          not null,
  trade_rmse_bp   double precision,
  trade_bias_bp   double precision,           -- median of (traded yield - curve), bp
  run_id          bigint           not null references models.runs,
  primary key (method_version, obs_date)
);

-- bond_ns_curve: each bond's distance from that day's curve. residual_bp = observed - fitted (positive: the bond
-- yields more than the curve).
create table models.bond_curve_point (
  method_version  text             not null,
  obs_date        date             not null,
  isin            text             not null,
  source          text             not null check (source in ('quote', 'trade')),
  tau_years       double precision not null,
  observed_yield  double precision not null,
  fitted_yield    double precision not null,
  residual_bp     double precision not null,
  weight          double precision,           -- quotes only: relative weight in the fit (average 1)
  run_id          bigint           not null references models.runs,
  primary key (method_version, obs_date, isin, source)
);

-- bond_rv_zscores: each bond's residual against its own trailing window (the window excludes the day scored).
create table models.bond_residual_zscore (
  method_version  text             not null,
  obs_date        date             not null,
  isin            text             not null,
  residual_bp     double precision not null,
  mean_bp         double precision not null,
  sd_bp           double precision not null,
  deviation_bp    double precision not null,  -- residual - its own trailing mean
  zscore          double precision not null,
  n_window        integer          not null,
  run_id          bigint           not null references models.runs,
  primary key (method_version, obs_date, isin)
);

-- bond_rv_zscores: the residual spread between two bonds (a minus b), against its own trailing window.
create table models.bond_pair_zscore (
  method_version  text             not null,
  obs_date        date             not null,
  isin_a          text             not null,
  isin_b          text             not null,
  tau_a           double precision not null,
  tau_b           double precision not null,
  spread_bp       double precision not null,
  mean_bp         double precision not null,
  sd_bp           double precision not null,
  deviation_bp    double precision not null,
  zscore          double precision not null,
  n_window        integer          not null,
  run_id          bigint           not null references models.runs,
  primary key (method_version, obs_date, isin_a, isin_b)
);

-- bond_liquidity: how much each bond has traded, and where it is in the auction cycle, as of each day.
create table models.bond_liquidity (
  method_version      text             not null,
  obs_date            date             not null,
  isin                text             not null,
  turnover_lkr        bigint           not null,
  n_trades            integer          not null,
  days_traded         integer          not null,
  is_benchmark        boolean          not null,   -- auctioned in the last 120 days
  last_auction        date,
  days_since_auction  integer,
  post_auction        boolean          not null,
  bid_to_cover        double precision,
  tier                text             not null check (tier in ('core', 'active', 'wider')),
  last_trade_date     date,
  last_trade_yield    double precision,
  days_since_trade    integer,
  trades_through      date             not null,   -- last day whose trade file had been published
  trade_data_lag_days integer          not null,
  run_id              bigint           not null references models.runs,
  primary key (method_version, obs_date, isin)
);

-- bond_execution_gap: where trades printed relative to the quoted mid, over a trailing window.
create table models.bond_execution_gap (
  method_version  text             not null,
  obs_date        date             not null,
  gap_bp          double precision not null,
  n               integer          not null,
  window_days     integer          not null,
  run_id          bigint           not null references models.runs,
  primary key (method_version, obs_date)
);

-- bond_carry: the funding rate used each day.
create table models.bond_funding (
  method_version  text             not null,
  obs_date        date             not null,
  bill_pct        double precision not null,
  rate_pct        double precision not null,
  spread_bp       double precision not null,
  bill_as_of      date             not null,
  stale_days      integer          not null,
  n_bills         integer          not null,
  window_days     integer          not null,
  run_id          bigint           not null references models.runs,
  primary key (method_version, obs_date)
);

-- bond_carry: carry, rolldown and duration per bond per day.
create table models.bond_carry (
  method_version  text             not null,
  obs_date        date             not null,
  isin            text             not null,
  entry_gap_bp    double precision not null,
  entry_yield     double precision not null,
  price           double precision not null,
  duration        double precision not null,
  carry_bp        double precision not null,
  roll_bp         double precision not null,
  total_bp        double precision not null,
  per_duration_bp double precision not null,
  run_id          bigint           not null references models.runs,
  primary key (method_version, obs_date, isin)
);

-- ===== Colombo Stock Exchange =================================================================================

-- cse_market_tape: one row per session.
create table models.cse_market_session (
  method_version   text             not null,
  session_date     date             not null,
  turnover         double precision,
  turnover_avg20   double precision,
  volume           double precision,
  volume_avg20     double precision,
  trades           double precision,
  trades_avg20     double precision,
  sessions_needed  integer,                    -- daily sessions still needed before the 20-session average exists
  foreign_buy      double precision,
  foreign_sell     double precision,
  foreign_net      double precision,
  per              double precision,
  pbv              double precision,
  dy               double precision,
  market_cap       double precision,
  listed           integer,
  traded_all       integer,
  equities_up      integer          not null,
  equities_down    integer          not null,
  equities_flat    integer          not null,
  equities_traded  integer          not null,
  run_id           bigint           not null references models.runs,
  primary key (method_version, session_date)
);

-- cse_market_tape: every index (headline, total return and sector) per session.
create table models.cse_index_session (
  method_version  text             not null,
  session_date    date             not null,
  index_code      text             not null,
  value           double precision not null,
  change          double precision,
  pct             double precision,            -- change / previous value (a fraction)
  run_id          bigint           not null references models.runs,
  primary key (method_version, session_date, index_code)
);

-- cse_security_metrics: one row per security per session it has a price for, or per session in the calendar.
create table models.cse_security_session (
  method_version  text             not null,
  session_date    date             not null,
  symbol          text             not null,
  traded          boolean          not null,   -- traded in this session (otherwise: last close carried)
  close           double precision,
  change          double precision,
  pct             double precision,
  turnover        double precision,
  volume          double precision,
  market_cap      double precision,
  low_52w         double precision,
  high_52w        double precision,
  range_pos       double precision,            -- (close - low) / (high - low)
  range_flag      boolean          not null,   -- a one-day move over 40% in the last ~year (likely unadjusted)
  vol_ratio       double precision,            -- volume / mean of the previous 20 sessions
  vol_avg20       double precision,
  rel_1w          double precision,            -- price return minus ASPI return over 5 sessions
  rel_1m          double precision,            -- ... 21 sessions
  rel_3m          double precision,            -- ... 63 sessions
  ret_1w          double precision,
  ret_1m          double precision,
  ret_3m          double precision,
  flag_1w         text,
  flag_1m         text,
  flag_3m         text,
  beta            double precision,
  run_id          bigint           not null references models.runs,
  primary key (method_version, session_date, symbol)
);
create index on models.cse_security_session (method_version, symbol, session_date);
