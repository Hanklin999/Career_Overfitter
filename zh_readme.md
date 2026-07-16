# Career Overfitter

一個以 AI 輔助的求職市場情報與 CV 決策支援產品，建構於 [104 人力銀行](https://www.104.com.tw/) 資料之上。

## 這個產品是為誰而做

Career Overfitter 的目標使用者是**明確想走數據分析，但不知道「數據分析」這件事其實藏在很多不同職稱與部門底下的人** — 一個 Business Analyst、一個 Product Analyst、一個 Data Scientist，實際做的工作內容可能高度重疊，但只靠職稱在人力銀行搜尋的人完全看不出這件事。這正是本產品目前定位為 **「Google Maps for Analytics Careers」** 的核心洞察：不從職缺列表開始，而是先給一張分析職涯的地圖，讓使用者先選一條路、看懂這條路實際在做什麼，最後才看個別職缺。

這個定位直接對應到本專案的具體設計選擇：為什麼資料來源是 104 而非全球型求職平台、為什麼爬蟲涵蓋四個分析領域（Business / Product / Marketing / Operations Analytics）而不是只有一個、為什麼要額外建立一層職務分類 overlay（`analytics_career_map.csv`）把原始職稱對應到「領域 x 工程深度」的座標系、以及為什麼 Career Map 和 Resume 兩頁才是整個產品的核心，而不是一個泛用的職缺搜尋框。

## 這個產品是什麼（以及不是什麼）

Career Overfitter 是一個**以 AI 輔助的求職市場情報與 CV 決策支援產品**——本質上是一套結構化資料管線，加上檢索增強生成（RAG），透過 Streamlit 應用呈現。

它**不是**一個自主代理人（autonomous agent）。系統中沒有多步驟任務規劃、沒有根據中間結果動態選擇工具、不會主動詢問缺失資訊、也沒有「執行動作 → 檢查結果」的迴圈。每一項功能（AI 建議、語意搜尋、職缺配對）都是單次的「檢索後生成」呼叫，而非 agentic loop。基於這個理由，本文件與產品介面刻意避免使用「AI agent」「agentic」「autonomous advisor」等字眼——真正的多輪對話式顧問功能目前列在「尚未實作」的未來規劃中，並非現有能力。

## 產品決策

**初始假設：** 這個族群的求職者，主要缺的不是職缺資訊本身，而是缺乏一個可靠的方法，把自己的實際經驗對應到零散、用詞不一致的市場需求上。

**MVP 優先順序（依序）：**

1. 從真實職缺建立結構化、去重的市場資料集（爬蟲 → 清洗 → 分類系統）。
2. 在提供任何個人化建議之前，先呈現職務與技能的市場需求樣態（技能儀表板）。
3. 透過檢索機制，讓個人化建議根基於真實職缺內容，而非僅依賴聚合統計數據（RAG）。
4. 為每一項依賴 AI 的功能保留決定性、規則式的備援方案，確保在 LLM API 無法使用或設定錯誤時產品仍可正常運作。

**明確排除優先順序（非疏漏，而是刻意決定不做）：**

- 自動大量投遞履歷
- 完全生成式的履歷改寫（規則式改寫建議是刻意的設計，而非過渡方案）
- 求職信（cover letter）生成
- 多輪對話式顧問
- 未經檢索職缺佐證的薪資預測

## 目錄

- [這個產品是為誰而做](#這個產品是為誰而做)
- [這個產品是什麼（以及不是什麼）](#這個產品是什麼以及不是什麼)
- [產品決策](#產品決策)
- [Analytics Career Map](#analytics-career-map)
- [功能特色](#功能特色)
- [系統架構](#系統架構)
- [專案結構](#專案結構)
- [快速開始](#快速開始)
- [資料管線](#資料管線)
- [爬蟲搜尋範圍](#爬蟲搜尋範圍)
- [RAG 系統（檢索增強生成）](#rag-系統檢索增強生成)
- [GitHub Actions 工作流程](#github-actions-工作流程)
- [維運注意事項](#維運注意事項)
- [未來規劃](#未來規劃)

## Analytics Career Map

產品把所有「分析類」職稱，用兩個軸重新組織 — 定義在 `utils/career_taxonomy.py` 與 `analytics_career_map.csv`（疊加在既有 280 列 `Job_taxonomy_byRole.csv` 分類表之上的 overlay，不會改變職缺分類邏輯本身，只是把分類結果裡「分析相關」的 `role_normalized` 值重新組織成一張好瀏覽的地圖）：

- **領域（業務應用），4 個值**：Business Analytics、Product Analytics、Marketing Analytics、Operations Analytics — *這個角色在分析什麼類型的問題*
- **工程深度，4 個等級**：BA → DA → DS → DE（Business Analyst → Data Analyst → Data Scientist → Data Engineer）— *這個角色離建模／工程有多近*

目前橫跨四個領域共對應 72 個職稱（例如 Product Analytics 底下包含 Product Analyst、Growth Product Analyst、Marketplace Analyst、CRM & Lifecycle Analyst、Decision Scientist 等）。其中 **Marketplace Analyst** 與 **CRM & Lifecycle Analyst** 兩個職稱在原本的分類表裡不存在，是專門新增的，目的是讓 Product Analytics 有完整的子分類；`CRM & Lifecycle Analyst` 刻意取了跟既有 `CRM Analyst`（屬於另一個 parent category、偏 IT／CRM 系統導入的職稱）不同的名字，避免兩者混淆。

不屬於「分析類」的職稱（Product Manager、Sales 相關、一般 HR／財務職稱等）刻意不放進這張地圖 — 地圖的目的是幫使用者找到藏在陌生職稱底下的分析工作，不是要涵蓋所有職能。

## 功能特色

### 🗺️ Explore Careers

- Analytics Career Map 的入口頁：X/Y 市場分布圖，一軸是領域、一軸是工程深度，泡泡大小代表目前該象限的職缺數量
- 點選或選擇一個領域，往下看該領域底下的子分類職稱與即時職缺數／薪資中位數，再往下才看個別職缺

### 🧭 Career Map

- 以 sunburst 階層圖呈現 Analytics → Domain → Sub-role — 從整體地圖一路點到單一職稱
- 選定一個職稱後，**依序**顯示：這個角色實際在做什麼（白話條列）、常見相關職稱、市場需求、薪資中位數、熱門技能、常見公司、你的履歷適配度（若已用過 Resume 頁）、最後才是這個職稱的真實職缺

### 📄 Resume

- 貼上履歷文字，或上傳 `.txt` / `.md` 檔案
- 透過邊界安全的別名比對器（`skill_alias.csv`）擷取 canonical 技能，並對容易誤判的短英文縮寫（如 `AI`、`PM`、`UX`）套用 evidence 權重降權，降低誤判率
- 對照職務分類，計算加權適配分數；分數會寫入 session state，讓 Career Map 頁在瀏覽任何職稱時都能直接顯示「Resume Fit」，不用重新計算
- 規則式改寫建議，離線即可使用，不依賴外部 API
- **Career Advisor（Gemini）**：不是泛用的「問 AI」框，而是回答有範圍的職涯決策問題（這條路為什麼適合我、我還缺哪些技能、BI 跟 Product Analytics 差在哪）；有真實職缺可檢索時會用其內容佐證，API 無法使用時自動退回規則式建議
- **推薦真實職缺**：獨立的功能按鈕，透過向量搜尋找出與你履歷最相似的實際職缺，並附上回到 104 原始職缺的連結
- 適配分數與技能證據皆可匯出 CSV

### 📈 Market Trends

- **Compare Career Paths**：不是「Top SQL / Top Python」排行榜，而是技能 x 領域的星等比較矩陣，讓你看出同一個技能在不同路徑的相對重要程度 — 這才是使用者真正想問的「我要往哪一條路」，而不是「什麼技能最紅」
- 各職稱薪資中位數、產業分布、遠端工作比例

### 🎯 Jobs

- 篩選的第一步是 **Career Path**（先選領域，再選底下的子分類職稱），不是原始的職稱關鍵字框
- 「你想做什麼樣的工作？」— 用一句話描述你的興趣，系統會先告訴你這聽起來像哪些 Career Path，再列出對應職缺（賣的是 Path，不是關鍵字搜尋）
- 每筆結果都附技能標籤、品質分數，以及回到 104 原始頁面的連結；可匯出 CSV

## 系統架構

```
                     ┌──────────────────┐
  104 人力銀行 ───▶  │  scraper_104.py  │ ───▶  jd_raw（Supabase）
                     └──────────────────┘
                                                     │
                                                     ▼
                                            ┌──────────────────┐
                                            │    cleaner.py     │  規則式職務分類
                                            │                    │  + 技能擷取
                                            └──────────────────┘
                                                     │
                                                     ▼
                                          job_posting（Supabase）
                                                     │
                              ┌──────────────────────┼──────────────────────┐
                              ▼                      ▼                      ▼
                     backfill_embeddings.py   Streamlit 應用（app.py）  pgvector 欄位
                              │                      │                      │
                              └──────────────────────┼──────────────────────┘
                                                     ▼
                                     utils/rag_retrieval.py + llm_advisor.py
                                    （Gemini generateContent + embedContent）
                                                     │
                                                     ▼
                                 utils/career_taxonomy.py（領域 x 工程深度 overlay，
                                 來自 analytics_career_map.csv）驅動 Explore Careers /
                                 Career Map / Market Trends / Jobs 四個頁面
```

系統使用兩組獨立的 Gemini API，共用同一組 `GEMINI_API_KEY`：

- **Embedding（向量化）**（`gemini-embedding-001`，透過 `utils/embeddings.py`）— 將職缺與使用者查詢轉換為向量，存放於 Supabase 的 `pgvector` 擴充功能中
- **生成（Generation）**（`gemini-2.5-flash`，透過 `utils/llm_advisor.py`）— 將結構化診斷結果與檢索到的職缺內容轉換為 Resume 頁面顯示的 Career Advisor 建議

## 專案結構

```
Career_Overfitter/
├── app.py                          # Streamlit 進入點（首頁，流程總覽）
├── pages/
│   ├── 1_Explore_Careers.py        # 領域 x 工程深度市場地圖（XY 分布圖）
│   ├── 2_Career_Map.py             # Sunburst 階層圖 + 單一職稱詳情面板
│   ├── 3_Resume.py                 # CV 解析、適配分數、Career Advisor、職缺配對
│   ├── 4_Market_Trends.py          # Compare Career Paths（技能 x 領域矩陣）、薪資、產業
│   └── 5_Jobs.py                   # Career Path 優先的職缺瀏覽 + 自然語言路徑分流
├── utils/
│   ├── supabase_client.py          # 帶快取的 Supabase REST 查詢
│   ├── cv_parser.py                # 技能擷取與適配分數計算
│   ├── ui_taxonomy.py              # UI 共用的篩選／分類輔助函式
│   ├── career_taxonomy.py          # Analytics Career Map overlay（領域 x 工程深度）
│   ├── llm_advisor.py              # Gemini generateContent 封裝（Career Advisor）
│   ├── embeddings.py               # Gemini embedContent/batchEmbedContents 封裝
│   └── rag_retrieval.py            # 透過 Supabase RPC 對 job_posting 做向量搜尋
├── scraper_104.py                  # 104 爬蟲 → jd_raw
├── cleaner.py                      # jd_raw → job_posting（規則式分類）
├── backfill_embeddings.py          # 為既有 job_posting 資料批次補算 embedding
├── clear_supabase_data.py          # 清空 jd_raw + job_posting（供「清空全部資料」選項使用）
├── sql/
│   └── 001_enable_pgvector_rag.sql # 啟用 pgvector、新增 embedding 欄位、建立 RPC function
├── Job_taxonomy_forsearch.csv      # 目前生效中的爬蟲關鍵字清單（42 個關鍵字，涵蓋 4 個領域）
├── Job_taxonomy_forsearch_full.csv # 完整 147 個關鍵字備份，供未來擴大範圍使用
├── Job_taxonomy_forsearch_marketing_analytics_backup.csv  # 前一版範圍快照
├── Job_taxonomy_byRole.csv         # 用於分類的職務分類表（280 列）
├── analytics_career_map.csv        # role_normalized → (領域, 工程深度) 對應表，供地圖使用
├── skill_alias.csv                 # 技能別名對照表
├── skill_taxonomy.csv              # 技能分類表
├── role_alias.csv                  # 職務名稱別名表
├── .github/workflows/
│   ├── cleaner-weekly.yml          # 主要管線：爬蟲 → 清洗 → 補算 embedding
│   ├── clean-only.yml              # 獨立工作流程：只重跑 cleaner，不重新爬蟲
│   └── test.yml                    # 單一關鍵字的輕量煙霧測試
├── requirements.txt
└── .env                            # 本機密鑰 — 切勿提交至版本控制
```

## 快速開始

### 前置需求

- Python 3.11 以上
- 一個 Supabase 專案（免費方案即可）
- 一組來自 [Google AI Studio](https://aistudio.google.com/apikey) 的 Gemini API 金鑰（非必要，但若要使用 AI 建議、語意搜尋、職缺配對功能則須設定）

### 安裝

```bash
pip install -r requirements.txt
```

### 環境變數

在專案根目錄建立 `.env`：

```env
SUPABASE_URL=https://xxxxxxxxxxxx.supabase.co/rest/v1
SUPABASE_KEY=your_anon_or_service_role_key

# 選填 — 啟用 AI 建議、語意搜尋、RAG 職缺配對
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-2.5-flash
GEMINI_EMBEDDING_MODEL=gemini-embedding-001
GEMINI_EMBEDDING_DIM=768
```

若部署在 Streamlit Community Cloud，改為將相同的 key/value 貼到應用的 **Settings → Secrets**（TOML 格式）；放在最外層的變數會自動以環境變數形式暴露，不需修改程式碼。

### 必要的 CSV 檔案

以下檔案須存在於專案根目錄（本 repo 已包含）：

- `skill_alias.csv`、`skill_taxonomy.csv`
- `Job_taxonomy_byRole.csv`、`role_alias.csv`
- `Job_taxonomy_forsearch.csv`（僅爬蟲使用）

### 本機執行

```bash
streamlit run app.py
```

開啟 http://localhost:8501。

## 資料管線

1. **`scraper_104.py`** 只從 `Job_taxonomy_forsearch.csv` 讀取關鍵字，呼叫 104 的列表與詳情 API，並將原始職缺 upsert 進 `jd_raw` 資料表。內建退避重試機制與流量封鎖偵測（`FAKE_404_THRESHOLD` / `FAKE_404_PAUSE`），因為 104 對高頻請求的限速相當嚴格。
2. **`cleaner.py`** 從 `jd_raw` 讀取資料，套用規則式職務分類（依據 `Job_taxonomy_byRole.csv`）與技能擷取（依據 `skill_alias.csv`），計算品質分數後 upsert 進 `job_posting`。執行時請將 `--limit` 設定為明顯高於 `jd_raw` 總筆數，並搭配 `--only-new`，以確保清洗涵蓋整個待處理積壓，而非只處理最近爬取的資料。
3. **`backfill_embeddings.py`** 為所有尚未有 embedding 的 `job_posting` 資料計算 Gemini embedding 並寫回，讓 RAG 搜尋可以運作。

## 爬蟲搜尋範圍

爬蟲最初使用 `Job_taxonomy_forsearch.csv` 中橫跨 18 個職務類別的全部 147 個關鍵字，並拆成 8 個 GitHub Actions matrix shard 平行執行 — 但總請求量過高，導致 104 開始封鎖流量（詳見 `scraper_104.py` 中的 `FAKE_404_THRESHOLD` 處理邏輯）。

搜尋範圍目前已調整三次：

1. 第一次縮減為 `Marketing / Brand / Growth` + `Analytics / Data / BI`（18 個關鍵字）— 保存於 `Job_taxonomy_forsearch_marketing_analytics_backup.csv`。
2. 進一步縮減為只聚焦 **Product Data Analyst**（12 個關鍵字），橫跨 `Product Management` 與 `Analytics / Data / BI` 兩個類別。
3. **目前已擴大為橫跨四個領域、共 42 個關鍵字** — `Product Management`、`Analytics / Data / BI`（原本的 12 個關鍵字不變），加上新增的 `Business Analytics`、`Marketing Analytics`、`Operations Analytics` 三個類別（新增 30 個關鍵字），讓下方的 Analytics Career Map 能在四個分析領域都有真實市場資料，而不只是 Product 一個領域。

完整的 147 個關鍵字清單保留在 `Job_taxonomy_forsearch_full.csv`，供參考。`cleaner-weekly.yml` 目前跑 3 個 matrix shard，每個約 14 個關鍵字（`offset 0/14/28`、`limit 14`），對應目前 42 個關鍵字的範圍；刻意選擇「較少、較大」的 shard 數量（3 個而非更多），以降低每個 shard checkout／安裝依賴的重複開銷，代價是每個 shard 被 104 限速的風險比先前單一 12 關鍵字 shard 略高。調整後請留意 `scrape-104` job 的 log 是否出現 `FAKE_404` 警告 — 若再次被封鎖，建議拆成更多、更小的 shard（例如 6 個約 7 個關鍵字），而非刪減關鍵字數量。

**若要進一步擴大或重新聚焦搜尋範圍：**

1. 先確認目前四領域範圍已能穩定執行、未再被封鎖。
2. 在 `Job_taxonomy_forsearch.csv` 新增或替換關鍵字（或從 `Job_taxonomy_forsearch_full.csv` 複製更多類別）。
3. 調整 `cleaner-weekly.yml` 中的 `matrix.include` — 建議每個 shard 維持在 14–20 個關鍵字左右，需要時再增加 shard 數量。

## RAG 系統（檢索增強生成）

以下三項功能透過向量搜尋，以真實職缺內容作為依據，而非單純依賴聚合統計數據：

- **AI 建議**（CV 比對工具）— 檢索與使用者履歷及目標職務最相關的職缺，並指示 Gemini 在產生建議時優先參考這些職缺的實際內容，而非僅依賴聚合技能權重統計推論。
- **推薦真實職缺**（CV 比對工具）— 將檢索到的職缺直接以排序、附連結的清單呈現，與 AI 建議的生成流程互相獨立。
- **語意搜尋**（職缺搜尋）— 讓使用者以自然語言描述需求，而非僅能依賴精確關鍵字比對。

### 運作方式

1. `utils/embeddings.py` 呼叫 Gemini 的 `gemini-embedding-001`（單筆查詢用 `embedContent`，批次補算用 `batchEmbedContents`），並透過 `outputDimensionality` 截斷至 768 維。遇到 429 錯誤時會以指數退避重試。
2. 向量儲存於 `job_posting.embedding` 欄位（Postgres 的 `vector(768)` 型別，透過 pgvector 擴充功能）。
3. `utils/rag_retrieval.py` 將查詢文字向量化後，呼叫 `match_job_postings` 這個 Postgres RPC（餘弦相似度計算，透過 PostgREST 自動對外暴露），取回最相似的前 N 筆職缺。
4. 每一個依賴 RAG 的功能都會先檢查可用性，若 pgvector 尚未設定完成，會自動退回非 RAG 的行為，而非直接報錯。

### 設定步驟

1. 在 Supabase Dashboard 開啟 **SQL Editor**，執行 `sql/001_enable_pgvector_rag.sql` 的完整內容（具冪等性，可重複執行）。
2. 為既有資料補算 embedding：
   ```bash
   python backfill_embeddings.py --limit 200
   ```
   若資料筆數超過此 limit，請以更大的 `--limit` 重新執行。`cleaner-weekly.yml` 會在每次清洗後自動執行此步驟（設有 `continue-on-error: true`，因此即使遷移尚未完成也不會導致整個管線失敗）。
3. 確認 `GEMINI_API_KEY` 已設定 — 不需要其他額外設定，所有 RAG 相關的 UI 區塊都會自動偵測可用性。

## GitHub Actions 工作流程

| 工作流程 | 觸發方式 | 用途 |
|---|---|---|
| `cleaner-weekly.yml` | 手動（`workflow_dispatch`） | 完整管線：可選的資料清空 → 爬蟲 → 清洗（`--limit 20000 --only-new`）→ 補算 embedding |
| `clean-only.yml` | 手動 | 只重跑 `cleaner.py`（可設定 `limit`／`only_new`／`quality_threshold`），並補算 embedding，不重新爬蟲 |
| `test.yml` | 手動 | 單一關鍵字、單頁的完整爬蟲 → 清洗管線煙霧測試 |

所需的 repository secrets：`SUPABASE_URL`、`SUPABASE_KEY`、`GEMINI_API_KEY`。

`cleaner-weekly.yml` 另外提供 `truncate_before_run` 核取方塊（預設關閉）。啟用時，會先執行 `clear_supabase_data.py`，清空 `job_posting` 與 `jd_raw` 兩張表的**所有**資料，才開始執行管線。此操作不可逆，啟用前請務必確認 secrets 指向的是正確的 Supabase 專案。

## 維運注意事項

- **Supabase 免費方案自動暫停**：專案若連續 7 天無資料庫活動會自動暫停，API 會完全無法解析，須手動從 Dashboard 恢復。若每週排程的頻率不足以被視為活動，可考慮加入輕量的保活機制，或升級為付費方案。
- **Gemini 免費方案速率限制**：embedding 補算會分批請求，遇到 `429` 時以指數退避重試；若仍持續觸發限制，可調降 `backfill_embeddings.py` 中的 `EMBED_BATCH_SIZE`，或拉長批次間的等待時間。
- **`cleaner.py` 預設行為**：若 `--limit` 設定不夠高，只有最近爬取的資料會被納入考量，較舊、尚未清洗的資料可能因落在視窗之外而被永久跳過。`cleaner-weekly.yml` 與 `clean-only.yml` 皆已傳入足夠大的 `--limit` 以避免此問題。
- **設定檔遺失風險**：`Job_taxonomy_forsearch.csv` 對爬蟲至關重要，若整個 repo 被部分檔案的交付內容整批覆蓋，很容易遺失 — 進行大量複製貼上更新後，請務必比對檔案數量或內容差異。

## 未來規劃

已完成：RAG 輔助的 AI 建議、語意職缺搜尋、CV 直接配對具體職缺。

考慮中、尚未實作（與上方[明確排除優先順序](#產品決策)清單不同 — 這些是未來可能推進的候選項目，而非已否決的想法）：

- 混合式技能擷取 — 在現有規則式 `skill_alias.csv` 比對器之外，補充 embedding 相似度比對，捕捉別名表未涵蓋的技能描述方式，同時仍以規則式比對作為主要判斷依據
- 透過 embedding 相似度偵測重複／近似重複職缺，避免重複刊登拉偏技能儀表板的統計結果
- 多輪對話式職涯顧問，讓每次追問都能重新檢索，而非僅在單一 session 中檢索一次 — 這是唯一能讓本產品名符其實地稱為「agentic」的關鍵功能；在其實作完成前，本產品定位為 AI 輔助／RAG 型產品，而非 agentic 產品（見[這個產品是什麼](#這個產品是什麼以及不是什麼)）
