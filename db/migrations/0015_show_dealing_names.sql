-- 0015 (2026-10-19): show directors' and accounts' names on the site (the owner's decision, decision 0021).
--
-- Migration 0014 kept the two tables that hold names unreadable by the website's role, pending a lawyer's view. The
-- owner decided the names are the point of the disclosures and should be shown; nothing is public before the
-- lawyer's review of the whole site (roadmap item 4), which now includes this. The read policy already exists.
grant select on models.cse_dealing_as_filed to web_reader;
grant select on models.cse_flow_actor to web_reader;
