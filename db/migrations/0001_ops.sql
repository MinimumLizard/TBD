-- 0001: the platform's own bookkeeping: run log, raw archive catalogue, conflicts, gap checks.
--
-- Migrations are numbered, applied in order, and never edited after they have been applied anywhere
-- (data_platform.core.migrate refuses to run if an applied file's contents changed). To change the schema,
-- add a new numbered file.

create schema if not exists ops;

-- Append-only guard. Attached to every table that records a fact or a raw fetch: any UPDATE or DELETE fails.
-- History is corrected by inserting newer rows, never by editing old ones (architecture §5, hard rule 2).
create or replace function ops.forbid_change() returns trigger
language plpgsql as $$
begin
  raise exception 'table %.% is append-only: % is not allowed (insert a newer row instead)',
    tg_table_schema, tg_table_name, tg_op;
end;
$$;

-- One row per collector or job run. This is the only ops table that is updated (to close the run).
create table ops.collector_runs (
  run_id        bigserial primary key,
  source_id     text        not null,
  job           text        not null,
  started_at    timestamptz not null default now(),
  finished_at   timestamptz,
  status        text        not null default 'running'
                check (status in ('running', 'ok', 'no_new_data', 'failed', 'skipped')),
  fetches       integer     not null default 0,
  rows_added    integer     not null default 0,
  message       text,
  code_version  text
);
create index on ops.collector_runs (source_id, started_at);

-- Every distinct piece of content ever archived, named by its SHA-256 fingerprint.
create table ops.raw_objects (
  sha256           text        primary key check (sha256 ~ '^[0-9a-f]{64}$'),
  bytes            bigint      not null,
  content_type     text,
  ext              text        not null,
  storage_key      text        not null,
  first_stored_at  timestamptz not null default now()
);
create trigger raw_objects_append_only before update or delete on ops.raw_objects
  for each row execute function ops.forbid_change();

-- Every request made (or migrated from the old repos): what was asked, when, and which content came back.
create table ops.raw_fetches (
  fetch_id     bigserial   primary key,
  source_id    text        not null,
  run_id       bigint      references ops.collector_runs,
  method       text        not null,
  url          text        not null,
  params       jsonb       not null default '{}'::jsonb,
  http_status  integer     not null,
  fetched_at   timestamptz not null,
  sha256       text        not null references ops.raw_objects,
  origin       text        not null default 'live'
               check (origin in ('live', 'migration', 're-download')),
  note         text
);
create index on ops.raw_fetches (source_id, fetched_at);
create index on ops.raw_fetches (sha256);
create trigger raw_fetches_append_only before update or delete on ops.raw_fetches
  for each row execute function ops.forbid_change();

-- When a re-fetch disagrees with a fact already stored under the same key, the stored fact is kept and the
-- disagreement is recorded here for a human to look at. Nothing is silently overwritten or silently dropped.
create table ops.value_conflicts (
  conflict_id   bigserial   primary key,
  table_name    text        not null,
  key           jsonb       not null,
  stored        jsonb       not null,
  incoming      jsonb       not null,
  fetch_id      bigint      references ops.raw_fetches,
  detected_at   timestamptz not null default now()
);

-- Results of the daily gap check: one row per dataset and expected day that is missing or late.
create table ops.gap_checks (
  checked_at   timestamptz not null default now(),
  dataset      text        not null,
  day          date        not null,
  status       text        not null check (status in ('missing', 'late', 'filled')),
  detail       text
);
create index on ops.gap_checks (dataset, day);
