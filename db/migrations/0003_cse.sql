-- 0003: Colombo Stock Exchange facts, from the public JSON API behind cse.lk (audit §2).
--
-- Keys are natural keys plus `source`, so a session collected by the daily job ('daily') and the same session
-- re-read from the one-year chart endpoint ('backfill') sit side by side, as in the old CSV files. A re-fetch
-- that disagrees with a stored row never overwrites it: the disagreement goes to ops.value_conflicts.
--
-- Volume has two meanings at the CSE (audit addendum, item 4):
--   volume_regular  shares traded on the regular market   (tradeSummary.sharevolume)
--   volume_total    including negotiated crossings          (tradeSummary.crossingVolume; chart endpoint `q`)
-- Both are stored under their own names; the old prices.csv mixed them at 2026-10-02.

create schema if not exists cse;

create table cse.security_list (
  session_date  date        not null,
  symbol        text        not null,
  stock_id      integer     not null,      -- the id companyChartDataByStock expects
  name          text        not null,
  active        integer,
  fetch_id      bigint      not null references ops.raw_fetches,
  fetched_at    timestamptz not null,
  ingested_at   timestamptz not null default now(),
  primary key (session_date, symbol)
);

create table cse.prices_daily (
  session_date    date             not null,
  symbol          text             not null,
  source          text             not null check (source in ('daily', 'backfill')),
  close           double precision not null,
  previous_close  double precision,
  open            double precision,
  high            double precision,
  low             double precision,
  volume_regular  double precision,
  volume_total    double precision,
  trades_regular  integer,
  trades_total    integer,
  turnover        double precision,          -- LKR, regular market (daily rows only)
  turnover_est    double precision,          -- close × volume_total, backfill rows only (decision D2)
  market_cap      double precision,
  last_traded_at  timestamptz,
  fetch_id        bigint           not null references ops.raw_fetches,
  fetched_at      timestamptz      not null,
  ingested_at     timestamptz      not null default now(),
  primary key (session_date, symbol, source)
);
create index on cse.prices_daily (symbol, session_date);

create table cse.indices_daily (
  session_date  date             not null,
  index_code    text             not null,  -- ASI, S&P SL20, sector codes, ASTRI, S&P SL20 TRI
  source        text             not null check (source in ('daily', 'backfill')),
  value         double precision not null,
  change        double precision,
  fetch_id      bigint           not null references ops.raw_fetches,
  fetched_at    timestamptz      not null,
  ingested_at   timestamptz      not null default now(),
  primary key (session_date, index_code, source)
);

create table cse.market_daily (
  session_date  date             not null,
  source        text             not null check (source in ('daily')),
  turnover      double precision,
  volume        double precision,
  trades        double precision,
  foreign_buy   double precision,
  foreign_sell  double precision,
  listed        integer,
  traded        integer,
  market_cap    double precision,
  aspi          double precision,
  spsl20        double precision,
  astri         double precision,
  spsl20_tri    double precision,
  per           double precision,
  pbv           double precision,
  dy            double precision,
  fetch_id      bigint           not null references ops.raw_fetches,
  fetched_at    timestamptz      not null,
  ingested_at   timestamptz      not null default now(),
  primary key (session_date, source)
);

create table cse.announcements (
  announcement_id  text        primary key,    -- announcementId; financial reports are 'F' || id
  announced_date   date        not null,
  symbol           text,
  company          text        not null,
  title            text        not null,
  category         text        not null,
  document_url     text,
  detail_endpoint  text,                        -- getAnnouncementById | getGeneralAnnouncementById | null
  list_fetch_id    bigint      not null references ops.raw_fetches,
  detail_fetch_id  bigint      references ops.raw_fetches,
  fetched_at       timestamptz not null,
  ingested_at      timestamptz not null default now()
);

-- Per-company snapshot from companyInfoSummery (price statistics, share count, CSE-published betas).
create table cse.company_info_daily (
  session_date       date             not null,
  symbol             text             not null,
  last_traded_price  double precision,
  previous_close     double precision,
  high_52w           double precision,          -- unadjusted, as served
  low_52w            double precision,
  market_cap         double precision,
  quantity_issued    double precision,
  isin               text,
  beta_triasi        double precision,
  beta_spsl          double precision,
  beta_period        text,
  beta_quarter       integer,
  fetch_id           bigint           not null references ops.raw_fetches,
  fetched_at         timestamptz      not null,
  ingested_at        timestamptz      not null default now(),
  primary key (session_date, symbol)
);

create table cse.company_profiles (
  symbol        text        not null,
  raw_sha256    text        not null references ops.raw_objects,
  sector_label  text,                          -- as served, not normalised (normalising is a model)
  board_type    text,
  fetch_id      bigint      not null references ops.raw_fetches,
  fetched_at    timestamptz not null,
  ingested_at   timestamptz not null default now(),
  primary key (symbol, raw_sha256)
);

do $$
declare t text;
begin
  foreach t in array array['security_list', 'prices_daily', 'indices_daily', 'market_daily', 'announcements',
                           'company_info_daily', 'company_profiles'] loop
    execute format('create trigger %I before update or delete on cse.%I
                    for each row execute function ops.forbid_change()', t || '_append_only', t);
  end loop;
end $$;

-- Readers that want "one price per stock per session" prefer the daily row (it carries real turnover),
-- exactly as the old terminal did (cse.metrics._prefer_daily).
create view cse.prices_daily_current as
select distinct on (session_date, symbol) *
from cse.prices_daily
order by session_date, symbol, case source when 'daily' then 0 else 1 end;

create view cse.indices_daily_current as
select distinct on (session_date, index_code) *
from cse.indices_daily
order by session_date, index_code, case source when 'daily' then 0 else 1 end;

create view cse.company_profiles_current as
select distinct on (symbol) * from cse.company_profiles order by symbol, fetched_at desc;
