-- ============================================================
-- analytics_queries.sql — Data Matters 分析查詢集
-- 在 Supabase SQL Editor 直接執行；所有 funnel 以 unique session 為單位。
-- 預設排除非 production 資料（properties->>'environment'）。
-- ============================================================

-- 共用基底：production 事件
-- （每段查詢自帶此 CTE，方便單獨複製執行）

-- 1) 每日 unique sessions（近 30 天）
with prod as (
  select * from analytics_events
  where coalesce(properties->>'environment','production') = 'production'
)
select occurred_at::date as day, count(distinct session_id) as sessions
from prod
where occurred_at >= now() - interval '30 days'
group by 1 order by 1 desc;

-- 2) Landing → Quiz Start 轉換率
with prod as (
  select * from analytics_events
  where coalesce(properties->>'environment','production') = 'production'
), s as (
  select
    count(distinct session_id) filter (where event_name = 'landing_viewed') as landed,
    count(distinct session_id) filter (where event_name = 'quiz_started')  as started
  from prod
)
select landed, started,
       round(100.0 * started / nullif(landed, 0), 1) as start_rate_pct
from s;

-- 3) Quiz Started → Quiz Completed 轉換率
with prod as (
  select * from analytics_events
  where coalesce(properties->>'environment','production') = 'production'
), s as (
  select
    count(distinct session_id) filter (where event_name = 'quiz_started')   as started,
    count(distinct session_id) filter (where event_name = 'quiz_completed') as completed
  from prod
)
select started, completed,
       round(100.0 * completed / nullif(started, 0), 1) as completion_rate_pct
from s;

-- 4) 各測驗站 unique sessions 與 drop-off
with prod as (
  select * from analytics_events
  where coalesce(properties->>'environment','production') = 'production'
), step_sessions as (
  select quiz_step, count(distinct session_id) as sessions
  from prod
  where event_name = 'quiz_step_completed' and quiz_step is not null
  group by quiz_step
)
select quiz_step, sessions,
       sessions - lead(sessions) over (order by quiz_step) as drop_to_next,
       round(100.0 * lead(sessions) over (order by quiz_step) / nullif(sessions,0), 1) as next_step_rate_pct
from step_sessions
order by quiz_step;

-- 5) Result View → Role Open rate
with prod as (
  select * from analytics_events
  where coalesce(properties->>'environment','production') = 'production'
), s as (
  select
    count(distinct session_id) filter (where event_name = 'result_viewed') as viewed,
    count(distinct session_id) filter (where event_name = 'role_opened' and (properties->>'source') = 'result_page') as opened
  from prod
)
select viewed, opened, round(100.0 * opened / nullif(viewed,0), 1) as role_open_rate_pct from s;

-- 6) Result View → Domain Select rate
with prod as (
  select * from analytics_events
  where coalesce(properties->>'environment','production') = 'production'
), s as (
  select
    count(distinct session_id) filter (where event_name = 'result_viewed')   as viewed,
    count(distinct session_id) filter (where event_name = 'domain_selected' and (properties->>'selection_action') = 'select') as selected
  from prod
)
select viewed, selected, round(100.0 * selected / nullif(viewed,0), 1) as domain_select_rate_pct from s;

-- 7) Result View → Job View rate
with prod as (
  select * from analytics_events
  where coalesce(properties->>'environment','production') = 'production'
), s as (
  select
    count(distinct session_id) filter (where event_name = 'result_viewed') as viewed,
    count(distinct session_id) filter (where event_name = 'job_viewed')    as job_viewed
  from prod
)
select viewed, job_viewed, round(100.0 * job_viewed / nullif(viewed,0), 1) as job_view_rate_pct from s;

-- 8) Result View → External Job Click rate
with prod as (
  select * from analytics_events
  where coalesce(properties->>'environment','production') = 'production'
), s as (
  select
    count(distinct session_id) filter (where event_name = 'result_viewed')        as viewed,
    count(distinct session_id) filter (where event_name = 'external_job_clicked') as clicked
  from prod
)
select viewed, clicked, round(100.0 * clicked / nullif(viewed,0), 1) as external_click_rate_pct from s;

-- 9) Meaningful Career Exploration Rate
-- 定義：同一 session 同時有 quiz_completed、result_viewed、
--（role_opened 或 domain_selected）、（job_viewed 或 external_job_clicked）
with prod as (
  select * from analytics_events
  where coalesce(properties->>'environment','production') = 'production'
), flags as (
  select session_id,
    bool_or(event_name = 'quiz_completed') as completed,
    bool_or(event_name = 'result_viewed')  as viewed,
    bool_or(event_name in ('role_opened','domain_selected')) as explored_role,
    bool_or(event_name in ('job_viewed','external_job_clicked')) as explored_job
  from prod group by session_id
)
select
  count(*) filter (where completed) as completed_sessions,
  count(*) filter (where completed and viewed and explored_role and explored_job) as meaningful_sessions,
  round(100.0 * count(*) filter (where completed and viewed and explored_role and explored_job)
        / nullif(count(*) filter (where completed), 0), 1) as meaningful_rate_pct
from flags;

-- 10) Top-1 recommendation acceptance rate（回饋中 preferred = top1）
with prod as (
  select * from analytics_events
  where coalesce(properties->>'environment','production') = 'production'
), fb as (
  select * from prod where event_name = 'result_feedback_submitted'
)
select count(*) as feedback_count,
       count(*) filter (where (properties->>'preferred_role_was_top_1')::boolean) as top1_accepted,
       round(100.0 * count(*) filter (where (properties->>'preferred_role_was_top_1')::boolean)
             / nullif(count(*), 0), 1) as top1_acceptance_pct
from fb;

-- 11) Top-3 recommendation acceptance rate
with prod as (
  select * from analytics_events
  where coalesce(properties->>'environment','production') = 'production'
), fb as (
  select * from prod where event_name = 'result_feedback_submitted'
)
select count(*) as feedback_count,
       count(*) filter (where (properties->>'preferred_role_was_top_3')::boolean) as top3_accepted,
       round(100.0 * count(*) filter (where (properties->>'preferred_role_was_top_3')::boolean)
             / nullif(count(*), 0), 1) as top3_acceptance_pct
from fb;

-- 12) 平均 clarity uplift（僅計算 before/after 皆有值者）
with prod as (
  select * from analytics_events
  where coalesce(properties->>'environment','production') = 'production'
)
select count(*) as rated,
       round(avg(clarity_after - clarity_before), 2) as avg_clarity_uplift,
       round(avg(clarity_before), 2) as avg_before,
       round(avg(clarity_after), 2)  as avg_after
from prod
where event_name = 'result_feedback_submitted'
  and clarity_before is not null and clarity_after is not null;

-- 13) 各 top role 的 accuracy rating
with prod as (
  select * from analytics_events
  where coalesce(properties->>'environment','production') = 'production'
)
select role_id,
       count(*) as ratings,
       round(avg(accuracy_rating), 2) as avg_accuracy
from prod
where event_name = 'result_feedback_submitted' and accuracy_rating is not null
group by role_id
order by ratings desc;

-- 14) device_type 分群 funnel
with prod as (
  select * from analytics_events
  where coalesce(properties->>'environment','production') = 'production'
), device_of as (
  select distinct on (session_id) session_id, coalesce(device_type,'unknown') as device_type
  from prod order by session_id, occurred_at
), flags as (
  select d.device_type, p.session_id,
    bool_or(p.event_name = 'landing_viewed')  as landed,
    bool_or(p.event_name = 'quiz_started')    as started,
    bool_or(p.event_name = 'quiz_completed')  as completed,
    bool_or(p.event_name = 'result_viewed')   as viewed
  from prod p join device_of d using (session_id)
  group by d.device_type, p.session_id
)
select device_type,
  count(*) filter (where landed)    as landed,
  count(*) filter (where started)   as started,
  count(*) filter (where completed) as completed,
  round(100.0 * count(*) filter (where completed) / nullif(count(*) filter (where started),0), 1) as completion_pct
from flags group by device_type order by landed desc;

-- 15) utm_source 分群 funnel
with prod as (
  select * from analytics_events
  where coalesce(properties->>'environment','production') = 'production'
), src_of as (
  select distinct on (session_id) session_id, coalesce(utm_source, referrer_domain, 'direct') as source
  from prod order by session_id, occurred_at
), flags as (
  select s.source, p.session_id,
    bool_or(p.event_name = 'quiz_started')   as started,
    bool_or(p.event_name = 'quiz_completed') as completed
  from prod p join src_of s using (session_id)
  group by s.source, p.session_id
)
select source,
  count(*) as sessions,
  count(*) filter (where started)   as started,
  count(*) filter (where completed) as completed,
  round(100.0 * count(*) filter (where completed) / nullif(count(*) filter (where started),0), 1) as completion_pct
from flags group by source order by sessions desc;

-- 16) 近 7 天 vs 近 30 天趨勢
with prod as (
  select * from analytics_events
  where coalesce(properties->>'environment','production') = 'production'
), agg as (
  select
    count(distinct session_id) filter (where occurred_at >= now() - interval '7 days')  as sessions_7d,
    count(distinct session_id) filter (where occurred_at >= now() - interval '30 days') as sessions_30d,
    count(distinct session_id) filter (where event_name = 'quiz_completed' and occurred_at >= now() - interval '7 days')  as completed_7d,
    count(distinct session_id) filter (where event_name = 'quiz_completed' and occurred_at >= now() - interval '30 days') as completed_30d
  from prod
)
select sessions_7d, sessions_30d, completed_7d, completed_30d,
       round(100.0 * completed_7d / nullif(sessions_7d, 0), 1)  as completion_pct_7d,
       round(100.0 * completed_30d / nullif(sessions_30d, 0), 1) as completion_pct_30d
from agg;
