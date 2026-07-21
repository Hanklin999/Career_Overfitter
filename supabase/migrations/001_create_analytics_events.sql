-- ============================================================
-- 001_create_analytics_events.sql
-- Data Matters 匿名使用分析事件表
-- 原則：匿名、insert-only、RLS 強制、不存個資與完整作答
-- 在 Supabase Dashboard → SQL Editor 直接執行本檔即可
-- ============================================================

create table if not exists public.analytics_events (
  id                  uuid primary key default gen_random_uuid(),
  occurred_at         timestamptz not null default now(),
  session_id          uuid not null,
  event_name          text not null,
  page_path           text,
  app_version         text not null default 'v1',
  device_type         text,
  referrer_domain     text,
  utm_source          text,
  utm_medium          text,
  utm_campaign        text,
  quiz_step           smallint,
  role_id             text,
  recommendation_rank smallint,
  domain_id           text,
  industry_id         text,
  job_id              text,
  company_name        text,
  accuracy_rating     smallint,
  clarity_before      smallint,
  clarity_after       smallint,
  preferred_role_id   text,
  properties          jsonb not null default '{}'::jsonb,

  constraint chk_event_name_len   check (length(event_name) between 1 and 80),
  constraint chk_page_path_len    check (page_path is null or length(page_path) <= 500),
  constraint chk_quiz_step        check (quiz_step is null or quiz_step in (1, 2, 3)),
  constraint chk_rec_rank         check (recommendation_rank is null or recommendation_rank in (1, 2, 3)),
  constraint chk_accuracy         check (accuracy_rating is null or accuracy_rating between 1 and 5),
  constraint chk_clarity_before   check (clarity_before is null or clarity_before between 1 and 5),
  constraint chk_clarity_after    check (clarity_after is null or clarity_after between 1 and 5),
  -- properties 大小控管（前端 serializer 另有欄位 allowlist 與字串長度限制）
  constraint chk_properties_size  check (length(properties::text) <= 4000),
  constraint chk_device_type      check (device_type is null or device_type in ('mobile','tablet','desktop','unknown')),
  -- 事件名稱允許清單（新增事件時需同步更新此 constraint、policy 與前端 allowlist）
  constraint chk_event_allowlist  check (event_name in (
    'landing_viewed','quiz_started','quiz_step_viewed','quiz_step_completed',
    'quiz_completed','result_viewed','role_opened','domain_selected',
    'industry_selected','job_viewed','external_job_clicked','quiz_restarted',
    'result_feedback_viewed','result_feedback_submitted'
  ))
);

comment on table public.analytics_events is
  'Data Matters 匿名產品使用事件。無個資、無完整作答內容；anon 僅可 INSERT。';

create index if not exists idx_ae_occurred_at   on public.analytics_events (occurred_at desc);
create index if not exists idx_ae_event_time    on public.analytics_events (event_name, occurred_at desc);
create index if not exists idx_ae_session_time  on public.analytics_events (session_id, occurred_at);
create index if not exists idx_ae_role_time     on public.analytics_events (role_id, occurred_at);
create index if not exists idx_ae_domain_time   on public.analytics_events (domain_id, occurred_at);

-- ── Row Level Security ──────────────────────────────────────
alter table public.analytics_events enable row level security;

-- 匿名與登入使用者：只允許 INSERT。occurred_at 必須採用 DB default（= now()）；
-- 前端 payload 完全省略 occurred_at，任意指定的時間會被 WITH CHECK 擋下。
drop policy if exists analytics_events_insert_only on public.analytics_events;
create policy analytics_events_insert_only
  on public.analytics_events
  for insert
  to anon, authenticated
  with check (
    session_id is not null
    and length(event_name) > 0
    and event_name in (
      'landing_viewed','quiz_started','quiz_step_viewed','quiz_step_completed',
      'quiz_completed','result_viewed','role_opened','domain_selected',
      'industry_selected','job_viewed','external_job_clicked','quiz_restarted',
      'result_feedback_viewed','result_feedback_submitted'
    )
    and occurred_at = now()
  );

-- 不建立 anon/authenticated 的 SELECT / UPDATE / DELETE policy（預設即拒絕），
-- 並明確收回權限，雙重保險：
grant insert on table public.analytics_events to anon, authenticated;
revoke select, update, delete on table public.analytics_events from anon, authenticated;
