-- 0007: fixes from the 2026-10-11 audit.
--
-- 1. Auction "current" views: the same auction file is sometimes listed under two URLs. After a parser upgrade
--    re-reads only one of them, the old views returned the file's rows twice (once per parser version). Each file
--    now contributes the rows of its newest successful parse only.
create or replace view bonds.auction_results_current as
select a.* from bonds.auction_results a
join (select distinct on (raw_sha256) raw_sha256, parser_version from bonds.files_latest_parse
      where kind = 'bond_auction' order by raw_sha256, parser_version desc) f
  on f.raw_sha256 = a.raw_sha256 and f.parser_version = a.parser_version;

create or replace view bonds.auction_announcements_current as
select a.* from bonds.auction_announcements a
join (select distinct on (raw_sha256) raw_sha256, parser_version from bonds.files_latest_parse
      where kind = 'bond_issuance' order by raw_sha256, parser_version desc) f
  on f.raw_sha256 = a.raw_sha256 and f.parser_version = a.parser_version;

-- 2. Outputs the owner has not published (config/entitlements.yaml, unpublished_outputs) are not readable by the
--    website's login at all, so hiding them does not rest on the application alone. A test checks this list
--    against config/entitlements.yaml.
revoke select on models.model_stats from web_reader;

-- 3. A website query can never run for long, whatever goes wrong.
alter role web_reader set statement_timeout = '10s';
