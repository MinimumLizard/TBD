-- The lab's risk test (cse_lab_backtest 1.1.0; decision 0025): each covariance estimator's forecast of risk against
-- the risk realised afterwards, week by week, with only what was known on each date. It is the evidence for the
-- estimator the lab uses, and it lengthens by itself as history grows. INTERNAL RESEARCH, like the rest of the lab
-- (decisions 0023, 0024): unpublished (config/entitlements.yaml) and revoked from the website's role below.
create table models.cse_bt_risk_test (
  method_version       text             not null,
  scope                text             not null,   -- full (the whole minimum-variance portfolio) or k15 (15 names)
  estimator            text             not null,   -- identity, oas, constant_corr, single_index, daily;
                                                    -- ref_equal_weight and ref_market are reference rows
  start_date           date             not null,
  end_date             date             not null,
  n_weeks              integer          not null,   -- weekly portfolios formed
  n_days               integer          not null,   -- daily returns that judge them
  realised_volatility  double precision not null,   -- annualised, from daily returns, no costs
  forecast_volatility  double precision,            -- the average of the weekly forecasts
  weekly_turnover      double precision,            -- average one-way change in weights from week to week
  effective_names      double precision,            -- 1 / sum of squared weights, averaged
  variance_ratio       double precision,            -- realised variance over the baseline estimator's (identity)
  ratio_low            double precision,            -- 90 % interval of that ratio (paired block bootstrap)
  ratio_high           double precision,
  run_id               bigint           not null references models.runs,
  primary key (method_version, scope, estimator)
);

alter table models.cse_bt_risk_test enable row level security;
create policy web_read on models.cse_bt_risk_test for select to web_reader using (true);
revoke all on models.cse_bt_risk_test from web_reader;
