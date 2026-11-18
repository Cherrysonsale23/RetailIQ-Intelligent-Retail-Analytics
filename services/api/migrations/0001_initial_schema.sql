create extension if not exists pgcrypto;

create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  display_name text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create or replace function public.handle_new_user()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  insert into public.profiles (id, display_name)
  values (new.id, coalesce(new.raw_user_meta_data ->> 'name', new.raw_user_meta_data ->> 'full_name'))
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users
for each row execute procedure public.handle_new_user();

create table if not exists public.datasets (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  original_filename text not null,
  storage_key text not null unique,
  byte_size bigint not null check (byte_size >= 0),
  content_sha256 text,
  source_type text not null default 'upload' check (source_type in ('upload','connector','replay')),
  status text not null default 'uploading' check (status in ('uploading','uploaded','queued','processing','ready','failed')),
  detected_schema jsonb not null default '[]'::jsonb,
  preview_data jsonb not null default '{"columns":[],"rows":[]}'::jsonb,
  row_count bigint,
  column_count integer,
  active_version integer not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists datasets_owner_created_idx on public.datasets(owner_id, created_at desc);

create table if not exists public.dataset_versions (
  id uuid primary key default gen_random_uuid(),
  dataset_id uuid not null references public.datasets(id) on delete cascade,
  version_number integer not null check (version_number > 0),
  raw_storage_key text not null,
  processed_storage_key text,
  schema_snapshot jsonb not null default '[]'::jsonb,
  row_count bigint,
  transformation_config jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique(dataset_id, version_number)
);

create table if not exists public.processing_jobs (
  id uuid primary key default gen_random_uuid(),
  dataset_id uuid not null references public.datasets(id) on delete cascade,
  owner_id uuid not null references auth.users(id) on delete cascade,
  version_number integer,
  status text not null default 'queued' check (status in ('queued','running','succeeded','failed','cancelled')),
  stage text not null default 'extract',
  progress integer not null default 0 check(progress between 0 and 100),
  error_code text,
  error_message text,
  retry_count integer not null default 0,
  started_at timestamptz,
  finished_at timestamptz,
  created_at timestamptz not null default now()
);
create index if not exists processing_jobs_owner_idx on public.processing_jobs(owner_id, created_at desc);
create unique index if not exists one_active_processing_job_per_dataset
  on public.processing_jobs(dataset_id) where status in ('queued','running');

create or replace function public.claim_next_processing_job()
returns setof public.processing_jobs
language sql
security definer
set search_path = ''
as $$
  with candidate as (
    select id from public.processing_jobs
    where status = 'queued'
    order by created_at asc
    for update skip locked
    limit 1
  )
  update public.processing_jobs as job
  set status = 'running', stage = 'extract', progress = 5, started_at = now()
  from candidate
  where job.id = candidate.id
  returning job.*;
$$;
revoke all on function public.claim_next_processing_job() from public, anon, authenticated;
grant execute on function public.claim_next_processing_job() to service_role;

create table if not exists public.processing_logs (
  id uuid primary key default gen_random_uuid(),
  job_id uuid not null references public.processing_jobs(id) on delete cascade,
  severity text not null default 'info' check(severity in ('debug','info','warning','error')),
  stage text not null,
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.data_quality_reports (
  id uuid primary key default gen_random_uuid(),
  dataset_version_id uuid not null references public.dataset_versions(id) on delete cascade,
  summary jsonb not null default '{}'::jsonb,
  column_report jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.analysis_runs (
  id uuid primary key default gen_random_uuid(),
  dataset_id uuid not null references public.datasets(id) on delete cascade,
  owner_id uuid not null references auth.users(id) on delete cascade,
  dataset_version_id uuid references public.dataset_versions(id) on delete set null,
  question text,
  plan jsonb not null default '{}'::jsonb,
  method_version text,
  status text not null default 'completed' check(status in ('queued','running','completed','failed')),
  result jsonb not null default '{}'::jsonb,
  evidence_index jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.agent_conversations (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade,
  dataset_id uuid references public.datasets(id) on delete set null,
  title text not null default 'New analysis',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create table if not exists public.agent_messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references public.agent_conversations(id) on delete cascade,
  owner_id uuid not null references auth.users(id) on delete cascade,
  role text not null check(role in ('user','assistant','tool')),
  content text not null,
  tool_reference jsonb,
  evidence_ids jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now()
);

alter table public.profiles enable row level security;
alter table public.datasets enable row level security;
alter table public.dataset_versions enable row level security;
alter table public.processing_jobs enable row level security;
alter table public.processing_logs enable row level security;
alter table public.data_quality_reports enable row level security;
alter table public.analysis_runs enable row level security;
alter table public.agent_conversations enable row level security;
alter table public.agent_messages enable row level security;

create policy "profile owner can read" on public.profiles for select to authenticated using (id = (select auth.uid()));
create policy "profile owner can update" on public.profiles for update to authenticated using (id = (select auth.uid())) with check (id = (select auth.uid()));
create policy "dataset owner access" on public.datasets for all to authenticated using (owner_id = (select auth.uid())) with check (owner_id = (select auth.uid()));
create policy "dataset version owner read" on public.dataset_versions for select to authenticated using (exists(select 1 from public.datasets d where d.id=dataset_id and d.owner_id=(select auth.uid())));
create policy "job owner read" on public.processing_jobs for select to authenticated using (owner_id = (select auth.uid()));
create policy "job owner insert" on public.processing_jobs for insert to authenticated with check (owner_id = (select auth.uid()) and exists(select 1 from public.datasets d where d.id=dataset_id and d.owner_id=(select auth.uid())));
create policy "processing logs owner read" on public.processing_logs for select to authenticated using (exists(select 1 from public.processing_jobs j where j.id=job_id and j.owner_id=(select auth.uid())));
create policy "quality report owner read" on public.data_quality_reports for select to authenticated using (exists(select 1 from public.dataset_versions v join public.datasets d on d.id=v.dataset_id where v.id=dataset_version_id and d.owner_id=(select auth.uid())));
create policy "analysis owner access" on public.analysis_runs for all to authenticated using (owner_id=(select auth.uid())) with check (owner_id=(select auth.uid()) and exists(select 1 from public.datasets d where d.id=dataset_id and d.owner_id=(select auth.uid())));
create policy "conversation owner access" on public.agent_conversations for all to authenticated using (owner_id=(select auth.uid()) and (dataset_id is null or exists(select 1 from public.datasets d where d.id=dataset_id and d.owner_id=(select auth.uid())))) with check (owner_id=(select auth.uid()) and (dataset_id is null or exists(select 1 from public.datasets d where d.id=dataset_id and d.owner_id=(select auth.uid()))));
create policy "message owner access" on public.agent_messages for all to authenticated using (owner_id=(select auth.uid()) and exists(select 1 from public.agent_conversations c where c.id=conversation_id and c.owner_id=(select auth.uid()))) with check (owner_id=(select auth.uid()) and exists(select 1 from public.agent_conversations c where c.id=conversation_id and c.owner_id=(select auth.uid())));

grant usage on schema public to authenticated, service_role;
grant select, update on public.profiles to authenticated;
grant all on public.profiles, public.datasets, public.dataset_versions, public.processing_jobs,
  public.processing_logs, public.data_quality_reports, public.analysis_runs,
  public.agent_conversations, public.agent_messages to service_role;
grant select, insert, update, delete on public.datasets to authenticated;
grant select on public.dataset_versions, public.processing_logs, public.data_quality_reports to authenticated;
grant select, insert on public.processing_jobs to authenticated;
grant select, insert, update, delete on public.analysis_runs, public.agent_conversations, public.agent_messages to authenticated;

insert into storage.buckets(id, name, public, file_size_limit, allowed_mime_types)
values ('private-datasets','private-datasets',false,8589934592,array['text/csv','application/vnd.ms-excel','application/octet-stream','application/vnd.apache.parquet'])
on conflict (id) do update set public=false;
create policy "dataset storage owner access" on storage.objects for all to authenticated
using (bucket_id='private-datasets' and (storage.foldername(name))[1]=(select auth.uid())::text)
with check (bucket_id='private-datasets' and (storage.foldername(name))[1]=(select auth.uid())::text);
