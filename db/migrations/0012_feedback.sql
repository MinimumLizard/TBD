-- 0012 (2026-10-18): visitors' feedback (docs/plan-retail-features.md §3, option A: users talk to us, never to
-- each other; nothing they write is shown on the site).
--
-- The website stays read-only towards everything else. It cannot read this table and cannot insert into it
-- directly: it can only call community.submit_feedback(), which checks every field, limits how often one sender
-- can write, and stores the row. Only the owner's own login (the jobs' role) reads feedback, with
-- `python -m data_platform.jobs.feedback`.
--
-- Personal data (Sri Lanka's Personal Data Protection Act, No. 9 of 2022): the form asks for no name or e-mail. The
-- only thing kept about the sender is `client_key`, a keyed hash of their network address made by the website
-- (the address itself is never stored), used only to limit how often one sender can write, and cleared after seven
-- days. A message can be deleted on request with the feedback job.
create schema if not exists community;

create table community.feedback (
  feedback_id  bigint generated always as identity primary key,
  received_at  timestamptz not null default now(),
  page         text        not null check (page ~ '^/[A-Za-z0-9/_.:%~-]{0,200}$'),
  kind         text        not null check (kind in ('page_vote', 'message')),
  useful       boolean,                                    -- page_vote: "was this page useful?"
  topic        text        check (topic in ('data_error', 'unclear', 'idea', 'other')),
  message      text        check (char_length(message) between 3 and 2000),
  viewer_tier  text        check (viewer_tier in ('free', 'plus', 'pro', 'professional')),
  client_key   text        check (client_key ~ '^[0-9a-f]{32}$'),
  status       text        not null default 'new' check (status in ('new', 'read', 'actioned', 'spam')),
  reviewed_at  timestamptz,
  check ((kind = 'page_vote' and useful is not null and message is null and topic is null)
      or (kind = 'message' and message is not null and topic is not null and useful is null))
);
create index feedback_sender_recent on community.feedback (client_key, received_at) where client_key is not null;
create index feedback_received on community.feedback (received_at);
alter table community.feedback enable row level security;     -- no policy: no role but the owner reads a row

-- Returns 'ok', 'invalid' (a field failed its check; nothing stored) or 'limited' (too many from this sender, or
-- from everyone, in the last hour; nothing stored).
create function community.submit_feedback(p_page text, p_kind text, p_useful boolean, p_topic text, p_message text,
                                          p_viewer_tier text, p_client_key text)
returns text
language plpgsql
security definer
set search_path = pg_catalog, community
as $$
declare
  v_message text := nullif(regexp_replace(coalesce(p_message, ''), '^\s+|\s+$', '', 'g'), '');
  v_sender  int;
  v_sender_messages int;
  v_everyone int;
begin
  if p_page is null or p_page !~ '^/[A-Za-z0-9/_.:%~-]{0,200}$'
     or p_kind not in ('page_vote', 'message')
     or (p_viewer_tier is not null and p_viewer_tier not in ('free', 'plus', 'pro', 'professional'))
     or p_client_key is null or p_client_key !~ '^[0-9a-f]{32}$'
     or (p_kind = 'page_vote' and (p_useful is null or v_message is not null or p_topic is not null))
     or (p_kind = 'message' and (p_useful is not null or p_topic is null
                                 or p_topic not in ('data_error', 'unclear', 'idea', 'other')
                                 or v_message is null or char_length(v_message) not between 3 and 2000)) then
    return 'invalid';
  end if;

  select count(*), count(*) filter (where kind = 'message') into v_sender, v_sender_messages
    from community.feedback where client_key = p_client_key and received_at > now() - interval '1 hour';
  select count(*) into v_everyone from community.feedback where received_at > now() - interval '1 hour';
  if v_sender >= 30 or (p_kind = 'message' and v_sender_messages >= 5) or v_everyone >= 2000 then
    return 'limited';
  end if;

  insert into community.feedback (page, kind, useful, topic, message, viewer_tier, client_key)
  values (p_page, p_kind, p_useful, p_topic, v_message, p_viewer_tier, p_client_key);

  -- the sender's key is needed only for the hourly limit; forget it after seven days
  update community.feedback set client_key = null
   where client_key is not null and received_at < now() - interval '7 days';
  return 'ok';
end $$;

revoke all on function community.submit_feedback(text, text, boolean, text, text, text, text) from public;
grant usage on schema community to web_reader;
grant execute on function community.submit_feedback(text, text, boolean, text, text, text, text) to web_reader;
