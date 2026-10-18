-- 0011 (2026-10-18): interest rates and inflation for the "fixed deposits, treasury bills and inflation" education
-- page (docs/plan-retail-features.md §4), and the outputs of the lk_savings_compare model.
--
-- Facts, in a new schema `rates`, stored AS PUBLISHED, like the bond facts (0002):
--   * every row points at the archived file it came from (raw_sha256) and the parser version that read it;
--   * a re-published file (CBSL renames its files with each update; DCS replaces its PDFs in place) adds rows beside
--     the old ones. Nothing is updated or deleted;
--   * the *_current views show, for each dataset, the rows of its newest file read by the newest parser version.
--     Each file is a complete history of its table, so one file wins as a whole: a value CBSL or DCS later revises
--     appears revised, and a value they withdraw disappears, exactly as in their own latest file.
--
-- Sources (config/sources.yaml): `cbsl` (statistical tables 4.03 and 4.04, the weekly treasury bill auction file)
-- and `dcs_cpi` (the Department of Census and Statistics' "Movements of the CCPI" PDFs, one per base year).

create schema if not exists rates;

-- One row per file, per content version and parser version.
create table rates.source_files (
  url             text        not null,
  raw_sha256      text        not null references ops.raw_objects,
  fetch_id        bigint      not null references ops.raw_fetches,
  parser_version  integer     not null,
  source_id       text        not null check (source_id in ('cbsl', 'dcs_cpi')),
  -- which table the file is: cbsl_4.04 (monthly rates), cbsl_4.03 (annual rates), cbsl_tbill_auctions (weekly),
  -- dcs_ccpi_<base> (one CCPI base, e.g. dcs_ccpi_2021). For DCS the base comes from the file's own title.
  dataset         text        not null,
  file_date       date,                 -- the date in a CBSL file name (table4.04_20261012.xlsx); null for DCS
  label           text,                 -- the link text on the publisher's page
  parse_status    text        not null check (parse_status in ('ok', 'failed')),
  parse_note      text,
  rows_parsed     integer     not null default 0,
  ingested_at     timestamptz not null default now(),
  primary key (url, raw_sha256, parser_version)
);
create trigger source_files_append_only before update or delete on rates.source_files
  for each row execute function ops.forbid_change();

-- CBSL table 4.04 (monthly, 2003 to date), one row per series and month. Percent per annum, end of month unless the
-- series is a monthly average (AWDR, AWFDR, AWNDR, AWNFDR: the CBSL computes them monthly).
--   series: OPR, SDFR, SLFR, TB_3M, TB_12M (primary market yields), AWDR, AWFDR, AWNDR, AWNFDR,
--           FD_12M_MIN, FD_12M_MAX (the range of commercial banks' 12-month fixed deposit rates)
create table rates.cbsl_monthly (
  raw_sha256      text             not null references ops.raw_objects,
  parser_version  integer          not null,
  series          text             not null,
  month           date             not null check (extract(day from month) = 1),   -- the first day of the month
  value           double precision not null,
  source          text             not null default 'cbsl',
  fetched_at      timestamptz      not null,
  ingested_at     timestamptz      not null default now(),
  primary key (raw_sha256, parser_version, series, month)
);

-- CBSL table 4.03 (annual, 1990 to date): the same series, end of year.
create table rates.cbsl_annual (
  raw_sha256      text             not null references ops.raw_objects,
  parser_version  integer          not null,
  series          text             not null,
  year            integer          not null,
  value           double precision not null,
  source          text             not null default 'cbsl',
  fetched_at      timestamptz      not null,
  ingested_at     timestamptz      not null default now(),
  primary key (raw_sha256, parser_version, series, year)
);

-- CBSL weekly treasury bill auctions (1996 to November 2025 when downloaded): one row per auction and tenor.
-- yield_pct is the weighted average yield "before tax" as published; yield_without_tax_pct is the "without tax"
-- column, printed for a few weeks only. A yield printed as 0 (no bills accepted) is stored as null.
create table rates.tbill_auctions (
  raw_sha256             text             not null references ops.raw_objects,
  parser_version         integer          not null,
  issue_date             date             not null,
  tenor_days             integer          not null check (tenor_days in (91, 182, 364)),
  offered_mn             double precision,
  received_mn            double precision,
  accepted_mn            double precision,
  yield_pct              double precision,
  yield_without_tax_pct  double precision,
  source                 text             not null default 'cbsl',
  fetched_at             timestamptz      not null,
  ingested_at            timestamptz      not null default now(),
  primary key (raw_sha256, parser_version, issue_date, tenor_days)
);

-- DCS consumer price index, as printed in each base year's "Movements of the CCPI" table. Bases are kept apart;
-- linking them into one series is a modelling step (lk_savings_compare, METHOD.md).
create table rates.cpi_monthly (
  raw_sha256      text             not null references ops.raw_objects,
  parser_version  integer          not null,
  index_code      text             not null check (index_code in ('CCPI')),
  base            text             not null,     -- as printed: 2021, 2013, 2006/07, 2002
  month           date             not null check (extract(day from month) = 1),
  value           double precision not null,
  source          text             not null default 'dcs',
  fetched_at      timestamptz      not null,
  ingested_at     timestamptz      not null default now(),
  primary key (raw_sha256, parser_version, index_code, base, month)
);

do $$
declare t text;
begin
  foreach t in array array['cbsl_monthly', 'cbsl_annual', 'tbill_auctions', 'cpi_monthly'] loop
    execute format('create trigger %I before update or delete on rates.%I
                    for each row execute function ops.forbid_change()', t || '_append_only', t);
  end loop;
end $$;

-- The newest parser version that has read each file successfully.
create view rates.files_latest_parse as
select distinct on (url, raw_sha256) *
from rates.source_files
where parse_status = 'ok'
order by url, raw_sha256, parser_version desc, fetch_id desc;

-- For each dataset, the one file that is current: the newest by the date in its name, then the one fetched last.
create view rates.files_current as
select distinct on (dataset) *
from rates.files_latest_parse
order by dataset, file_date desc nulls last, fetch_id desc;

create view rates.cbsl_monthly_current as
select m.* from rates.cbsl_monthly m
join rates.files_current f on f.raw_sha256 = m.raw_sha256 and f.parser_version = m.parser_version
 and f.dataset = 'cbsl_4.04';

create view rates.cbsl_annual_current as
select a.* from rates.cbsl_annual a
join rates.files_current f on f.raw_sha256 = a.raw_sha256 and f.parser_version = a.parser_version
 and f.dataset = 'cbsl_4.03';

create view rates.tbill_auctions_current as
select t.* from rates.tbill_auctions t
join rates.files_current f on f.raw_sha256 = t.raw_sha256 and f.parser_version = t.parser_version
 and f.dataset = 'cbsl_tbill_auctions';

create view rates.cpi_monthly_current as
select c.* from rates.cpi_monthly c
join rates.files_current f on f.raw_sha256 = c.raw_sha256 and f.parser_version = c.parser_version
 and f.dataset like 'dcs_ccpi_%';

-- Second line of defence (0006): row-level security on every new table. The website's login cannot read rates.*.
alter table rates.source_files enable row level security;
alter table rates.cbsl_monthly enable row level security;
alter table rates.cbsl_annual enable row level security;
alter table rates.tbill_auctions enable row level security;
alter table rates.cpi_monthly enable row level security;

-- ===== lk_savings_compare (model outputs) ======================================================================

-- The monthly inputs the model used, after its choices: which deposit rate stood for a 12-month fixed deposit that
-- month, the 12-month bill yield, the linked CCPI and the advance income tax rate in force. Shown on the page so
-- every figure can be traced back to the published tables.
create table models.savings_rates (
  method_version  text             not null,
  month           date             not null,
  fd_rate_pct     double precision,
  fd_series       text,                         -- AWNFDR, or AWFDR before the CBSL published AWNFDR
  bill_published_pct double precision,          -- 12-month treasury bill primary market yield, as in table 4.04
  bill_rate_pct   double precision,             -- the same before tax: from May 2002 to March 2018 table 4.04
                                                -- prints yields after the 10% withholding tax, added back here
                                                -- (lk_savings_compare METHOD.md)
  cpi             double precision,             -- CCPI linked across base years, expressed on the 2002 base
  cpi_base        text,                         -- the base year whose index this month's figure comes from
  inflation_yoy   double precision,             -- cpi / cpi 12 months earlier - 1 (a fraction)
  fd_tax_pct      double precision not null,    -- advance income tax on fixed deposit interest paid this month
  run_id          bigint           not null references models.runs,
  primary key (method_version, month)
);

-- What Rs 100,000 grew to, for every start month and horizon (1 to 10 years), per instrument and basis.
--   instrument: fd (12-month fixed deposit, renewed yearly), tbill (12-month treasury bill, rolled yearly)
--   basis:      nominal | nominal_after_tax | real | real_after_tax  (bills: nominal and real only)
create table models.savings_growth (
  method_version  text             not null,
  start_month     date             not null,
  horizon_years   integer          not null,
  instrument      text             not null check (instrument in ('fd', 'tbill')),
  basis           text             not null check (basis in ('nominal', 'nominal_after_tax', 'real', 'real_after_tax')),
  end_month       date             not null,
  value           double precision not null,   -- rupees, from Rs 100,000
  annual_rate     double precision not null,   -- (value / 100,000)^(1 / years) - 1 (a fraction)
  fd_series       text,                         -- fd only: AWNFDR, AWFDR, or AWFDR+AWNFDR when a period spans both
  run_id          bigint           not null references models.runs,
  primary key (method_version, start_month, horizon_years, instrument, basis)
);
create index on models.savings_growth (method_version, horizon_years, instrument, basis);

-- Across every start month, per horizon (1, 3, 5, 10 years), instrument and basis: how the outcomes were spread.
create table models.savings_summary (
  method_version   text             not null,
  horizon_years    integer          not null,
  instrument       text             not null,
  basis            text             not null,
  n_periods        integer          not null,
  first_start      date             not null,
  last_start       date             not null,
  n_ahead          integer,                    -- periods in which it ended above the other instrument, same basis
                                               -- (before tax only: bills' tax depends on the person)
  n_above_start    integer          not null,  -- periods in which it ended above Rs 100,000 (real bases: kept
                                               -- ahead of inflation)
  median_value     double precision not null,
  best_value       double precision not null,
  best_start       date             not null,
  worst_value      double precision not null,
  worst_start      date             not null,
  median_annual    double precision not null,
  best_annual      double precision not null,
  worst_annual     double precision not null,
  run_id           bigint           not null references models.runs,
  primary key (method_version, horizon_years, instrument, basis)
);

do $$
declare t text;
begin
  foreach t in array array['savings_rates', 'savings_growth', 'savings_summary'] loop
    execute format('alter table models.%I enable row level security', t);
    execute format('create policy web_read on models.%I for select to web_reader using (true)', t);
    execute format('grant select on models.%I to web_reader', t);
  end loop;
end $$;
