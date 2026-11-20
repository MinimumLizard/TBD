-- The portfolio lab's second review (decision 0026): a third rebalancing policy, half-yearly reviews (the first session
-- of January and July), beside the quarterly and dynamic ones (cse_lab_backtest 1.2.0). INTERNAL RESEARCH, like the
-- rest of the lab (decisions 0023, 0024).
alter table models.cse_bt_summary drop constraint cse_bt_summary_policy_check;
alter table models.cse_bt_summary add constraint cse_bt_summary_policy_check
  check (policy in ('quarterly', 'half_yearly', 'dynamic'));
