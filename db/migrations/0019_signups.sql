-- 0019 (2026-11-13): signing up with an e-mail address (decision 0025; docs/plan-janu-review.md §5).
--
-- After a starting path, a visitor may leave an e-mail address so that an account can be opened for it when sign-ins
-- open, and may ask for the weekly summary. Accounts and an e-mail service do not exist yet (decision 0016), so a
-- sign-up is stored as 'pending': nothing is sent to an address until its owner has confirmed it through a link
-- (double opt-in), which the account system will do.
--
-- As with feedback (migration 0012), the website stays read-only towards everything else. It cannot read this table
-- and cannot insert into it directly: it can only call community.submit_signup(), which checks every field and limits
-- how often one sender can write. Only the owner's login reads it, with `python -m data_platform.jobs.signups`.
--
-- Personal data (Sri Lanka's Personal Data Protection Act, No. 9 of 2022): the e-mail address is personal data. It is
-- kept with the consent wording the visitor ticked (consent_version) and the time; it is used only to open the
-- account and, where asked, to send the weekly summary; an address is deleted on request with the signups job. The
-- sender's network address is never stored: only a keyed hash, for the hourly limit, cleared after seven days.
create table community.signups (
  signup_id        bigint generated always as identity primary key,
  email            text        not null unique
                               check (email = lower(email) and char_length(email) <= 254
                                      and email ~ '^[^[:space:]@<>"'',;:\\]+@[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$'),
  starting_type    text        check (starting_type ~ '^[a-z]{1,20}$'),      -- the starting path the visitor came from
  starting_answer  text        check (starting_answer ~ '^[a-z]{1,20}$'),
  wants_weekly     boolean     not null default false,
  consent_version  text        not null check (consent_version ~ '^\d{4}-\d{2}-\d{2}$'),
  consented_at     timestamptz not null default now(),
  status           text        not null default 'pending' check (status in ('pending', 'confirmed', 'unsubscribed')),
  confirmed_at     timestamptz,
  client_key       text        check (client_key ~ '^[0-9a-f]{32}$'),
  check ((starting_type is null) = (starting_answer is null))
);
create index signups_sender_recent on community.signups (client_key, consented_at) where client_key is not null;
alter table community.signups enable row level security;      -- no policy: no role but the owner reads a row

-- Returns 'ok', 'invalid' (a field failed its check; nothing stored) or 'limited' (too many from this sender, or
-- from everyone, in the last hour; nothing stored). An address already on the list also returns 'ok', so the answer
-- never tells anyone whether an address has signed up; its choices are updated, and an unsubscribed address that
-- signs up again is pending again.
create function community.submit_signup(p_email text, p_type text, p_answer text, p_weekly boolean,
                                        p_consent_version text, p_client_key text)
returns text
language plpgsql
security definer
set search_path = pg_catalog, community
as $$
declare
  v_email text := lower(regexp_replace(coalesce(p_email, ''), '^\s+|\s+$', '', 'g'));
  v_sender int;
  v_everyone int;
begin
  if char_length(v_email) > 254
     or v_email !~ '^[^[:space:]@<>"'',;:\\]+@[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$'
     or (p_type is null) <> (p_answer is null)
     or (p_type is not null and (p_type !~ '^[a-z]{1,20}$' or p_answer !~ '^[a-z]{1,20}$'))
     or p_weekly is null
     or p_consent_version is null or p_consent_version !~ '^\d{4}-\d{2}-\d{2}$'
     or p_client_key is null or p_client_key !~ '^[0-9a-f]{32}$' then
    return 'invalid';
  end if;

  select count(*) into v_sender from community.signups
   where client_key = p_client_key and consented_at > now() - interval '1 hour';
  select count(*) into v_everyone from community.signups where consented_at > now() - interval '1 hour';
  if v_sender >= 5 or v_everyone >= 500 then
    return 'limited';
  end if;

  insert into community.signups (email, starting_type, starting_answer, wants_weekly, consent_version, client_key)
  values (v_email, p_type, p_answer, p_weekly, p_consent_version, p_client_key)
  on conflict (email) do update
     set starting_type = coalesce(excluded.starting_type, signups.starting_type),
         starting_answer = coalesce(excluded.starting_answer, signups.starting_answer),
         wants_weekly = excluded.wants_weekly,
         consent_version = excluded.consent_version,
         consented_at = now(),
         client_key = excluded.client_key,
         status = case when signups.status = 'unsubscribed' then 'pending' else signups.status end,
         confirmed_at = case when signups.status = 'unsubscribed' then null else signups.confirmed_at end;

  -- the sender's key is needed only for the hourly limit; forget it after seven days
  update community.signups set client_key = null
   where client_key is not null and consented_at < now() - interval '7 days';
  return 'ok';
end $$;

revoke all on function community.submit_signup(text, text, text, boolean, text, text) from public;
grant execute on function community.submit_signup(text, text, text, boolean, text, text) to web_reader;
