-- Persistent control plane for Build Strategy.
-- Run once in Supabase SQL Editor.
-- Keep the storage bucket private.

create table if not exists public.build_jobs (
    id text primary key,
    job_id text not null,
    kind text not null default 'STRATEGY_FINDER',
    version text not null,
    user_key text not null,
    status text not null,
    requested_action text,
    symbols jsonb not null default '[]'::jsonb,
    timeframe text not null,
    history_years integer not null default 1,
    chunk_days integer not null default 30,
    start_date timestamptz not null,
    end_date timestamptz not null,
    current_symbol text,
    current_chunk integer not null default 0,
    total_chunks integer not null default 0,
    progress_percent double precision not null default 0,
    current_stage text,
    worker_id text,
    heartbeat_at timestamptz,
    created_at timestamptz not null default now(),
    started_at timestamptz,
    completed_at timestamptz,
    updated_at timestamptz not null default now(),
    last_error text,
    recovery_count integer not null default 0,
    symbols_progress jsonb not null default '{}'::jsonb,
    result_manifest jsonb not null default '[]'::jsonb
);

create index if not exists idx_build_jobs_user_created on public.build_jobs(user_key, created_at desc);
create index if not exists idx_build_jobs_status_created on public.build_jobs(status, created_at);
create index if not exists idx_build_jobs_heartbeat on public.build_jobs(status, heartbeat_at);

-- Atomic queue claim: safe for multiple workers using FOR UPDATE SKIP LOCKED.
create or replace function public.claim_next_build_job(p_worker_id text)
returns setof public.build_jobs
language plpgsql
security definer
set search_path = public
as $$
begin
    return query
    with candidate as (
        select id
        from public.build_jobs
        where status = 'QUEUED'
          and coalesce(requested_action, '') <> 'STOP'
        order by created_at asc
        for update skip locked
        limit 1
    )
    update public.build_jobs j
       set status = 'RUNNING',
           worker_id = p_worker_id,
           heartbeat_at = now(),
           started_at = coalesce(j.started_at, now()),
           updated_at = now()
      from candidate c
     where j.id = c.id
    returning j.*;
end;
$$;

revoke all on function public.claim_next_build_job(text) from public;
grant execute on function public.claim_next_build_job(text) to service_role;

do $$
begin
    insert into storage.buckets (id, name, public)
    values ('adx-build-data', 'adx-build-data', false)
    on conflict (id) do nothing;
exception when undefined_table then
    null;
end $$;

-- Production worker/UI use the Supabase secret key, so normal table grants/RLS
-- are optional for this server-to-server control plane. Keep the bucket private.

-- Explicit grants for the worker/control-plane service key.
grant select, insert, update on table public.build_jobs to service_role;

-- Requeue jobs whose worker died without a final checkpoint.  The function is
-- intentionally restricted to stale RUNNING rows, preserving all checkpoints.
create or replace function public.requeue_stale_build_jobs(p_stale_minutes integer default 10)
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
    v_count integer := 0;
begin
    update public.build_jobs
       set status = 'QUEUED',
           requested_action = null,
           worker_id = null,
           current_stage = format('Recovered stale worker checkpoint; queued for resume'),
           recovery_count = coalesce(recovery_count, 0) + 1,
           updated_at = now()
     where status = 'RUNNING'
       and heartbeat_at is not null
       and heartbeat_at < now() - make_interval(mins => greatest(2, p_stale_minutes));
    get diagnostics v_count = row_count;
    return v_count;
end;
$$;

grant execute on function public.requeue_stale_build_jobs(integer) to service_role;

-- Idempotent upgrade for existing deployments and Fast Build worker settings.
alter table public.build_jobs add column if not exists calculation_batch_rows integer not null default 5000;
alter table public.build_jobs add column if not exists fast_build_mode boolean not null default false;
alter table public.build_jobs add column if not exists target_candle_rows integer;
alter table public.build_jobs add column if not exists symbol_candle_targets jsonb not null default '{}'::jsonb;
alter table public.build_jobs add column if not exists storage_mode text;
alter table public.build_jobs add column if not exists persistent_storage boolean;
alter table public.build_jobs add column if not exists storage_notice text;
