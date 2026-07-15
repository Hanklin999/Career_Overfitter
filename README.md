# Career Overfitter — Streamlit Frontend

## 專案結構

```
Career_Overfitter/
├── app.py                    # 主入口（首頁）
├── pages/
│   ├── 1_職缺瀏覽.py         # 職缺搜尋 & 瀏覽
│   ├── 2_CV_Fit分析.py       # 履歷技能抽取 & Fit Score
│   └── 3_技能Dashboard.py    # 技能熱度 / 薪資 / 產業分析
├── utils/
│   ├── supabase_client.py    # Supabase 查詢（有 cache）
│   └── cv_parser.py          # CV 解析 & FitScore 計算
├── requirements.txt
└── .env                      # 不要 commit！
```

## 環境設定

### 1. 安裝依賴
```bash
pip install -r requirements.txt
```

### 2. 設定 .env
```env
SUPABASE_URL=https://xxxxxxxxxxxx.supabase.co/rest/v1
SUPABASE_KEY=your_anon_or_service_role_key

# 選填：設定後 CV Fitting Tool 會啟用「AI 智能建議」區塊
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-2.5-flash
```

### 3. 確認 CSV 檔案存在於專案根目錄
- `skill_alias.csv`
- `skill_taxonomy.csv`
- `Job_taxonomy_byRole.csv`
- `role_alias.csv`

## 執行

```bash
streamlit run app.py
```

瀏覽器開啟 http://localhost:8501

## 功能說明

### 🔍 職缺瀏覽
- 依職稱關鍵字、Role、產業、薪資、Remote 篩選
- 顯示技能 tags、品質分數
- 一鍵匯出 CSV

### 📄 CV Fit 分析
- 貼上履歷文字或上傳 .txt / .md
- 自動對照 skill_alias.csv 抽取 canonical skills
- 計算與各 role 的加權 fit score
- 顯示匹配 / 缺口技能
- 內建規則式（rule-based）履歷改寫建議，離線可用
- 設定 `GEMINI_API_KEY` 後，可另外產生「AI 智能建議」：最適職能、關鍵技能證據、
  最大缺口、履歷改寫建議、下一步學習建議（見 `utils/llm_advisor.py`）
- 匯出 Fit Score CSV

### 📊 技能 Dashboard
- Top N 技能需求橫條圖
- 各 Role 薪資中位數
- 產業分布 & Remote 比例
- 可排序數據表

## 資料來源
所有資料來自 Supabase `job_posting` 表（由 cleaner.py 寫入）。
`jd_raw` 筆數顯示爬蟲進度，`job_posting` 筆數顯示清洗進度。

## Cache 設定
`supabase_client.py` 使用 `@st.cache_data(ttl=300)`（5分鐘）。
若需要即時資料，點擊右上角 ⟳ 重新整理即可。

## 爬蟲範圍（Phase 1 縮小版）

104 職缺爬蟲原本用 `Job_taxonomy_forsearch.csv` 裡 147 個關鍵字、橫跨 18 個職能大類，
搭配 GitHub Actions 8 個平行 shard 執行，總請求量太大，容易被 104 判定為異常流量而擋下
（見 `scraper_104.py` 裡的 `FAKE_404_THRESHOLD` / `FAKE_404_PAUSE` 處理）。

範圍縮小過兩次：

1. 第一次縮到 `Marketing / Brand / Growth` + `Analytics / Data / BI`（18 個關鍵字）。
   這份設定備份在 `Job_taxonomy_forsearch_marketing_analytics_backup.csv`。
2. 目前改成以 **Product Data Analyst** 為中心，共 12 個關鍵字，分屬：
   - `Product Management`：Product Analyst、產品分析、產品數據分析、產品資料分析、
     Product Data Analyst、Growth Product Analyst、成長產品分析、Product Operations Analyst、
     產品營運分析
   - `Analytics / Data / BI`：Data Analyst、數據分析師、用戶行為分析

完整的 147 個關鍵字保留在 `Job_taxonomy_forsearch_full.csv`，作為未來擴大範圍的備份。
`.github/workflows/cleaner-weekly.yml` 目前也只留 1 個 shard，對應縮小後的關鍵字量。

### 之後要擴大或改變範圍時
1. 確認目前範圍的爬蟲穩定（沒有頻繁觸發 fake 404 / block）。
2. 從 `Job_taxonomy_forsearch_full.csv`（完整 147 個）或某個 `*_backup.csv`
   快照，把想要的職能大類 / 關鍵字複製回 `Job_taxonomy_forsearch.csv`。
3. 視新的關鍵字總數，調整 `cleaner-weekly.yml` 的 `matrix.include`
   （每個 shard 抓 15-20 個關鍵字比較安全，超過就多加一個 shard）。

## 清空全部資料（危險操作）

`Weekly 104 Full Detail Pipeline`（`cleaner-weekly.yml`）手動觸發時，多了一個
`truncate_before_run` 勾選框（預設關閉）。勾選後，workflow 會先跑 `clear-data`
這個 job，執行 `clear_supabase_data.py` 把 `job_posting` + `jd_raw` **兩張表的
全部資料清空**，清空成功才會繼續往下跑 `scrape-104` / `cleaner`；沒勾選則
`clear-data` 這個 job 會直接跳過清空那個 step，其他流程照常執行，不受影響。

⚠️ 這個操作不可復原，觸發前務必再三確認 Secrets 裡的 `SUPABASE_URL` 指向的是
正確的專案。

## LLM 輔助功能（Gemini）

`cleaner.py` 目前的職能分類 / 技能抽取仍是規則式（rule-based），沒有呼叫 LLM；
`GEMINI_API_KEY` 目前只用在使用者端的 CV Fitting Tool，作為輔助使用者的功能：

- 位置：`pages/3_CV_Fitting_Tool.py` 的「🤖 AI 智能建議（Gemini）」區塊
- 邏輯封裝在 `utils/llm_advisor.py`，用既有的 `requests` 直接呼叫 Gemini REST API，
  沒有額外引入 SDK 依賴
- 輸入是頁面本來就會算的 `llm_ready_diagnosis_payload`（fit score、matched/gap skills、
  技能證據權重等結構化資料），輸出是 `best_fit_role / why_fit / key_skill_evidence /
  biggest_gap / rewrite_suggestions / next_learning_actions`
- 沒有設定 `GEMINI_API_KEY`，或呼叫失敗時，頁面會自動 fallback 回原本的規則式建議，
  不會噴錯或空白
