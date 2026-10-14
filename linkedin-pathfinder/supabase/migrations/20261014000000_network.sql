-- Intro Pathfinder: shared connection network.
--
-- Model
--   people   – one row per real person, keyed by LinkedIn profile slug (or name|company as a fallback).
--   profiles – an app user, linked to the `people` row that represents them.
--   edges    – undirected "knows" edges (a < b). `import` edges come from Connections.csv uploads and
--              are shared with everyone; `manual` edges are private notes visible only to their author.
--
-- Privacy
--   Clients can never read other users' edges. Pathfinding and degree calculations run in
--   SECURITY DEFINER functions that return only what the caller needs (the edges on their shortest
--   paths to a target, or their own degree to a person).

create extension if not exists pg_trgm;

create schema if not exists private;

-- ---------------------------------------------------------------- tables

create table if not exists public.people (
  id           uuid primary key default gen_random_uuid(),
  key          text not null unique,
  name         text not null,
  company      text,
  title        text,
  linkedin_url text,
  created_at   timestamptz not null default now()
);
create index if not exists people_name_trgm on public.people using gin (name gin_trgm_ops);
create index if not exists people_company_trgm on public.people using gin (company gin_trgm_ops);

create table if not exists public.profiles (
  id           uuid primary key references auth.users (id) on delete cascade,
  person_id    uuid unique references public.people (id) on delete set null,
  full_name    text,
  linkedin_url text,
  created_at   timestamptz not null default now()
);

create table if not exists public.edges (
  a              uuid not null references public.people (id) on delete cascade,
  b              uuid not null references public.people (id) on delete cascade,
  contributed_by uuid not null references auth.users (id) on delete cascade,
  source         text not null default 'import' check (source in ('import', 'manual')),
  strength       smallint not null default 2 check (strength between 1 and 3),
  created_at     timestamptz not null default now(),
  primary key (a, b, contributed_by),
  check (a < b)
);
create index if not exists edges_b_idx on public.edges (b);
create index if not exists edges_contributor_idx on public.edges (contributed_by);

create table if not exists public.targets (
  user_id    uuid not null default auth.uid() references auth.users (id) on delete cascade,
  person_id  uuid not null references public.people (id) on delete cascade,
  note       text,
  created_at timestamptz not null default now(),
  primary key (user_id, person_id)
);

create table if not exists public.imports (
  id         bigint generated always as identity primary key,
  user_id    uuid not null default auth.uid() references auth.users (id) on delete cascade,
  filename   text,
  row_count  integer not null,
  created_at timestamptz not null default now()
);

-- ---------------------------------------------------------------- row level security

alter table public.people   enable row level security;
alter table public.profiles enable row level security;
alter table public.edges    enable row level security;
alter table public.targets  enable row level security;
alter table public.imports  enable row level security;

drop policy if exists "people are readable by members" on public.people;
create policy "people are readable by members" on public.people
  for select to authenticated using (true);

drop policy if exists "own profile" on public.profiles;
create policy "own profile" on public.profiles
  for select to authenticated using (id = auth.uid());

drop policy if exists "own edges readable" on public.edges;
create policy "own edges readable" on public.edges
  for select to authenticated using (contributed_by = auth.uid());
drop policy if exists "own edges deletable" on public.edges;
create policy "own edges deletable" on public.edges
  for delete to authenticated using (contributed_by = auth.uid());

drop policy if exists "own targets" on public.targets;
create policy "own targets" on public.targets
  for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());

drop policy if exists "own imports" on public.imports;
create policy "own imports" on public.imports
  for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());

-- ---------------------------------------------------------------- helpers (not exposed to the API)

create or replace function private.person_key(p_name text, p_url text, p_company text)
returns text language sql immutable as $$
  select coalesce(
    'li:' || lower((regexp_match(coalesce(p_url, ''), 'linkedin\.com/in/([^/?#]+)', 'i'))[1]),
    'nm:' || lower(regexp_replace(trim(p_name), '\s+', ' ', 'g')) || '|' || lower(trim(coalesce(p_company, '')))
  )
$$;

-- Edges as seen by one user: everyone's imports plus that user's private manual edges, both directions.
create or replace function private.adj(p_uid uuid)
returns table (src uuid, dst uuid, strength smallint) language sql stable as $$
  select e.a, e.b, e.strength from public.edges e where e.source = 'import' or e.contributed_by = p_uid
  union all
  select e.b, e.a, e.strength from public.edges e where e.source = 'import' or e.contributed_by = p_uid
$$;

create or replace function private.me()
returns uuid language sql stable security definer set search_path = '' as $$
  select person_id from public.profiles where id = auth.uid()
$$;

-- Degree (1–3) and mutual count for everyone within three hops of p_me.
create or replace function private.network(p_me uuid, p_uid uuid)
returns table (person_id uuid, degree int, mutuals int) language sql stable as $$
  with a as materialized (select * from private.adj(p_uid)),
  d1 as (select distinct a.dst as id from a where a.src = p_me and a.dst <> p_me),
  d2 as (
    select a.dst as id, count(distinct a.src)::int as mutuals
    from a join d1 on a.src = d1.id
    where a.dst <> p_me and a.dst not in (select id from d1)
    group by a.dst
  ),
  d3 as (
    select a.dst as id, count(distinct a.src)::int as mutuals
    from a join d2 on a.src = d2.id
    where a.dst <> p_me and a.dst not in (select id from d1) and a.dst not in (select id from d2)
    group by a.dst
  )
  select id, 1, 0 from d1
  union all select id, 2, mutuals from d2
  union all select id, 3, mutuals from d3
$$;

create or replace function private.upsert_person(p_name text, p_url text, p_company text, p_title text)
returns uuid language plpgsql security definer set search_path = '' as $$
declare v_id uuid;
begin
  if coalesce(trim(p_name), '') = '' then raise exception 'name is required'; end if;
  insert into public.people (key, name, company, title, linkedin_url)
  values (private.person_key(p_name, p_url, p_company), trim(p_name), nullif(trim(p_company), ''),
          nullif(trim(p_title), ''), nullif(trim(p_url), ''))
  on conflict (key) do update set
    company      = coalesce(public.people.company, excluded.company),
    title        = coalesce(public.people.title, excluded.title),
    linkedin_url = coalesce(public.people.linkedin_url, excluded.linkedin_url)
  returning id into v_id;
  return v_id;
end $$;

-- ---------------------------------------------------------------- API (RPC)

-- Link the signed-in user to their own person node. Matching by LinkedIn URL is what joins
-- your upload to everyone who already has you in their Connections.csv.
create or replace function public.set_my_profile(p_name text, p_linkedin_url text)
returns public.profiles language plpgsql security definer set search_path = '' as $$
declare
  v_person uuid;
  v_row public.profiles;
begin
  if auth.uid() is null then raise exception 'not signed in'; end if;
  if coalesce(p_linkedin_url, '') !~* 'linkedin\.com/in/[^/?#]+' then
    raise exception 'Enter your LinkedIn profile URL (linkedin.com/in/…)';
  end if;
  v_person := private.upsert_person(p_name, p_linkedin_url, null, null);
  if exists (select 1 from public.profiles where person_id = v_person and id <> auth.uid()) then
    raise exception 'That LinkedIn profile is already claimed by another account';
  end if;
  update public.people set name = trim(p_name) where id = v_person;
  insert into public.profiles (id, person_id, full_name, linkedin_url)
  values (auth.uid(), v_person, trim(p_name), trim(p_linkedin_url))
  on conflict (id) do update set person_id = excluded.person_id, full_name = excluded.full_name,
                                 linkedin_url = excluded.linkedin_url
  returning * into v_row;
  return v_row;
end $$;

-- Bulk-add rows from Connections.csv: [{name, url, company, title}, …]. Call in chunks of ~500.
create or replace function public.import_connections(p_rows jsonb)
returns integer language plpgsql security definer set search_path = '' as $$
declare
  v_me uuid := private.me();
  v_count integer;
begin
  if v_me is null then raise exception 'Set your LinkedIn profile before importing'; end if;
  if jsonb_array_length(p_rows) > 2000 then raise exception 'Send at most 2000 rows per call'; end if;

  with rows as (
    select distinct on (private.person_key(r.name, r.url, r.company))
      private.person_key(r.name, r.url, r.company) as key, trim(r.name) as name,
      nullif(trim(r.company), '') as company, nullif(trim(r.title), '') as title, nullif(trim(r.url), '') as url
    from jsonb_to_recordset(p_rows) as r (name text, url text, company text, title text)
    where coalesce(trim(r.name), '') <> ''
  ),
  ups as (
    insert into public.people (key, name, company, title, linkedin_url)
    select key, name, company, title, url from rows
    on conflict (key) do update set
      company      = coalesce(excluded.company, public.people.company),
      title        = coalesce(excluded.title, public.people.title),
      linkedin_url = coalesce(public.people.linkedin_url, excluded.linkedin_url)
    returning id
  ),
  ins as (
    insert into public.edges (a, b, contributed_by, source)
    select least(v_me, id), greatest(v_me, id), auth.uid(), 'import' from ups where id <> v_me
    on conflict do nothing
    returning 1
  )
  select count(*) into v_count from ups;
  return v_count;
end $$;

-- Find or create a person (for targets and manual links that aren't in anyone's upload yet).
create or replace function public.ensure_person(p_name text, p_linkedin_url text default null,
                                                p_company text default null, p_title text default null)
returns uuid language plpgsql security definer set search_path = '' as $$
begin
  if auth.uid() is null then raise exception 'not signed in'; end if;
  return private.upsert_person(p_name, p_linkedin_url, p_company, p_title);
end $$;

-- Private "A knows B" note. Only affects the author's own paths.
create or replace function public.add_link(p_a uuid, p_b uuid, p_strength smallint default 2)
returns void language plpgsql security definer set search_path = '' as $$
begin
  if auth.uid() is null then raise exception 'not signed in'; end if;
  if p_a = p_b then raise exception 'A person cannot know themselves'; end if;
  insert into public.edges (a, b, contributed_by, source, strength)
  values (least(p_a, p_b), greatest(p_a, p_b), auth.uid(), 'manual', p_strength)
  on conflict (a, b, contributed_by) do update set strength = excluded.strength;
end $$;

-- How well you know one of your connections (1 weak … 3 close). Used to prefer warmer intros.
create or replace function public.set_closeness(p_person uuid, p_strength smallint)
returns void language plpgsql security definer set search_path = '' as $$
declare v_me uuid := private.me();
begin
  if v_me is null then raise exception 'Set your LinkedIn profile first'; end if;
  update public.edges set strength = p_strength
  where contributed_by = auth.uid() and a = least(v_me, p_person) and b = greatest(v_me, p_person);
  if not found then
    perform public.add_link(v_me, p_person, p_strength);
  end if;
end $$;

-- Search the directory with your degree to each person. With no query, lists your network.
create or replace function public.search_network(p_query text default null, p_degree int default null,
                                                 p_limit int default 50, p_offset int default 0)
returns table (id uuid, name text, company text, title text, linkedin_url text,
               degree int, mutuals int, closeness smallint, total bigint)
language sql stable security definer set search_path = '' as $$
  with me as (select private.me() as id),
  net as materialized (select n.* from me, private.network(me.id, auth.uid()) n),
  mine as (
    select case when e.a = me.id then e.b else e.a end as id, max(e.strength) as strength
    from public.edges e, me
    where e.contributed_by = auth.uid() and (e.a = me.id or e.b = me.id)
    group by 1
  )
  select p.id, p.name, p.company, p.title, p.linkedin_url, n.degree, n.mutuals,
         case when n.degree = 1 then coalesce(mine.strength, 2)::smallint end,
         count(*) over ()
  from public.people p
  left join net n on n.person_id = p.id
  left join mine on mine.id = p.id
  where p.id is distinct from (select id from me)
    and (nullif(trim(p_query), '') is not null or n.degree is not null)
    and (nullif(trim(p_query), '') is null
         or p.name ilike '%' || trim(p_query) || '%' or p.company ilike '%' || trim(p_query) || '%')
    and (p_degree is null or n.degree = p_degree)
  order by n.degree nulls last, n.mutuals desc nulls last, p.name
  limit least(p_limit, 500) offset p_offset
$$;

-- Every edge that lies on a shortest path from you to the target (a DAG, `hop` = distance of `a`
-- from you). The client enumerates and ranks the routes by warmth.
create or replace function public.path_graph(p_target uuid, p_max_hops int default 4)
returns table (a uuid, b uuid, strength smallint, hop int)
language plpgsql security definer set search_path = '' set client_min_messages = warning as $$
declare
  v_me uuid := private.me();
  v_uid uuid := auth.uid();
  v_level int := 0;
  v_found int;
  v_new int;
begin
  if v_me is null or p_target is null or p_target = v_me then return; end if;

  create temp table if not exists pg_dist (node uuid primary key, d int not null);
  create temp table if not exists pg_keep (node uuid primary key, d int not null);
  truncate pg_dist; truncate pg_keep;
  insert into pg_dist values (v_me, 0);

  -- Forward BFS until the target's level is reached.
  loop
    insert into pg_dist (node, d)
    select distinct x.dst, v_level + 1
    from private.adj(v_uid) x join pg_dist f on f.node = x.src and f.d = v_level
    on conflict (node) do nothing;
    get diagnostics v_new = row_count;
    v_level := v_level + 1;
    select d into v_found from pg_dist where node = p_target;
    exit when v_found is not null or v_new = 0 or v_level >= least(p_max_hops, 6);
  end loop;
  if v_found is null then return; end if;

  -- Walk back from the target keeping only nodes on some shortest path.
  insert into pg_keep values (p_target, v_found);
  for lvl in reverse v_found - 1 .. 0 loop
    insert into pg_keep (node, d)
    select distinct f.node, lvl
    from pg_dist f join private.adj(v_uid) x on x.src = f.node
    join pg_keep k on k.node = x.dst and k.d = lvl + 1
    where f.d = lvl
    on conflict (node) do nothing;
  end loop;

  return query
    select u.node, v.node, max(x.strength)::smallint, u.d
    from pg_keep u
    join private.adj(v_uid) x on x.src = u.node
    join pg_keep v on v.node = x.dst and v.d = u.d + 1
    group by u.node, v.node, u.d
    limit 5000;
end $$;

-- Your ego network for the graph view: you, your 1st-degree connections and your top 2nd-degree people.
create or replace function public.ego_graph(p_limit int default 150)
returns jsonb language sql stable security definer set search_path = '' as $$
  with me as (select private.me() as id),
  net as materialized (select n.* from me, private.network(me.id, auth.uid()) n where n.degree <= 2),
  pick as (
    (select person_id as id, degree from net where degree = 1 limit p_limit)
    union all
    (select person_id, degree from net where degree = 2 order by mutuals desc limit p_limit)
    union all
    select id, 0 from me where id is not null
  ),
  links as (
    select distinct least(x.src, x.dst) as s, greatest(x.src, x.dst) as t
    from private.adj(auth.uid()) x
    join pick a on a.id = x.src join pick b on b.id = x.dst
  )
  select jsonb_build_object(
    'nodes', coalesce((select jsonb_agg(jsonb_build_object('id', p.id, 'name', p.name, 'company', p.company,
                                                           'title', p.title, 'degree', pick.degree))
                       from pick join public.people p on p.id = pick.id), '[]'::jsonb),
    'links', coalesce((select jsonb_agg(jsonb_build_object('source', s, 'target', t)) from links), '[]'::jsonb)
  )
$$;

create or replace function public.network_stats()
returns jsonb language sql stable security definer set search_path = '' as $$
  with me as (select private.me() as id),
  net as (select n.* from me, private.network(me.id, auth.uid()) n)
  select jsonb_build_object(
    'first',   (select count(*) from net where degree = 1),
    'second',  (select count(*) from net where degree = 2),
    'third',   (select count(*) from net where degree = 3),
    'members', (select count(*) from public.profiles where person_id is not null),
    'people',  (select count(*) from public.people),
    'targets', (select count(*) from public.targets where user_id = auth.uid())
  )
$$;

-- Remove everything you contributed (your profile link, uploads, notes and targets).
create or replace function public.reset_my_data()
returns void language plpgsql security definer set search_path = '' as $$
begin
  delete from public.edges where contributed_by = auth.uid();
  delete from public.targets where user_id = auth.uid();
  delete from public.imports where user_id = auth.uid();
  delete from public.profiles where id = auth.uid();
end $$;

-- ---------------------------------------------------------------- grants

revoke all on schema private from public, anon, authenticated;
revoke execute on all functions in schema public from public, anon;
grant execute on function
  public.set_my_profile(text, text),
  public.import_connections(jsonb),
  public.ensure_person(text, text, text, text),
  public.add_link(uuid, uuid, smallint),
  public.set_closeness(uuid, smallint),
  public.search_network(text, int, int, int),
  public.path_graph(uuid, int),
  public.ego_graph(int),
  public.network_stats(),
  public.reset_my_data()
to authenticated;
