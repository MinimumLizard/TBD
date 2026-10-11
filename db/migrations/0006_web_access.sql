-- 0006: how the website reads the database (docs/architecture.md §8, decision 0016).
--
-- First line of defence: web/lib/entitlements.ts decides, on the server, what each visitor may see.
-- Second line, here:
--   * The website connects as `web_reader`, which can only SELECT, and only from the models schema (pre-computed
--     outputs). It cannot read the raw facts, the run logs or anything in ops, and it cannot write anything.
--   * Row-level security is switched on for every table in every platform schema, with no policy except the
--     web_reader read policy on model outputs. Any other role that is not the tables' owner (for example the
--     anon / authenticated roles a Supabase project gives the browser) therefore reads nothing at all, even if
--     a schema is ever exposed by mistake. The owner (the jobs' own login) is unaffected.
--
-- The role is created without a login. To use it, the owner gives it one, once, outside git:
--   alter role web_reader with login password '<a long random password>';
-- and puts that connection string in Vercel as DATABASE_URL (docs/phase4-verification.md).

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'web_reader') then
    create role web_reader nologin;
  end if;
end $$;

grant usage on schema models to web_reader;
grant select on all tables in schema models to web_reader;
revoke select on models.runs, models.revisions from web_reader;     -- bookkeeping: the website has no use for it
alter default privileges in schema models grant select on tables to web_reader;

do $$
declare r record;
begin
  for r in select schemaname, tablename from pg_tables where schemaname in ('ops', 'bonds', 'cse', 'models') loop
    execute format('alter table %I.%I enable row level security', r.schemaname, r.tablename);
  end loop;
  for r in select tablename from pg_tables where schemaname = 'models' loop
    execute format('create policy web_read on models.%I for select to web_reader using (true)', r.tablename);
  end loop;
end $$;
