-- 0008 (2026-10-18): what the retail-friendly site needs from the models.
--
-- 1. cse_security_metrics also publishes each share's company name and the CSE's sector label, so pages can show
--    "John Keells Holdings PLC" beside JKH.N0000. Facts only: the latest name and sector the CSE published on or
--    before the run's date.
create table models.cse_security_reference (
  method_version  text             not null,
  symbol          text             not null,
  name            text,
  sector_label    text,                        -- as the CSE's company profile prints it
  last_session    date,                        -- the latest session the share appears in the CSE's security list
  run_id          bigint           not null references models.runs,
  primary key (method_version, symbol)
);
alter table models.cse_security_reference enable row level security;
create policy web_read on models.cse_security_reference for select to web_reader using (true);
grant select on models.cse_security_reference to web_reader;

-- 2. bond_carry also publishes each bond's convexity, so a bond's page can show how its price would respond to a
--    change in yield (duration and convexity together). Empty for versions that do not compute it.
alter table models.bond_carry add column convexity double precision;
