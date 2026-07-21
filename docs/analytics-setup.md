# 匿名使用分析設定（Supabase Analytics）

## 架構

純靜態站（無 bundler、無後端）。前端 `analytics.js` 直接呼叫 Supabase REST API
（PostgREST）對 `public.analytics_events` 做 insert，使用 `fetch keepalive`，
不阻塞換頁與外部連結。**不載入 supabase-js 套件**（零依賴，等效且更輕量）。

安全模型：前端只持有 Project URL 與 anon（publishable）key——這兩者依 Supabase
設計本來就會公開，資料安全由 Row Level Security 保證：匿名使用者**只能 INSERT**，
不能 SELECT / UPDATE / DELETE，且事件名稱走 DB 端 allowlist。

> ⚠️ **service_role key 絕對不能放進前端、repository 或任何公開位置。**

## Supabase 建立步驟

1. https://supabase.com → New project（免費方案即可）
2. Dashboard → SQL Editor → 貼上並執行 `supabase/migrations/001_create_analytics_events.sql`
3. Dashboard → Settings → API → 複製 `Project URL` 與 `anon public` key

## 前端設定（取代環境變數）

本專案無 build step，Netlify 的環境變數無法注入前端，因此設定放在
`analytics-config.js`（可安全入庫，因為 anon key 本來就是公開的）：

```js
window.ANALYTICS_CONFIG = {
  SUPABASE_URL: "https://xxxx.supabase.co",
  SUPABASE_ANON_KEY: "eyJ...",
  ANALYTICS_ENABLED: true,
  ANALYTICS_DEBUG: false
};
```

兩個值留空 = analytics 自動停用（console.warn 一次，網站功能完全正常）。
`.env.example` 僅作為欄位對照文件，本專案實際不讀取 .env。

## local / preview / production 區分

由 hostname 自動判定，寫入每筆事件的 `properties.environment`：

| 環境 | 判定 | 行為 |
|---|---|---|
| `local` | localhost / 127.0.0.1 | **預設不送出**（開 ANALYTICS_DEBUG 才送，方便測試） |
| `deploy_preview` | `*--*.netlify.app` | 送出，標記 deploy_preview，分析時排除 |
| `production` | 其他 | 送出 |

分析 SQL 預設 `properties->>'environment' = 'production'`。

## Event Dictionary

| 事件 | 觸發時機 | 主要欄位 |
|---|---|---|
| landing_viewed | 首頁載入，每 session 一次 | landing_variant |
| quiz_started | 點 CTA 進入第一站 | entry_point |
| quiz_step_viewed | 進入某站（同站 re-render 不重複） | quiz_step, navigation_direction |
| quiz_step_completed | 完成某站進下一站 | quiz_step, time_spent_sec, answered/total_question_count |
| quiz_completed | 配對計算成功 | total_time_spent_sec, completed_step_count, result_count |
| result_viewed | 結果顯示（每次新測驗一次） | role_id, top/second/third_role_id, scoring_version |
| role_opened | 展開角色完整說明 | role_id, recommendation_rank, source |
| domain_selected | 結果頁選領域 | domain_id, role_id, selection_action |
| industry_selected | （目前無此 UI，僅預留定義） | — |
| job_viewed | 職缺卡在使用者篩選後渲染 | job_id, role_id, domain_id, company_name, list_position |
| external_job_clicked | 點外部職缺連結 | job_id, destination_domain（僅 hostname） |
| quiz_restarted | 結果頁重新測驗 | previous_top_role_id |
| result_feedback_viewed | 回饋卡進入 viewport，每結果一次 | — |
| result_feedback_submitted | 送出匿名回饋 | accuracy_rating, clarity_before/after, preferred_role_id |

role_id 使用 Job Family 全名字串（資料模型中的穩定識別鍵）。

## 如何驗證事件

1. 本機：`python -m http.server 8000`，`analytics-config.js` 填好並暫時設 `ANALYTICS_DEBUG: true`
2. 開 DevTools Console：每個事件會印出 payload；Network 分頁應看到 `analytics_events` POST 201
3. Supabase Dashboard → Table Editor → `analytics_events` → 應出現事件列（第一筆通常是 landing_viewed）
4. 驗完把 `ANALYTICS_DEBUG` 改回 `false`

## 確認 anon 無法讀取

用 curl（換成你的 URL 與 anon key）：

```bash
curl "https://xxxx.supabase.co/rest/v1/analytics_events?select=*" \
  -H "apikey: <ANON_KEY>" -H "Authorization: Bearer <ANON_KEY>"
```

預期得到 `permission denied`（42501）或空陣列以外的錯誤——**不應**回傳資料列。
UPDATE / DELETE 同理會被拒絕。INSERT 則應成功（201）。

## 隱私與資料最小化

- 匿名 session ID 存 sessionStorage（關分頁即結束），不用 localStorage 建立永久識別
- 不存：姓名、Email、電話、完整作答、精確位置、IP 欄位、瀏覽器指紋、完整 referrer/外部 URL（只留 domain）
- device_type 只分 mobile / tablet / desktop / unknown，不解析完整 UA
- properties 欄位走前端 allowlist＋長度限制，DB 端另有 4KB 上限

## 如何關閉 analytics

`analytics-config.js` 設 `ANALYTICS_ENABLED: false`（或清空 URL/KEY）→ commit → push。

## 如何刪除測試資料

Supabase SQL Editor（service_role 權限）：

```sql
delete from analytics_events where properties->>'environment' != 'production';
```

## 已知限制

- 回饋送出為 fire-and-forget：失敗時前端仍顯示感謝訊息（內建一次自動重試；client_event_id 可後端去重）
- sessionStorage 被清除或無痕模式限制時，同一人可能產生多個 session
- keepalive fetch 在極舊瀏覽器可能於換頁時丟失事件

## 執行 analytics_queries.sql

Supabase SQL Editor 開啟 `supabase/analytics_queries.sql`，每段查詢（1–16）可獨立複製執行。
