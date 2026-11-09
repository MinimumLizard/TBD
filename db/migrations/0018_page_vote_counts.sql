-- "Was this useful?" counts (Janu's review, 2026-11-09; docs/plan-janu-review.md): the site may show how many readers
-- found a guide useful. Two changes to the feedback of migration 0012:
--   1. one vote per sender and page: a sender's later vote on the same page, while the sender's key is still kept
--      (seven days), replaces the earlier one, so a count cannot be pushed up by repeating a vote;
--   2. community.page_votes(page): the totals for one page, for the website's role. It returns two numbers and nothing
--      about any visitor; the table itself stays unreadable by the website.
-- submit_feedback is otherwise exactly migration 0012's: the same checks, limits and forgetting.

create or replace function community.submit_feedback(p_page text, p_kind text, p_useful boolean, p_topic text,
                                                     p_message text, p_viewer_tier text, p_client_key text)
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
  v_previous bigint;
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

  if p_kind = 'page_vote' then                  -- new: one vote per sender and page (it replaces the earlier one)
    select feedback_id into v_previous from community.feedback
     where kind = 'page_vote' and page = p_page and client_key = p_client_key
     order by received_at desc limit 1;
  end if;
  if v_previous is not null then
    update community.feedback set useful = p_useful, viewer_tier = p_viewer_tier, received_at = now()
     where feedback_id = v_previous;
  else
    insert into community.feedback (page, kind, useful, topic, message, viewer_tier, client_key)
    values (p_page, p_kind, p_useful, p_topic, v_message, p_viewer_tier, p_client_key);
  end if;

  -- the sender's key is needed only for the hourly limit and the one-vote rule; forget it after seven days
  update community.feedback set client_key = null
   where client_key is not null and received_at < now() - interval '7 days';
  return 'ok';
end $$;

-- The totals of "useful" and "not useful" votes for one page: no rows, no keys, nothing about a visitor.
create function community.page_votes(p_page text)
returns table (useful bigint, not_useful bigint)
language sql
stable
security definer
set search_path = pg_catalog, community
as $$
  select count(*) filter (where useful), count(*) filter (where not useful)
    from community.feedback where kind = 'page_vote' and page = p_page;
$$;

revoke all on function community.page_votes(text) from public;
grant execute on function community.page_votes(text) to web_reader;
