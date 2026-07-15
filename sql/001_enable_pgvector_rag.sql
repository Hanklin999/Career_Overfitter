-- ============================================================
-- Career Overfitter — 啟用 pgvector + CV Fit RAG 檢索用的 schema
-- ============================================================
-- 用法：整份貼到 Supabase Dashboard -> SQL Editor -> New query，執行一次即可。
-- 可重複執行（用了 if not exists / or replace），不會因為重跑而報錯或重複建立。
--
-- 這份 migration 做三件事：
--   1. 啟用 pgvector extension
--   2. job_posting 加一個 embedding 欄位，存 Gemini embedding 向量
--   3. 建立 match_job_postings 這個 RPC function，讓 Streamlit 那邊可以透過
--      PostgREST 呼叫（POST /rest/v1/rpc/match_job_postings）做相似度檢索
-- ============================================================

-- 1. 啟用 pgvector（Supabase 免費方案就有，不用額外付費）
create extension if not exists vector;

-- 2. job_posting 加 embedding 欄位
--    維度用 768（Gemini embedding 模型透過 outputDimensionality 截斷到 768），
--    在儲存空間跟檢索品質之間是常見的折衷值，資料量不大的話完全夠用。
alter table job_posting
  add column if not exists embedding vector(768);

-- 3. 相似度檢索用的 RPC function
--    cosine distance 用 <=> 運算子，PostgREST 沒辦法直接在一般 REST query
--    裡使用這種運算子，所以包成一個 SQL function，讓程式端改成呼叫
--    /rest/v1/rpc/match_job_postings 就好。
create or replace function match_job_postings(
  query_embedding vector(768),
  match_count int default 5,
  filter_role text default null
)
returns table (
  job_no text,
  title_clean text,
  role_normalized text,
  job_parent_category text,
  job_description text,
  similarity float
)
language sql stable
as $$
  select
    job_posting.job_no,
    job_posting.title_clean,
    job_posting.role_normalized,
    job_posting.job_parent_category,
    job_posting.job_description,
    1 - (job_posting.embedding <=> query_embedding) as similarity
  from job_posting
  where job_posting.embedding is not null
    and (filter_role is null or job_posting.role_normalized = filter_role)
  order by job_posting.embedding <=> query_embedding
  limit match_count;
$$;

-- ============================================================
-- 選用：等 job_posting 資料量變大（例如破萬筆）以後，可以再加一個
-- ivfflat 索引加速相似度搜尋。資料量還小的時候不需要，加了效果也不明顯，
-- 甚至 ivfflat 對太小的表現不佳，所以先不建，這裡先留著當之後的參考：
--
-- create index if not exists job_posting_embedding_idx
--   on job_posting
--   using ivfflat (embedding vector_cosine_ops)
--   with (lists = 100);
-- ============================================================
