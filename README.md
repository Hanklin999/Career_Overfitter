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
