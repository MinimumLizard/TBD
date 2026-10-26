-- 0016 (2026-10-20): money flows with the owner's aliases and ownership groups; the portfolio lab (Phase 3b).
--
-- 1. Money flows (cse_flows 1.0.0, completed in place before its first production run, decision 0015 rule 11):
--    models.cse_flow_dealing.own_group   the account that dealt is in the same ownership group as the company whose
--                                        shares it dealt in (cse_ownership's groups as at the dealing date)
--    models.cse_flow_actor.actor_group   the name of the account's ownership group (the account's own name when it
--                                        heads no group)
--
-- 2. The portfolio lab (audit C4, C8-C11; decision 0023). INTERNAL RESEARCH ONLY: every table below is listed in
--    config/entitlements.yaml `unpublished_outputs`, the website's role cannot read any of them, and no page or API
--    route reads them. The owner reads them through `python -m data_platform.jobs.lab_report`.
--    Inputs (append-only, every version kept, like the owner's other confirmations):
--      cse.sector_overrides        the owner's sector assignments (config/sector_overrides.yaml), per version
--      cse.lab_private_settings    the owner's personal lab settings (the private file LAB_PRIVATE_FILE: the
--                                  conflict-of-interest list and the portfolio size), per version; never in git
--    Outputs:
--      models.cse_weekly_return    cse_risk_estimates: each share's (and the ASPI's) Wednesday-to-Wednesday return
--      models.cse_risk_summary     ... per estimate date: status, window, shrinkage, risk-free rate, premium
--      models.cse_risk_universe    ... per estimate date and security: in the universe or not, and why
--      models.cse_risk_estimate    ... per estimate date and share in the universe: beta, expected return, risk
--      models.cse_lab_summary      cse_portfolio_lab: per estimate date, status and the inputs' fingerprint
--      models.cse_lab_cap          ... per estimate date and share: the per-share cap and the liquidity cap
--      models.cse_lab_portfolio    ... per estimate date and portfolio: expected return, risk, what binds
--      models.cse_lab_weight       ... per estimate date, portfolio and name: the model weight
--      models.cse_lab_exposure     ... per estimate date, portfolio and sector or ownership group: the weight
--      models.cse_lab_frontier     ... per estimate date: the constrained efficient frontier
--      models.cse_lab_nav          cse_lab_record: per session, series and portfolio: value, cash
--      models.cse_lab_holding      ... per session, series, portfolio and name: shares, value, weight
--      models.cse_lab_trade        ... per session, series and portfolio: each change of shares, with its cost

alter table models.cse_flow_dealing add column if not exists own_group boolean not null default false;
alter table models.cse_flow_actor add column if not exists actor_group text;

-- --- inputs ----------------------------------------------------------------------------------------------------

create table cse.sector_overrides (
  version_id    bigserial   primary key,
  file_sha256   text        not null,
  overrides     jsonb       not null,       -- {symbol: one of the 20 S&P/CSE industry groups}
  code_version  text,
  loaded_at     timestamptz not null default now()
);

create table cse.lab_private_settings (
  version_id    bigserial   primary key,
  file_sha256   text        not null,
  settings      jsonb       not null,       -- {"excluded": [symbol, ...], "portfolio_size_lkr": number}
  code_version  text,
  loaded_at     timestamptz not null default now()
);

do $$
declare t text;
begin
  foreach t in array array['sector_overrides', 'lab_private_settings'] loop
    execute format('create trigger %I before update or delete on cse.%I
                    for each row execute function ops.forbid_change()', t || '_append_only', t);
    execute format('alter table cse.%I enable row level security', t);
  end loop;
end $$;

-- --- cse_risk_estimates --------------------------------------------------------------------------------------------

create table models.cse_weekly_return (
  method_version  text             not null,
  series          text             not null,   -- a share's symbol, or ASI (the ASPI, the market proxy)
  week_end        date             not null,   -- a Wednesday: the return runs from the previous Wednesday to this one
  level           double precision not null,   -- the total-return index (the ASPI) on or before week_end
  level_date      date             not null,   -- the session that value is from
  weekly_return   double precision not null,
  run_id          bigint           not null references models.runs,
  primary key (method_version, series, week_end)
);

create table models.cse_risk_summary (
  method_version       text             not null,
  as_of                date             not null,   -- the estimate date (a session)
  status               text             not null check (status in ('ok', 'waiting')),
  message              text             not null,
  preview              boolean          not null,   -- estimates on the longest history available (old lab preview)
  n_securities         integer          not null,
  n_universe           integer          not null,
  history_weeks        integer,                     -- weekly returns per estimate (52; a preview's own number)
  max_weeks_available  integer          not null,
  first_week           date,                        -- the first and last Wednesday of the returns used
  last_week            date,
  shrinkage            double precision,            -- Ledoit-Wolf shrinkage intensity
  risk_free            double precision,            -- annual
  risk_free_source     text,
  risk_free_month      date,                        -- the month of the bill yield used (when from the CBSL)
  equity_risk_premium  double precision,            -- an assumption
  market_proxy         text             not null,
  run_id               bigint           not null references models.runs,
  primary key (method_version, as_of)
);

create table models.cse_risk_universe (
  method_version       text             not null,
  as_of                date             not null,
  symbol               text             not null,
  name                 text,
  included             boolean          not null,
  reason               text,                        -- why it is left out (null when included)
  weeks                integer,                     -- weekly total returns available (ordinary shares only)
  traded_share         double precision,            -- share of the last 52 weeks' sessions it traded on
  median_turnover      double precision,            -- median daily turnover over those sessions (Rs; 0 untraded)
  real_turnover_share  double precision,            -- share of those sessions with the CSE's own turnover figure
  sector               text,
  run_id               bigint           not null references models.runs,
  primary key (method_version, as_of, symbol)
);

create table models.cse_risk_estimate (
  method_version   text             not null,
  as_of            date             not null,
  symbol           text             not null,
  sector           text             not null,
  group_key        text             not null,   -- ownership group (cse_ownership), the share's own when none
  group_name       text,
  beta             double precision not null,   -- Dimson: current + one-week-lagged market slope
  beta_current     double precision not null,
  beta_lag         double precision not null,
  expected_return  double precision not null,   -- CAPM, annual
  volatility       double precision not null,   -- annual, from the covariance's diagonal
  amihud           double precision,            -- mean |weekly return| per Rs mn of weekly turnover
  median_turnover  double precision not null,
  turnover_source  text             not null,   -- real | estimated | mixed
  run_id           bigint           not null references models.runs,
  primary key (method_version, as_of, symbol)
);

-- --- cse_portfolio_lab ---------------------------------------------------------------------------------------------

create table models.cse_lab_summary (
  method_version  text             not null,
  as_of           date             not null,
  status          text             not null check (status in ('ok', 'waiting', 'infeasible')),
  message         text             not null,
  preview         boolean          not null,
  n_universe      integer          not null,
  notional_lkr    double precision,            -- the portfolio size the liquidity caps are computed for
  inputs_sha256   text             not null,   -- the date's inputs, parameters and code: a date is recomputed when
                                               -- this changes, and its stored rows are reused when it does not
  run_id          bigint           not null references models.runs,
  primary key (method_version, as_of)
);

create table models.cse_lab_cap (
  method_version  text             not null,
  as_of           date             not null,
  symbol          text             not null,
  cap             double precision not null,   -- min(per-share maximum, liquidity cap)
  liquidity_cap   double precision not null,
  run_id          bigint           not null references models.runs,
  primary key (method_version, as_of, symbol)
);

create table models.cse_lab_portfolio (
  method_version   text             not null,
  as_of            date             not null,
  portfolio        text             not null,   -- min_variance | risk_parity | max_sharpe | equal_weight | market |
                                                -- <kind>_<K> (the versions with K names)
  family           text             not null check (family in ('full', 'fewer_names', 'market')),
  names_target     integer,                     -- K, for the versions with fewer names
  status           text             not null check (status in ('ok', 'infeasible', 'not_formed')),
  message          text,
  formed_on        date,                        -- the date the weights were set (fewer names: the last rebalance
                                                -- date; full portfolios: as_of)
  n_names          integer,
  expected_return  double precision,
  volatility       double precision,
  sharpe           double precision,
  tracking_error   double precision,            -- against the full portfolio of the same kind, as at as_of
  weight_sum       double precision,
  min_weight       double precision,
  max_over_cap     double precision,
  max_sector_over  double precision,
  max_group_over   double precision,
  constraints_ok   boolean,
  binding          text,                        -- the constraints that hold with equality, in words
  run_id           bigint           not null references models.runs,
  primary key (method_version, as_of, portfolio)
);

create table models.cse_lab_weight (
  method_version     text             not null,
  as_of              date             not null,
  portfolio          text             not null,
  symbol             text             not null,
  weight             double precision not null,
  risk_contribution  double precision,         -- share of the portfolio's variance (sums to 1)
  cap                double precision,
  sector             text,
  group_key          text,
  expected_return    double precision,
  at_cap             boolean          not null,
  run_id             bigint           not null references models.runs,
  primary key (method_version, as_of, portfolio, symbol)
);

create table models.cse_lab_exposure (
  method_version  text             not null,
  as_of           date             not null,
  portfolio       text             not null,
  kind            text             not null check (kind in ('sector', 'group')),
  name            text             not null,   -- the sector, or the ownership group's key
  label           text,                        -- the group's name
  weight          double precision not null,
  at_cap          boolean          not null,
  run_id          bigint           not null references models.runs,
  primary key (method_version, as_of, portfolio, kind, name)
);

create table models.cse_lab_frontier (
  method_version   text             not null,
  as_of            date             not null,
  point            integer          not null,
  expected_return  double precision not null,
  volatility       double precision not null,
  run_id           bigint           not null references models.runs,
  primary key (method_version, as_of, point)
);

-- --- cse_lab_record --------------------------------------------------------------------------------------------

create table models.cse_lab_nav (
  method_version  text             not null,
  series          text             not null,
  session_date    date             not null,
  portfolio       text             not null,
  nav             double precision not null,
  cash            double precision not null,
  holdings_value  double precision not null,
  note            text             not null,
  run_id          bigint           not null references models.runs,
  primary key (method_version, series, session_date, portfolio)
);

create table models.cse_lab_holding (
  method_version  text             not null,
  series          text             not null,
  session_date    date             not null,
  portfolio       text             not null,
  symbol          text             not null,
  shares          double precision not null,
  price           double precision,
  value           double precision not null,
  weight          double precision not null,
  target_weight   double precision,            -- the model weight
  outside_band    boolean          not null,   -- |weight - model weight| beyond the drift band
  run_id          bigint           not null references models.runs,
  primary key (method_version, series, session_date, portfolio, symbol)
);

create table models.cse_lab_trade (
  method_version  text             not null,
  series          text             not null,
  session_date    date             not null,
  portfolio       text             not null,
  seq             integer          not null,   -- order within the session and portfolio
  symbol          text             not null,
  action          text             not null check (action in ('increase', 'decrease', 'dividend', 'subdivision',
                                                                'scrip', 'rights')),
  shares          double precision not null,
  price           double precision,
  value           double precision not null,
  cost            double precision not null,
  reason          text             not null,
  run_id          bigint           not null references models.runs,
  primary key (method_version, series, session_date, portfolio, seq)
);

-- Row-level security on every new table, with the models schema's usual read policy (as migration 0014 did for its
-- unpublished tables), and the website's role revoked explicitly: migration 0006 grants it every new models table by
-- default, so without this revoke it could read them. With it, the role cannot read them at all.
do $$
declare t text;
begin
  foreach t in array array['cse_weekly_return', 'cse_risk_summary', 'cse_risk_universe', 'cse_risk_estimate',
                           'cse_lab_summary', 'cse_lab_cap', 'cse_lab_portfolio', 'cse_lab_weight', 'cse_lab_exposure',
                           'cse_lab_frontier', 'cse_lab_nav', 'cse_lab_holding', 'cse_lab_trade'] loop
    execute format('alter table models.%I enable row level security', t);
    execute format('create policy web_read on models.%I for select to web_reader using (true)', t);
    execute format('revoke all on models.%I from web_reader', t);
  end loop;
end $$;
