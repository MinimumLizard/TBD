-- 0013 (2026-10-19): CSE interim reports, ownership and company figures (Phase 3b; audit C13-C16, C21, C22).
--
-- Facts (append-only, like every fact table):
--   cse.financial_reports        each report collected (or attempted): the CSE's report id, company, kind, title,
--                                period, upload time, PDF link, pages, words, status, and the SHA-256 of the PDF
--                                (when we downloaded it; the old terminal kept only the text) and of its text
--   cse.report_texts             each distinct report text (pdftotext -layout), keyed by its SHA-256; the same
--                                bytes are also in the raw archive under that name
--   cse.company_fiscal_years     each company profile's financial year end (finYearEnd), per profile response
--   cse.ownership_confirmations  every version of the owner's ownership confirmations (aliases of one holder,
--                                parents of unlisted holders), as loaded before each model run
-- Model outputs:
--   models.cse_holding                 every row of every parsed top-20 table, with the credited owner (names
--                                      private individuals: shown, on the owner's decision 0021)
--   models.cse_ownership_detail        per company and session, the old companies.csv, incl. the controller's
--                                      name and the chain
--   models.cse_company_ownership       per company and session: shares of the top 20 by owner type, the
--                                      controlling block, the ownership group, a free-float estimate
--   models.cse_report_figures          per report: EPS and NAV per share, reconciled inside the report
--   models.cse_fundamentals            per company and session: TTM EPS, NAV per share, P/E, P/B, ROE, dividend yield

create table cse.report_texts (
  sha256       text        primary key references ops.raw_objects,
  body         text        not null,          -- the text, decoded as UTF-8 (a NUL character, if any, as U+FFFD)
  words        integer     not null,
  ingested_at  timestamptz not null default now()
);

create table cse.financial_reports (
  report_id    bigint      not null,          -- the CSE's report id (the financials list's `id`)
  code         text        not null,          -- company code, e.g. JKH
  symbol       text        not null,          -- the share the list was asked for (the voting line where there is one)
  kind         text        not null check (kind in ('quarterly', 'annual')),
  title        text        not null,          -- fileText
  period_date  date,                          -- manualDate (Sri Lanka time); null when the CSE gave none
  uploaded_at  timestamptz,                   -- uploadedDate
  url          text        not null,          -- the PDF on cdn.cse.lk
  pages        integer,
  words        integer,
  status       text        not null check (status in ('ok', 'no_text', 'download_failed')),
  pdf_sha256   text        references ops.raw_objects,   -- null for the old terminal's reports (it kept only text)
  text_sha256  text        references cse.report_texts,  -- null when the download failed
  extracted_by text,                          -- 'pdftotext -layout' (+ version), or the old terminal's text file
  fetch_id     bigint      not null references ops.raw_fetches,   -- the PDF (live) or the old index file (migration)
  fetched_at   timestamptz not null,          -- when the PDF was downloaded (the old index's fetched_utc)
  ingested_at  timestamptz not null default now(),
  primary key (report_id, fetched_at)
);
create index on cse.financial_reports (code);

-- One row per report: a successful download wins over a failed attempt, then the latest.
create view cse.financial_reports_current as
select distinct on (report_id) * from cse.financial_reports
order by report_id, (status = 'download_failed'), fetched_at desc;

create table cse.company_fiscal_years (
  symbol        text        not null,
  raw_sha256    text        not null references ops.raw_objects,   -- the companyProfile response
  session_date  date,                         -- the session whose end-of-day run fetched it (null: not known)
  fin_year_end  text,                         -- finYearEnd as served: '1' = 31 March, '2' = 31 December
  fetch_id      bigint      not null references ops.raw_fetches,
  fetched_at    timestamptz not null,
  ingested_at   timestamptz not null default now(),
  primary key (symbol, raw_sha256)
);

create table cse.ownership_confirmations (
  version_id      bigserial   primary key,
  public_sha256   text        not null,       -- SHA-256 of the repository's two files (aliases, then parents)
  public          jsonb       not null,       -- {"aliases": {display name: {variants, type, symbol}},
                                              --  "parents": {holder: {owner, owner_type, pct, source, quote}}}
  private_sha256  text,                       -- SHA-256 of the private file (OWNERSHIP_PRIVATE_FILE); null: none yet
  private         jsonb       not null,       -- the same two sections from the private file: entries that name a
                                              -- private individual never go in the public repository
  code_version    text,
  loaded_at       timestamptz not null default now()
);

do $$
declare t text;
begin
  foreach t in array array['report_texts', 'financial_reports', 'company_fiscal_years', 'ownership_confirmations'] loop
    execute format('create trigger %I before update or delete on cse.%I
                    for each row execute function ops.forbid_change()', t || '_append_only', t);
    execute format('alter table cse.%I enable row level security', t);
  end loop;
end $$;

-- cse_ownership --------------------------------------------------------------------------------------------------

create table models.cse_holding (
  method_version  text             not null,
  report_id       bigint           not null,
  share_class     text             not null check (share_class in ('N', 'X')),   -- voting | non-voting
  row_no          integer          not null,   -- position in the table (ranks can tie)
  rank            integer          not null,
  period_date     date,
  code            text             not null,
  symbol          text             not null,
  name_as_filed   text             not null,
  shares          double precision not null,
  pct             double precision not null,
  fraction        double precision,            -- shares / the class's shares at the report date
  owner_key       text             not null,
  owner_name      text             not null,
  owner_type      text             not null,   -- listed | individual | joint | estate | trust | institution | company | nominee
  owner_symbol    text             not null,
  via             text             not null,   -- custodian or lender the shares are held through
  rule            text             not null,
  table_status    text             not null,   -- verified | verified_total | consistent | unverified
  source_url      text             not null,
  as_of           date             not null,   -- the session whose share counts checked the table
  run_id          bigint           not null references models.runs,
  primary key (method_version, report_id, share_class, row_no)
);
create index on models.cse_holding (method_version, code);

create table models.cse_ownership_detail (
  method_version          text             not null,
  session_date            date             not null,
  code                    text             not null,
  name                    text             not null,
  report_id               bigint,
  kind                    text,
  period_date             date,
  report_status           text             not null,  -- no_report | ok | no_table | no_text | download_failed
  status_n                text,
  note_n                  text,
  status_x                text,
  note_x                  text,
  rows                    integer,
  top_holders_pct_voting  double precision,
  market_cap              double precision,
  controller_key          text,
  controller_name         text,
  controller_type         text,
  control_pct             double precision,
  control_level           text,                       -- controlled (> 50 %) | influence (20-50 %)
  chain                   text,
  group_key               text             not null,
  group_name              text,
  source_url              text,
  run_id                  bigint           not null references models.runs,
  primary key (method_version, session_date, code)
);

create table models.cse_company_ownership (
  method_version    text             not null,
  session_date      date             not null,
  code              text             not null,
  report_id         bigint,
  period_date       date,                        -- the report's period: holdings are as at this date
  report_status     text             not null,   -- no_report | ok | no_table | no_text | download_failed
  table_status      text,                        -- the voting table's check (else the non-voting one's)
  top20_pct         double precision,            -- % of voting shares held by the published top 20
  pct_listed        double precision,            -- ... of which by listed companies
  pct_company       double precision,            --     unlisted companies
  pct_institution   double precision,            --     funds, insurers' funds, the state and its bodies
  pct_individual    double precision,
  pct_joint         double precision,
  pct_estate        double precision,
  pct_trust         double precision,
  pct_nominee       double precision,            --     unidentified nominee accounts
  pct_own_shares    double precision,            --     the company itself
  controller_type   text,                        -- the largest voting block's owner type (when >= 20 %)
  controller_name   text,                        -- its name, only when a company, a fund or the state
  control_pct       double precision,
  control_level     text,                        -- controlled | influence
  group_id          text             not null,   -- companies with the same group_id are in one ownership group
  group_head_type   text,
  group_head_name   text,                        -- only when a company, a fund or the state
  group_size        integer          not null,
  free_float_pct    double precision,            -- estimate: see METHOD.md
  market_cap        double precision,
  source_url        text,
  run_id            bigint           not null references models.runs,
  primary key (method_version, session_date, code)
);
create index on models.cse_company_ownership (method_version, code);

-- cse_fundamentals -----------------------------------------------------------------------------------------------

create table models.cse_report_figures (
  method_version  text             not null,
  report_id       bigint           not null,
  code            text             not null,
  period_date     date             not null,   -- the quarter the report covers
  fye             text             not null,   -- finYearEnd ('1' March, '2' December, '' unknown)
  shares          double precision,            -- the share count the figures reconciled under
  eps             double precision,            -- as printed (first column)
  eps_class       text             not null,   -- quarter | ytd | unknown | ''
  eps_status      text             not null,   -- verified | not found
  profit          double precision,            -- rupees
  unit            double precision,            -- the statement's unit: 1, 1000 or 1000000
  eps_line        text             not null,
  nav             double precision,            -- net assets per share, as printed
  nav_status      text             not null,
  equity          double precision,            -- rupees
  nav_line        text             not null,
  source_url      text             not null,
  as_of           date             not null,   -- the session whose share counts were tried
  run_id          bigint           not null references models.runs,
  primary key (method_version, report_id)
);
create index on models.cse_report_figures (method_version, code);

create table models.cse_fundamentals (
  method_version  text             not null,
  session_date    date             not null,
  code            text             not null,
  price           double precision,            -- the voting share's last close on or before the session
  price_date      date,
  shares          double precision,            -- shares issued (N + X) at the session
  fye             text             not null,   -- '31 Mar' | '31 Dec' | ''
  nav             double precision,            -- latest reconciled equity / shares
  nav_period      date,
  pb              double precision,
  ttm_profit      double precision,
  ttm_eps         double precision,
  ttm_to          date,
  ttm_note        text             not null,
  earnings_yield  double precision,
  pe              double precision,
  roe             double precision,
  div_ttm         double precision,            -- cash dividends per share, ex-dates in the last 365 days
  dy              double precision,
  report_id       bigint,                      -- the company's latest report (by period)
  report_period   date,
  report_url      text,
  run_id          bigint           not null references models.runs,
  primary key (method_version, session_date, code)
);
create index on models.cse_fundamentals (method_version, code);

do $$
declare t text;
begin
  foreach t in array array['cse_holding', 'cse_ownership_detail', 'cse_company_ownership', 'cse_report_figures',
                           'cse_fundamentals'] loop
    execute format('alter table models.%I enable row level security', t);
    -- every output is readable by the website: shareholders' names are shown, on the owner's decision of 2026-10-19
    -- (decision 0021, as for directors' names); the lawyer's answer is needed before anything is public
    execute format('create policy web_read on models.%I for select to web_reader using (true)', t);
    execute format('grant select on models.%I to web_reader', t);
  end loop;
end $$;
