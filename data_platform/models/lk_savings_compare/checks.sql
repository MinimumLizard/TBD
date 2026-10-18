-- Measurements quoted in METHOD.md:  psql "$DATABASE_URL" -f data_platform/models/lk_savings_compare/checks.sql
-- link factors at the first month of each newer base
select n.base newer, o.base older, n.month, o.value older_v, n.value newer_v, round((o.value / n.value)::numeric, 4) factor
from rates.cpi_monthly_current n join rates.cpi_monthly_current o on o.month = n.month and o.base <> n.base
where n.month = (select min(month) from rates.cpi_monthly_current x where x.base = n.base)
  and (n.base, o.base) in (('2006/07', '2002'), ('2013', '2006/07'), ('2021', '2013'));
-- growth over the 2013/2021 overlap in each base
select base, round(((max(value) filter (where month = '2023-01-01')) / (max(value) filter (where month = '2022-01-01')) - 1)::numeric * 100, 1) pct
from rates.cpi_monthly_current where base in ('2013', '2021') group by 1;
-- 4.04 TB_12M / auction-file before-tax yield (last 364-day auction of the month), median per period
with last_auction as (
  select distinct on (date_trunc('month', issue_date)) date_trunc('month', issue_date)::date m, yield_pct
  from rates.tbill_auctions_current where tenor_days = 364 and yield_pct is not null
  order by date_trunc('month', issue_date), issue_date desc)
select case when m < '2013-01-01' then '2003-2012' when m < '2018-04-01' then '2013-2018/03' else '2018/04-2025' end p,
       round(percentile_cont(0.5) within group (order by t.value / a.yield_pct)::numeric, 3) median_ratio, count(*)
from last_auction a join rates.cbsl_monthly_current t on t.series = 'TB_12M' and t.month = a.m group by 1 order by 1;
