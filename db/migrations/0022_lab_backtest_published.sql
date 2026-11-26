-- The portfolio lab's walk-forward test is published in the Pro tier (owner, 2026-11-26, decision 0027): the website's
-- role may read its tables again (migrations 0017 and 0020 revoked them). Row-level security and the web_read policies
-- created in 0017 and 0020 stay; the tier check in web/lib/entitlements.ts decides who sees the rows.
-- The lab's estimates and the owner's own portfolios (cse_risk_estimates, cse_portfolio_lab, cse_lab_record) stay
-- revoked: they are internal (decision 0023), and the owner's record reads private settings.
grant select on models.cse_bt_summary, models.cse_bt_nav, models.cse_bt_event, models.cse_bt_target,
  models.cse_bt_trade, models.cse_bt_risk_test to web_reader;
