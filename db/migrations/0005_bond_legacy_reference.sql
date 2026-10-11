-- 0005: the old bond tool's own list of bonds, kept as a fact (decision 0015).
--
-- The old tool learned some of its bond reference data (series labels, coupons, two synthetic keys) from earlier
-- versions of its own parsers; those values survive only in its database, because its bond table only ever filled
-- in blanks and never forgot. No PDMO file still teaches them to the current parsers. Version 1 of the
-- bond_identity model therefore starts from this list, exactly as the old tool did, and reproduces every quote it
-- resolved. Loaded once, by the history migration, from the archived database file (source_sha256).

create table bonds.legacy_reference (
  source_sha256   text        not null references ops.raw_objects,   -- the archived old database file
  isin            text        not null,
  coupon_pct      double precision,
  maturity_date   date,
  tenor_years     integer,
  series_label    text,
  issue_date      date,
  coupon_dates    text,
  first_seen_date date,
  notes           text,
  ingested_at     timestamptz not null default now(),
  primary key (source_sha256, isin)
);
create trigger legacy_reference_append_only before update or delete on bonds.legacy_reference
  for each row execute function ops.forbid_change();
