-- 0016 (2026-10-20): money flows with the owner's aliases and ownership groups; the portfolio lab (Phase 3b).
--
-- 1. Money flows (cse_flows 1.0.0, completed in place before its first production run, decision 0015 rule 11):
--    models.cse_flow_dealing.own_group   the account that dealt is in the same ownership group as the company whose
--                                        shares it dealt in (cse_ownership's groups as at the dealing date)
--    models.cse_flow_actor.actor_group   the name of the account's ownership group (the account's own name when it
--                                        heads no group)

alter table models.cse_flow_dealing add column if not exists own_group boolean not null default false;
alter table models.cse_flow_actor add column if not exists actor_group text;
