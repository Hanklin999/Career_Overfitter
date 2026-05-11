# config_and_keywords.py
from dotenv import load_dotenv
import os
import pandas as pd
from pathlib import Path

# ── 載入 .env ───────────────────────────────────────────────
load_dotenv()  # 會從當前工作目錄開始往上找 .env

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("請在 .env 中設定 SUPABASE_URL 與 SUPABASE_KEY")


# ── 從 Job_taxonomy_forsearch.csv 讀取關鍵字 ─────────────────
ROOT_DIR = Path(__file__).resolve().parent  # 這個檔所在的資料夾
SEARCH_TAXONOMY_PATH = ROOT_DIR / "Job_taxonomy_forsearch.csv"


def load_keywords_for_category(category: str) -> dict:
    """
    從 Job_taxonomy_forsearch.csv 讀取指定 job_parent_category
    回傳格式：
    {
        "Consulting": ["商業分析師", "Business Analyst", "BA", "管理顧問", ...]
    }
    """
    if not SEARCH_TAXONOMY_PATH.exists():
        raise FileNotFoundError(f"找不到 Job_taxonomy_forsearch.csv: {SEARCH_TAXONOMY_PATH}")

    df = pd.read_csv(SEARCH_TAXONOMY_PATH)

    # 預期欄位：job_parent_category, job_sub_category, job_skill_name, <最後一欄是中英混合關鍵字> [file:57]
    cols = list(df.columns)
    if len(cols) < 4:
        raise ValueError(f"Job_taxonomy_forsearch.csv 欄位數不足，實際欄位: {cols}")
    
    parent_col = cols[0]               # job_parent_category
    skill_name_col = cols[2]          # job_skill_name
    keyword_col = cols[3]             # 例如 "GTM專員, 上市策略專員, Go-to-Market專員"

    # 只挑指定大類，例如 "Consulting"
    sub = df[df[parent_col] == category].copy()
    if sub.empty:
        raise ValueError(f"在 Job_taxonomy_forsearch.csv 中找不到 job_parent_category = {category} 的資料")

    keywords_set = set()

    for _, row in sub.iterrows():
        # 1) 加入英文職稱本身
        role_name = str(row[skill_name_col]).strip()
        if role_name:
            keywords_set.add(role_name)

        # 2) 把中英混合關鍵字欄位拆成多個 keyword
        raw_kw = str(row[keyword_col] or "").strip()
        if raw_kw:
            # 這裡假設你是用「逗號 + 可能空白」分隔，如 "商業分析師, Business Analyst, BA" [file:57]
            parts = [p.strip() for p in raw_kw.replace("，", ",").split(",") if p.strip()]
            for p in parts:
                keywords_set.add(p)

    keywords = sorted(keywords_set)

    return {category: keywords}


if __name__ == "__main__":
    print("SUPABASE_URL =", SUPABASE_URL)
    print("SUPABASE_KEY (前 10 碼) =", SUPABASE_KEY[:10])
    
    consulting_keywords = load_keywords_for_category("Consulting")
    print("\nConsulting 關鍵字共 %d 個：" % len(consulting_keywords["Consulting"]))
    print(consulting_keywords["Consulting"])