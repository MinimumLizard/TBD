-- 0009 (2026-10-18): CSE corporate actions and total returns (Phase 3b, part 1; audit C6 and C7).
--
-- Facts (append-only, like every fact table):
--   cse.company_announcements      each company's announcement list (getAnnouncementByCompany), one row per
--                                  company and announcement; the old terminal's data/raw/announcements/byCompany
--   cse.announcement_details       each announcement's detail response (getAnnouncementById, the typed record;
--                                  getGeneralAnnouncementById, the "(DATES)" follow-ups), one row per announcement,
--                                  endpoint and distinct response, with the typed fields as served
--   cse.corporate_action_reviews   every version of the owner's confirmations
--                                  (config/corporate_actions_review.yaml), as loaded before each model run
-- Model outputs:
--   models.cse_corporate_action       every corporate-action row the old terminal's corporate_actions.csv holds
--   models.cse_corporate_action_used  the actions total returns use: confirmed, or confirmed by the owner
--   models.cse_total_return           per share and traded session: the total-return factor, the TRI and the
--                                     price-only return

create table cse.company_announcements (
  symbol           text        not null,      -- the share the list was asked for (the voting line where there is one)
  announcement_id  bigint      not null,
  list_row_id      bigint,                    -- the list's own row id (`id`), not the announcement id
  announced_date   date,                      -- dateOfAnnouncement; null if the CSE's text could not be read as a date
  date_text        text,                      -- dateOfAnnouncement as served
  category         text        not null,      -- announcementCategory, surrounding spaces removed
  company          text,
  fetch_id         bigint      not null references ops.raw_fetches,
  fetched_at       timestamptz not null,
  ingested_at      timestamptz not null default now(),
  primary key (symbol, announcement_id)
);
create index on cse.company_announcements (announcement_id);

create table cse.announcement_details (
  announcement_id  bigint      not null,
  endpoint         text        not null check (endpoint in ('getAnnouncementById', 'getGeneralAnnouncementById')),
  raw_sha256       text        not null references ops.raw_objects,
  has_detail       boolean     not null,      -- false: 204 / {} (the other endpoint serves this announcement)
  d_type           text,                      -- reqBaseAnnouncement.dType, e.g. CashDividendWithDates
  symbol           text,                      -- reqBaseAnnouncement.symbol (the bare company code)
  base             jsonb,                     -- reqBaseAnnouncement exactly as served: every typed field
  docs             jsonb,                     -- reqAnnouncementDocs as served (the PDF links)
  fetch_id         bigint      not null references ops.raw_fetches,
  fetched_at       timestamptz not null,
  ingested_at      timestamptz not null default now(),
  primary key (announcement_id, endpoint, raw_sha256)
);

create table cse.corporate_action_reviews (
  version_id    bigserial   primary key,
  file_sha256   text        not null,         -- SHA-256 of the file's bytes
  source_path   text        not null,         -- config/corporate_actions_review.yaml
  confirm       jsonb       not null,         -- {"<action id>": {<field>: <corrected value>, ...}}
  reject        jsonb       not null,         -- ["<action id>", ...]
  code_version  text,                         -- the git commit the file was read at
  loaded_at     timestamptz not null default now()
);

do $$
declare t text;
begin
  foreach t in array array['company_announcements', 'announcement_details', 'corporate_action_reviews'] loop
    execute format('create trigger %I before update or delete on cse.%I
                    for each row execute function ops.forbid_change()', t || '_append_only', t);
    execute format('alter table cse.%I enable row level security', t);
  end loop;
end $$;

-- cse_corporate_actions: the old terminal's corporate_actions.csv, one row per action id, plus what became of it.
create table models.cse_corporate_action (
  method_version      text             not null,
  action_id           text             not null,   -- '<announcement id>[+<dates announcement id>]:<symbol>'
  symbol              text             not null,
  action_type         text             not null,   -- cash_dividend | subdivision | scrip | rights
  ex_date             date,
  amount_per_share    double precision,            -- rupees per share (cash dividends)
  ratio_new           double precision,            -- new shares ...
  ratio_held          double precision,            -- ... per this many existing shares
  factor              double precision,            -- share-count factor (sub-division, scrip)
  subscription_price  double precision,            -- rupees per new share (rights)
  status              text             not null,   -- confirmed | needs_review (as the old CSV)
  note                text             not null,
  source_url          text             not null,   -- the announcement's PDF ('' when there is none)
  announcement_id     bigint           not null,
  announced_date      date,
  use_status          text             not null    -- used | awaiting_confirmation | rejected | superseded | replaced
                      check (use_status in ('used', 'awaiting_confirmation', 'rejected', 'superseded', 'replaced')),
  run_id              bigint           not null references models.runs,
  primary key (method_version, action_id)
);
create index on models.cse_corporate_action (method_version, symbol);

create table models.cse_corporate_action_used (
  method_version      text             not null,
  action_id           text             not null,
  symbol              text             not null,
  action_type         text             not null,
  ex_date             date             not null,
  amount_per_share    double precision,
  ratio_new           double precision,
  ratio_held          double precision,
  factor              double precision,
  subscription_price  double precision,
  status              text             not null,   -- confirmed | confirmed (reviewed)
  note                text             not null,
  source_url          text             not null,
  announced_date      date,
  run_id              bigint           not null references models.runs,
  primary key (method_version, action_id)
);
create index on models.cse_corporate_action_used (method_version, symbol);

create table models.cse_total_return (
  method_version  text             not null,
  symbol          text             not null,
  session_date    date             not null,   -- a session the share traded in
  close           double precision not null,   -- unadjusted close
  price_return    double precision,            -- close / previous traded close - 1
  total_return    double precision,            -- (close x F + D x (1 - withholding)) / base - 1
  share_factor    double precision not null,   -- F: sub-divisions and scrip issues that went ex since the last close
  dividend        double precision not null,   -- D: cash dividends per share that went ex since the last close
  base_price      double precision,            -- the previous close, or the theoretical ex-rights price
  events          text             not null,   -- the actions applied on this session, as the old terminal wrote them
  tri             double precision not null,   -- total-return index, 1 at the share's first close
  tr_1w           double precision,            -- total return over 5 sessions (last traded TRI on or before each end)
  tr_1m           double precision,            -- ... 21 sessions
  tr_3m           double precision,            -- ... 63 sessions
  run_id          bigint           not null references models.runs,
  primary key (method_version, symbol, session_date)
);

do $$
declare t text;
begin
  foreach t in array array['cse_corporate_action', 'cse_corporate_action_used', 'cse_total_return'] loop
    execute format('alter table models.%I enable row level security', t);
    execute format('create policy web_read on models.%I for select to web_reader using (true)', t);
    execute format('grant select on models.%I to web_reader', t);
  end loop;
end $$;
