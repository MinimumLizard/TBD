-- 0002: LKR government securities, as published by the PDMO (treasury.gov.lk).
--
-- Design (docs/architecture.md §5, audit §3):
--   * Facts are stored AS PUBLISHED. Nothing is filtered at ingest. The old pipeline dropped about 38
--     administered/step-coupon quotes a day and resolved series labels to ISINs while ingesting. Here every
--     row of every file is kept, and resolution to ISINs is a separate, versioned step (a model, Phase 3).
--   * Every fact row points at the exact archived file (raw_sha256) and the parser version that read it.
--     Re-parsing with a fixed parser adds rows under a new parser_version; old rows stay.
--   * "Current" views pick, per day, the rows from the latest-posted file (amended reports replace the
--     original) read by the newest parser version.

create schema if not exists bonds;

-- One row per file listed on a PDMO index page, per content version and parser version.
create table bonds.source_files (
  url             text        not null,
  raw_sha256      text        not null references ops.raw_objects,
  fetch_id        bigint      not null references ops.raw_fetches,
  parser_version  integer     not null,
  kind            text        not null check (kind in
                    ('daily_summary', 'volumes', 'trade_summary', 'bond_auction', 'bond_issuance')),
  index_year      integer     not null,
  posted_date     date,
  label_date      date,
  amended         boolean     not null default false,
  report_date     date,                 -- the date the file's contents are FOR (from the file itself)
  trading_date    date,                 -- daily summaries only: the transaction day they also cover
  parse_status    text        not null check (parse_status in ('ok', 'failed')),
  parse_note      text,
  rows_parsed     integer     not null default 0,
  ingested_at     timestamptz not null default now(),
  primary key (url, raw_sha256, parser_version)
);
create trigger source_files_append_only before update or delete on bonds.source_files
  for each row execute function ops.forbid_change();

-- Dealer two-way quotes from the Daily Summary Report (QuotesTBond sheet). Keyed by series label, as printed.
create table bonds.quotes (
  raw_sha256      text             not null references ops.raw_objects,
  parser_version  integer          not null,
  row_no          integer          not null,
  report_date     date             not null,
  trading_date    date,
  series_label    text,                   -- canonical form, e.g. 10.00%2030A
  printed_label   text,                   -- as printed, kept for step-coupon labels
  coupon_pct      double precision,       -- first coupon for step-coupon bonds
  n_coupon_steps  integer          not null,
  maturity_date   date             not null,
  bid_price       double precision,
  offer_price     double precision,
  bid_yield       double precision,       -- percent per annum
  offer_yield     double precision,
  source          text             not null default 'pdmo',
  fetched_at      timestamptz      not null,
  ingested_at     timestamptz      not null default now(),
  primary key (raw_sha256, parser_version, row_no)
);
create index on bonds.quotes (report_date);

-- Outright transaction volumes per ISIN (dated by the data itself: maturity - remaining_years * 365).
create table bonds.volumes (
  raw_sha256      text             not null references ops.raw_objects,
  parser_version  integer          not null,
  row_no          integer          not null,
  obs_date        date             not null,
  isin            text             not null,
  maturity_date   date             not null,
  volume_lkr      bigint           not null,
  source          text             not null default 'pdmo',
  fetched_at      timestamptz      not null,
  ingested_at     timestamptz      not null default now(),
  primary key (raw_sha256, parser_version, row_no)
);
create index on bonds.volumes (obs_date);

-- Executed secondary-market trades per ISIN (bills and bonds), from the Trade Summary PDF.
create table bonds.trades (
  raw_sha256      text             not null references ops.raw_objects,
  parser_version  integer          not null,
  row_no          integer          not null,
  obs_date        date             not null,
  isin            text             not null,
  security_type   text             not null,
  open_yield      double precision,
  close_yield     double precision,
  high_yield      double precision,
  low_yield       double precision,
  wavg_yield      double precision,
  volume_lkr      bigint,
  n_trades        integer,
  source          text             not null default 'pdmo',
  fetched_at      timestamptz      not null,
  ingested_at     timestamptz      not null default now(),
  primary key (raw_sha256, parser_version, row_no)
);
create index on bonds.trades (obs_date);

-- Auction results (table releases) and issuance-window results (prose releases).
create table bonds.auction_results (
  raw_sha256      text             not null references ops.raw_objects,
  parser_version  integer          not null,
  row_no          integer          not null,
  auction_date    date             not null,
  kind            text             not null check (kind in ('auction', 'issuance')),
  settlement_date date,
  isin            text             not null,
  series_label    text,
  maturity_date   date             not null,
  coupon_pct      double precision,
  way_pct         double precision,       -- weighted average yield
  offered_lkr     bigint,
  bids_lkr        bigint,
  accepted_lkr    bigint,
  source          text             not null default 'pdmo',
  fetched_at      timestamptz      not null,
  ingested_at     timestamptz      not null default now(),
  primary key (raw_sha256, parser_version, row_no)
);

-- Auction announcements (published before the auction): issue dates, coupon dates, accrued interest.
create table bonds.auction_announcements (
  raw_sha256      text             not null references ops.raw_objects,
  parser_version  integer          not null,
  row_no          integer          not null,
  auction_date    date             not null,
  settlement_date date,
  isin            text             not null,
  series_label    text,
  maturity_date   date             not null,
  coupon_pct      double precision,
  issue_date      date,
  coupon_dates    text,                   -- "MM-DD,MM-DD"
  accrued_per_100 double precision,
  offered_lkr     bigint,
  source          text             not null default 'pdmo',
  fetched_at      timestamptz      not null,
  ingested_at     timestamptz      not null default now(),
  primary key (raw_sha256, parser_version, row_no)
);

do $$
declare t text;
begin
  foreach t in array array['quotes', 'volumes', 'trades', 'auction_results', 'auction_announcements'] loop
    execute format('create trigger %I before update or delete on bonds.%I
                    for each row execute function ops.forbid_change()', t || '_append_only', t);
  end loop;
end $$;

-- The newest parser version that has read each file successfully.
create view bonds.files_latest_parse as
select distinct on (url, raw_sha256) *
from bonds.source_files
where parse_status = 'ok'
order by url, raw_sha256, parser_version desc, fetch_id desc;

-- For each report day and kind, the file that wins: the latest posted (amended reports are posted later), then
-- the latest by label date, then the one stored last (fetch order follows the old pipeline's processing order).
-- Two different files can legitimately cover the same day (e.g. an amendment); only one is current.
create view bonds.files_current as
select distinct on (kind, report_date) *
from bonds.files_latest_parse
where kind in ('daily_summary', 'volumes', 'trade_summary')
order by kind, report_date, posted_date desc nulls last, label_date desc nulls last, fetch_id desc;

create view bonds.quotes_current as
select q.* from bonds.quotes q
join bonds.files_current f
  on f.raw_sha256 = q.raw_sha256 and f.parser_version = q.parser_version and f.kind = 'daily_summary';

create view bonds.volumes_current as
select v.* from bonds.volumes v
join bonds.files_current f
  on f.raw_sha256 = v.raw_sha256 and f.parser_version = v.parser_version and f.kind = 'volumes';

create view bonds.trades_current as
select t.* from bonds.trades t
join bonds.files_current f
  on f.raw_sha256 = t.raw_sha256 and f.parser_version = t.parser_version and f.kind = 'trade_summary';

-- Auction documents are each distinct events, so every file's latest parse is current.
-- (The same file is sometimes listed under two URLs, so files are de-duplicated by content first.)
create view bonds.auction_results_current as
select a.* from bonds.auction_results a
join (select distinct raw_sha256, parser_version from bonds.files_latest_parse where kind = 'bond_auction') f
  on f.raw_sha256 = a.raw_sha256 and f.parser_version = a.parser_version;

create view bonds.auction_announcements_current as
select a.* from bonds.auction_announcements a
join (select distinct raw_sha256, parser_version from bonds.files_latest_parse where kind = 'bond_issuance') f
  on f.raw_sha256 = a.raw_sha256 and f.parser_version = a.parser_version;
