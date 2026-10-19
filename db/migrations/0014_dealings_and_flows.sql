-- 0014 (2026-10-18): directors' share dealings and money flows (Phase 3b, part 3; audit C18 and C19).
--
-- No new fact table: the dealing notices are announcement details (cse.announcement_details, migration 0009), kept
-- exactly as the CSE served them, names included. The model outputs below are split so that every table holding a
-- person's name is UNPUBLISHED (config/entitlements.yaml unpublished_outputs): the website's database role cannot
-- read those at all, until the owner's lawyer has reviewed what may be shown.
--
-- Model outputs:
--   models.cse_dealing          cse_dealings: one row per disclosed transaction, without names (published)
--   models.cse_dealing_as_filed cse_dealings: the same transactions' names and free text as filed (UNPUBLISHED)
--   models.cse_flow_company     cse_flows: per company, window and as-of day: purchases, disposals, net, counts
--   models.cse_flow_summary     cse_flows: per as-of day: how many dealings, the median disclosure lag
--   models.cse_flow_dealing     cse_flows: per transaction: the kind of account that dealt and the flags
--   models.cse_flow_actor       cse_flows: per account that dealt, window and as-of day (names: UNPUBLISHED)

create table models.cse_dealing (
  method_version   text             not null,
  transaction_id   text             not null,   -- '<announcement id>:<n>', n = the transaction's place in the notice
  announcement_id  bigint           not null,
  line_no          integer          not null,
  symbol           text             not null,   -- the company's code as the notice gives it (no share class)
  company          text             not null,
  role             text             not null    -- the director's role, read from the notice's free text
                   check (role in ('chair', 'chief_executive', 'executive', 'non_executive',
                                   'independent_non_executive', 'several', 'not_stated')),
  account_type     text             not null check (account_type in ('own', 'related')),
  trade_date       date,                        -- the transaction date the notice gives
  deal_date        date,                        -- trade_date, or the announcement date when the notice gives none
  side             text             not null check (side in ('purchase', 'disposal', 'other')),
  quantity         double precision,
  price            double precision,            -- rupees per share
  value            double precision,            -- quantity x price, rupees
  announced_date   date,
  lag_days         integer,                     -- weekdays from trade_date to announced_date
  superseded_by    bigint,                      -- a later notice that re-files this one; null: this one counts
  run_id           bigint           not null references models.runs,
  primary key (method_version, transaction_id)
);
create index on models.cse_dealing (method_version, symbol);
create index on models.cse_dealing (method_version, deal_date);

create table models.cse_dealing_as_filed (
  method_version   text             not null,
  transaction_id   text             not null,
  director         text             not null,   -- as filed (a person's name)
  director_role    text             not null,   -- as filed (free text; sometimes names people)
  account          text             not null,   -- the account that dealt, as filed (a person or a company)
  trans_type       text             not null,   -- the transaction type, as filed (free text)
  source_url       text             not null,   -- the notice's PDF on the CSE's site
  run_id           bigint           not null references models.runs,
  primary key (method_version, transaction_id)
);

create table models.cse_flow_company (
  method_version   text             not null,
  as_of            date             not null,   -- the window ends on this dealing date
  window_days      integer          not null check (window_days in (30, 90, 365)),
  symbol           text             not null,
  company          text             not null,
  purchase_value   double precision not null,   -- rupees, purchases in the window
  disposal_value   double precision not null,   -- rupees, disposals in the window
  net_value        double precision not null,   -- purchases - disposals
  n_purchasers     integer          not null,   -- distinct accounts that made purchases
  n_disposers      integer          not null,   -- distinct accounts that made disposals
  n_transactions   integer          not null,
  cluster          boolean          not null,   -- two or more distinct purchasers and net purchases above zero
  run_id           bigint           not null references models.runs,
  primary key (method_version, as_of, window_days, symbol)
);
create index on models.cse_flow_company (method_version, symbol);

create table models.cse_flow_summary (
  method_version   text             not null,
  as_of            date             not null,
  n_dealings       integer          not null,   -- transactions dated on or before as_of (any side)
  n_trades         integer          not null,   -- ... of which purchases or disposals
  lag_median       double precision,            -- median disclosure lag, weekdays
  run_id           bigint           not null references models.runs,
  primary key (method_version, as_of)
);

create table models.cse_flow_dealing (
  method_version   text             not null,
  transaction_id   text             not null,
  symbol           text             not null,
  deal_date        date,
  side             text             not null check (side in ('purchase', 'disposal', 'other')),
  value            double precision,
  actor_type       text             not null,   -- the kind of account: individual, company, listed, ...
  large            boolean          not null,   -- value of Rs 10 mn or more
  related_account  boolean          not null,   -- dealt through a related ("relevant interest") account
  run_id           bigint           not null references models.runs,
  primary key (method_version, transaction_id)
);
create index on models.cse_flow_dealing (method_version, deal_date);

create table models.cse_flow_actor (
  method_version   text             not null,
  as_of            date             not null,
  window_days      integer          not null check (window_days in (30, 90, 365)),
  actor_key        text             not null,   -- the account's matching key (from its name)
  actor            text             not null,   -- the account's name (a person or a company)
  actor_type       text             not null,
  purchase_value   double precision not null,
  disposal_value   double precision not null,
  net_value        double precision not null,
  n_transactions   integer          not null,
  companies        text             not null,   -- JSON: [[code, net value], ...], the six largest by size
  run_id           bigint           not null references models.runs,
  primary key (method_version, as_of, window_days, actor_key)
);

do $$
declare t text;
begin
  foreach t in array array['cse_dealing', 'cse_dealing_as_filed', 'cse_flow_company', 'cse_flow_summary',
                           'cse_flow_dealing', 'cse_flow_actor'] loop
    execute format('alter table models.%I enable row level security', t);
    execute format('create policy web_read on models.%I for select to web_reader using (true)', t);
  end loop;
  -- Only the tables without names are readable by the website's role at all. (Migration 0006 grants every new
  -- models table by default, so the tables with names are revoked explicitly.)
  foreach t in array array['cse_dealing', 'cse_flow_company', 'cse_flow_summary', 'cse_flow_dealing'] loop
    execute format('grant select on models.%I to web_reader', t);
  end loop;
  foreach t in array array['cse_dealing_as_filed', 'cse_flow_actor'] loop
    execute format('revoke all on models.%I from web_reader', t);
  end loop;
end $$;
