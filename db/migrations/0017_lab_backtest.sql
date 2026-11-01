-- The portfolio lab's walk-forward test (model cse_lab_backtest; decision 0024): what the lab's rules would have built
-- and held on each past date, with only what was known then, under two rebalancing policies. INTERNAL RESEARCH, like
-- the rest of the lab (decision 0023): unpublished (config/entitlements.yaml) and revoked from the website's role below.

create table models.cse_bt_summary (
  method_version  text             not null,
  policy          text             not null check (policy in ('quarterly', 'dynamic')),
  portfolio       text             not null,   -- min_variance_10 ... equal_weight_15, market (the ASPI), bills
  start_date      date             not null,
  end_date        date             not null,
  end_value       double precision not null,  -- from the notional at the start
  total_return    double precision,
  volatility      double precision,           -- annualised, from daily values
  max_drawdown    double precision,
  best_month      double precision,
  worst_month     double precision,
  n_rebalances    integer,                    -- inception, scheduled and threshold rebalances
  n_drift         integer,                    -- sessions with drift-band trades
  turnover        double precision,           -- value traded (increases and decreases) / the average value
  costs           double precision,           -- in rupees
  n_names_end     integer,
  run_id          bigint           not null references models.runs,
  primary key (method_version, policy, portfolio)
);

create table models.cse_bt_nav (
  method_version  text             not null,
  session_date    date             not null,
  policy          text             not null,
  portfolio       text             not null,
  nav             double precision not null,
  cash            double precision not null,
  n_names         integer,
  run_id          bigint           not null references models.runs,
  primary key (method_version, session_date, policy, portfolio)
);

create table models.cse_bt_event (
  method_version   text             not null,
  session_date     date             not null,
  policy           text             not null,
  portfolio        text             not null,
  kind             text             not null check (kind in ('inception', 'scheduled', 'threshold', 'drift')),
  tracking_error   double precision,          -- holdings against the rules' new portfolio, before rebalancing
  left_universe    boolean          not null,
  names_in         text             not null,  -- comma-separated symbols
  names_out        text             not null,
  drift_names      text             not null,
  estimate_weeks   integer,                   -- the weekly returns the date's estimates used
  preview          boolean,                   -- estimates on less than a year of weekly returns
  binding          text,
  model_volatility double precision,
  universe_volatility_median double precision,  -- of every share the rules considered on the date
  turnover         double precision           not null,
  cost             double precision           not null,
  nav              double precision           not null,
  run_id           bigint           not null references models.runs,
  primary key (method_version, session_date, policy, portfolio, kind)
);

create table models.cse_bt_target (
  method_version    text             not null,
  as_of             date             not null,
  policy            text             not null,
  portfolio         text             not null,
  symbol            text             not null,
  applied           boolean          not null,  -- the holdings were rebalanced to these weights on the date
  today             boolean          not null,  -- the rules' portfolio on the latest session (shown, not applied)
  weight            double precision not null,
  risk_contribution double precision,
  volatility        double precision,
  beta              double precision,
  avg_correlation   double precision,          -- with the other names of the portfolio
  sector            text,
  group_key         text,
  group_name        text,
  at_cap            boolean          not null,
  at_floor          boolean          not null,
  rank              integer,                   -- its place in the full portfolio of the same kind
  in_previous       boolean          not null,
  run_id            bigint           not null references models.runs,
  primary key (method_version, as_of, policy, portfolio, symbol, today)
);

create table models.cse_bt_trade (
  method_version  text             not null,
  session_date    date             not null,
  policy          text             not null,
  portfolio       text             not null,
  seq             integer          not null,
  symbol          text             not null,
  action          text             not null check (action in ('increase', 'decrease', 'dividend', 'subdivision',
                                                                'scrip', 'rights')),
  shares          double precision not null,
  price           double precision,
  value           double precision not null,
  cost            double precision not null,
  reason          text             not null,
  run_id          bigint           not null references models.runs,
  primary key (method_version, session_date, policy, portfolio, seq)
);

-- Row-level security on every new table, and the website's role revoked (as migration 0016 did for the lab).
do $$
declare t text;
begin
  foreach t in array array['cse_bt_summary', 'cse_bt_nav', 'cse_bt_event', 'cse_bt_target', 'cse_bt_trade'] loop
    execute format('alter table models.%I enable row level security', t);
    execute format('create policy web_read on models.%I for select to web_reader using (true)', t);
    execute format('revoke all on models.%I from web_reader', t);
  end loop;
end $$;
