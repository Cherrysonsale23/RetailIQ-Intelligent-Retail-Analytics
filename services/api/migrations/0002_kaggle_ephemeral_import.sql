alter table public.datasets alter column storage_key drop not null;
alter table public.datasets add column if not exists source_metadata jsonb not null default '{}'::jsonb;
alter table public.datasets drop constraint if exists datasets_source_type_check;
alter table public.datasets add constraint datasets_source_type_check
  check (source_type in ('upload','connector','replay','kaggle'));

alter table public.dataset_versions alter column raw_storage_key drop not null;
alter table public.processing_jobs add column if not exists source_config jsonb not null default '{}'::jsonb;

create table if not exists public.dataset_analytics_snapshots (
  id uuid primary key default gen_random_uuid(),
  dataset_id uuid not null references public.datasets(id) on delete cascade,
  dataset_version_id uuid not null references public.dataset_versions(id) on delete cascade,
  owner_id uuid not null references auth.users(id) on delete cascade,
  snapshot jsonb not null,
  created_at timestamptz not null default now(),
  unique(dataset_id, dataset_version_id)
);
create index if not exists analytics_snapshots_owner_idx on public.dataset_analytics_snapshots(owner_id, created_at desc);
alter table public.dataset_analytics_snapshots enable row level security;
drop policy if exists "analytics snapshot owner read" on public.dataset_analytics_snapshots;
create policy "analytics snapshot owner read" on public.dataset_analytics_snapshots
  for select to authenticated using (
    owner_id = (select auth.uid()) and
    exists(select 1 from public.datasets d where d.id = dataset_id and d.owner_id = (select auth.uid()))
  );
grant select on public.dataset_analytics_snapshots to authenticated;
grant all on public.dataset_analytics_snapshots to service_role;
