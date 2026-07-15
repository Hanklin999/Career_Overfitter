# Career Overfitter

一個以 AI 輔助的求職市場情報與 CV 決策支援產品，建構於 [104 人力銀行](https://www.104.com.tw/) 資料之上。

## 這個產品是為誰而做

Career Overfitter 的目標使用者是**台灣的早期職涯或轉職中的數據／商業專業人士，他們不確定自己的背景是否真的符合 Product Analytics、BI、Growth 或 Product Management 這類職務，且目前沒有可靠的方法把零散、用詞不一致的職缺資訊轉化成具體可執行的下一步**。

這個定位直接對應到本專案的具體設計選擇：為什麼資料來源是 104 而非全球型求職平台、為什麼爬蟲範圍聚焦在 Product Data Analyst 相關關鍵字而非「所有職缺」、為什麼要建立職務／技能分類系統來正規化命名而非直接呈現原始職缺文字、以及為什麼 CV 比對工具是整個產品的核心，而不只是一個泛用的職缺搜尋介面。

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

## 功能特色

### 🔍 職缺搜尋

- 結構化篩選：職稱關鍵字、公司性質（外商／本土、上市／未上市）、產業、職務類別、最低薪資、最低學歷、遠端工作偏好
- **AI 語意搜尋**：直接用一句話描述你想要的工作（例如「想找用 Python 做行銷分析、不需要太多工程背景的職缺」），系統會根據向量相似度比對真實職缺內容排序結果，與結構化篩選條件互相獨立
- 每筆結果都附技能標籤、品質分數，以及回到 104 原始頁面的連結
- 一鍵匯出 CSV

### 📊 技能儀表板

- 依出現頻率排列 Top-N 熱門技能
- 各職務的薪資中位數
- 產業分布與遠端工作比例
- 可排序的原始資料表

### 📄 CV 比對工具

- 貼上履歷文字，或上傳 `.txt` / `.md` 檔案
- 透過邊界安全的別名比對器（`skill_alias.csv`）擷取 canonical 技能，並對容易誤判的短英文縮寫（如 `AI`、`PM`、`UX`）套用 evidence 權重降權，降低誤判率
- 對照職務分類，計算加權適配分數，並列出符合與缺口技能
- 規則式改寫建議，離線即可使用，不依賴外部 API
- **AI 建議（Gemini）**：最適配職務、適配原因、關鍵技能證據、主要缺口、履歷改寫建議、下一步學習方向 — 依需求即時產生，API 無法使用時會自動退回規則式建議
- **推薦真實職缺**：獨立的功能按鈕，透過向量搜尋找出與你履歷最相似的實際職缺（而非僅是聚合後的職務輪廓），並附上回到 104 原始職缺的連結
- 適配分數與技能證據皆可匯出 CSV

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
```

系統使用兩組獨立的 Gemini API，共用同一組 `GEMINI_API_KEY`：

- **Embedding（向量化）**（`gemini-embedding-001`，透過 `utils/embeddings.py`）— 將職缺與使用者查詢轉換為向量，存放於 Supabase 的 `pgvector` 擴充功能中
- **生成（Generation）**（`gemini-2.5-flash`，透過 `utils/llm_advisor.py`）— 將結構化診斷結果與檢索到的職缺內容轉換為 CV 比對工具頁面顯示的 AI 建議

## 專案結構

```
Career_Overfitter/
├── app.py                          # Streamlit 進入點（首頁）
├── pages/
│   ├── 1_Job_Search.py             # 職缺瀏覽 + AI 語意搜尋
│   ├── 2_Skill_Dashboard.py        # 市場技能／薪資／產業統計
│   └── 3_CV_Fitting_Tool.py        # CV 解析、適配分數、AI 建議、職缺配對
├── utils/
│   ├── supabase_client.py          # 帶快取的 Supabase REST 查詢
│   ├── cv_parser.py                # 技能擷取與適配分數計算
│   ├── ui_taxonomy.py              # UI 共用的篩選／分類輔助函式
│   ├── llm_advisor.py              # Gemini generateContent 封裝（AI 建議）
│   ├── embeddings.py               # Gemini embedContent/batchEmbedContents 封裝
│   └── rag_retrieval.py            # 透過 Supabase RPC 對 job_posting 做向量搜尋
├── scraper_104.py                  # 104 爬蟲 → jd_raw
├── cleaner.py                      # jd_raw → job_posting（規則式分類）
├── backfill_embeddings.py          # 為既有 job_posting 資料批次補算 embedding
├── clear_supabase_data.py          # 清空 jd_raw + job_posting（供「清空全部資料」選項使用）
├── sql/
│   └── 001_enable_pgvector_rag.sql # 啟用 pgvector、新增 embedding 欄位、建立 RPC function
├── Job_taxonomy_forsearch.csv      # 目前生效中的爬蟲關鍵字清單（目前 12 個關鍵字）
├── Job_taxonomy_forsearch_full.csv # 完整 147 個關鍵字備份，供未來擴大範圍使用
├── Job_taxonomy_forsearch_marketing_analytics_backup.csv  # 前一版範圍快照
├── Job_taxonomy_byRole.csv         # 用於分類的職務分類表
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

搜尋範圍已縮減兩次：

1. 第一次縮減為 `Marketing / Brand / Growth` + `Analytics / Data / BI`（18 個關鍵字）— 保存於 `Job_taxonomy_forsearch_marketing_analytics_backup.csv`。
2. 目前聚焦於 **Product Data Analyst**（12 個關鍵字），橫跨 `Product Management` 與 `Analytics / Data / BI` 兩個類別。

完整的 147 個關鍵字清單保留在 `Job_taxonomy_forsearch_full.csv`，供未來擴大範圍時使用。`cleaner-weekly.yml` 目前只跑單一 matrix shard，對應目前縮減後的關鍵字數量。

**若要擴大或重新聚焦搜尋範圍：**

1. 先確認目前範圍已能穩定執行、未再被封鎖。
2. 從 `Job_taxonomy_forsearch_full.csv`（或某個 `*_backup.csv` 快照）複製想要的類別／關鍵字進 `Job_taxonomy_forsearch.csv`。
3. 調整 `cleaner-weekly.yml` 中的 `matrix.include` — 建議每個 shard 維持在 15–20 個關鍵字左右，需要時再增加 shard 數量。

建議採漸進式擴充（一次增加 1–2 個類別），而非一次恢復成完整清單；資料量的成長也不一定需要新增關鍵字，讓每週排程在目前範圍內持續累積資料同樣有效。

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
