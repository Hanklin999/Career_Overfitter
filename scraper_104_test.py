#!/usr/bin/env python3
"""
scraper_104_test.py — 從 104 爬取 Testing 類職缺，存入 Supabase jd_raw
- 使用 Job_taxonomy_forsearch.csv 產生中英混合關鍵字
- 每個關鍵字最多抓 2 頁
- 預設會抓列表 + 詳情（job_description 等），再寫入 jd_raw
"""

import argparse
import os
import json
import time
import random
from datetime import datetime, timezone
from pathlib import Path

import requests
import pandas as pd
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed


# ── 讀取 .env ─────────────────────────────────────────────────
load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("請在 .env 中設定 SUPABASE_URL 與 SUPABASE_KEY")

SUPA_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json; charset=utf-8",
    "Accept": "application/json",
    "Prefer": "resolution=merge-duplicates",
}

# ── 104 API 設定 ─────────────────────────────────────────────
MAX_PAGES = 2  # 你指定每個關鍵字最多 2 頁

LIST_API = "https://www.104.com.tw/jobs/search/api/jobs"
DETAIL_API_TPL = "https://www.104.com.tw/job/ajax/content/%s"

PERIOD_MAP = {
    "0": None,
    "1": "1",
    "2": "1~3",
    "3": "3~5",
    "4": "5~10",
    "5": "10+",
}

# ── Session ─────────────────────────────────────────────────
crawler = requests.Session()
crawler.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8",
    "Referer": "https://www.104.com.tw/jobs/search/",
})

# 暖機請求（取得必要 cookie）
try:
    crawler.get("https://www.104.com.tw/jobs/search/", timeout=10)
except Exception as e:
    print("⚠️ 104 暖機請求失敗（可能稍後會影響列表抓取）:", e)


# ── Keyword Loader：從 Job_taxonomy_forsearch.csv 載入 Testing 關鍵字 ──
ROOT_DIR = Path(__file__).resolve().parent
SEARCH_TAXONOMY_PATH = ROOT_DIR / "Job_taxonomy_forsearch.csv"


def load_keywords_for_testing() -> dict:
    """
    從 Job_taxonomy_forsearch.csv 讀取 job_parent_category = 'Testing'
    回傳格式：
    {
        "Testing": [ "測試工程師", "Test Engineer", "QA", ... ]
    }
    """
    if not SEARCH_TAXONOMY_PATH.exists():
        raise FileNotFoundError(f"找不到 Job_taxonomy_forsearch.csv: {SEARCH_TAXONOMY_PATH}")

    df = pd.read_csv(SEARCH_TAXONOMY_PATH)

    cols = list(df.columns)
    if len(cols) < 4:
        raise ValueError(f"Job_taxonomy_forsearch.csv 欄位數不足，實際欄位: {cols}")

    parent_col = cols[0]      # job_parent_category
    skill_name_col = cols[2]  # job_skill_name
    keyword_col = cols[3]     # 中英混合關鍵字

    sub = df[df[parent_col] == "Testing"].copy()
    if sub.empty:
        raise ValueError("在 Job_taxonomy_forsearch.csv 中找不到 job_parent_category = 'Testing' 的資料")

    keywords_set = set()

    for _, row in sub.iterrows():
        role_name = str(row[skill_name_col]).strip()
        if role_name:
            keywords_set.add(role_name)

        raw_kw = str(row[keyword_col] or "").strip()
        if raw_kw:
            # 支援全形 / 半形逗號
            parts = [p.strip() for p in raw_kw.replace("，", ",").split(",") if p.strip()]
            for p in parts:
                keywords_set.add(p)

    keywords = sorted(keywords_set)

    return {"Testing": keywords}


# ── Supabase jd_raw helpers ─────────────────────────────────
def truncate_jd_raw() -> None:
    try:
        r = requests.delete(
            f"{SUPABASE_URL}/jd_raw",
            headers={**SUPA_HEADERS, "Prefer": "count=exact"},
            params={"job_url": "neq.null"},
            timeout=30,
        )
        print("truncate jd_raw: HTTP %d | %s" % (r.status_code, r.text[:200]))
        r.raise_for_status()
    except Exception as e:
        print("⚠️ 清空 jd_raw 失敗:", e)
        raise


def count_jd_raw() -> int:
    r = requests.get(
        f"{SUPABASE_URL}/jd_raw",
        headers={**SUPA_HEADERS, "Prefer": "count=exact"},
        params={"select": "job_url", "limit": 1},
        timeout=30,
    )
    r.raise_for_status()
    return int(r.headers.get("Content-Range", "0-0/0").split("/")[-1])


def chunked(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def save_to_supabase(jobs: list) -> None:
    if not jobs:
        print("⚠️ 沒有資料需要寫入 Supabase")
        return

    now_iso = datetime.now(timezone.utc).isoformat()
    # 以 job_no 去重
    deduped = {j["job_no"]: j for j in jobs if j.get("job_no")}
    records = []

    for job in deduped.values():
        records.append({
            "job_no": job.get("job_no"),
            "source": job.get("source"),
            "category": job.get("category"),
            "keyword": job.get("keyword"),
            "title": job.get("title"),
            "company": job.get("company"),
            "location": job.get("location"),
            "industry": job.get("industry"),
            "is_foreign": job.get("is_foreign"),
            "is_listed": job.get("is_listed"),
            "job_url": job.get("job_url"),
            "period": job.get("period"),
            "appear_date": job.get("appear_date"),
            "salary_low": job.get("salary_low"),
            "salary_high": job.get("salary_high"),
            "remote_work": job.get("remote_work"),
            "welfare_tags": job.get("welfare_tags"),
            "description_snippet": job.get("description_snippet"),
            "skill": job.get("skill"),
            "specialty": job.get("specialty"),
            "work_exp": job.get("work_exp"),
            "edu": job.get("edu"),
            "job_description": job.get("job_description"),
            "job_category": job.get("job_category"),
            "manage_resp": job.get("manage_resp"),
            "scraped_at": now_iso,
        })

    success = fail = 0
    for idx, batch in enumerate(chunked(records, 100), start=1):
        try:
            body = json.dumps(batch, ensure_ascii=False).encode("utf-8")
            r = requests.post(
                f"{SUPABASE_URL}/jd_raw",
                headers=SUPA_HEADERS,
                data=body,
                timeout=30,
            )
            if r.status_code in (200, 201):
                success += len(batch)
                print(" batch %d (%d 筆) ✅" % (idx, len(batch)))
            else:
                fail += len(batch)
                print(" batch %d HTTP %d: %s" % (idx, r.status_code, r.text[:300]))
        except Exception as e:
            fail += len(batch)
            print(" batch %d 例外: %s" % (idx, e))

    print("\n✅ jd_raw 寫入：%d 成功 / %d 失敗" % (success, fail))


# ── Phase 1：列表 API ────────────────────────────────────────
def fetch_list(keyword: str, category: str, max_pages: int = MAX_PAGES) -> list:
    jobs = []

    for page in range(1, max_pages + 1):
        try:
            resp = crawler.get(
                LIST_API,
                params={
                    "keyword": keyword,
                    "order": "15",  # 依照更新時間排序
                    "asc": "0",
                    "page": str(page),
                    "mode": "s",
                    "ro": "0",
                },
                timeout=20,
            )
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"[{keyword}] page {page} 連線失敗: {e}")
            break

        if "application/json" not in resp.headers.get("Content-Type", ""):
            print(f"[{keyword}] page {page} 非 JSON 回應，停止")
            break

        data = resp.json()
        job_list = data.get("data", [])
        total_p = int(data.get("metadata", {}).get("pagination", {}).get("lastPage", 1))

        if not job_list:
            print(f"[{keyword}] page {page} 無資料，停止")
            break

        for item in job_list:
            link = item.get("link", {}).get("job", "")
            job_url = ("https://" + link) if link and not link.startswith("http") else link
            job_url = job_url.split("?")[0].rstrip("/")
            jobshort = job_url.split("/")[-1]

            raw_tags = item.get("tags", {}) or {}
            tags_dict = {}
            welfare_tags = []
            if isinstance(raw_tags, dict):
                for key, val in raw_tags.items():
                    desc = val.get("desc", "") if isinstance(val, dict) else str(val)
                    tags_dict[key] = desc
                    if key.startswith("wf") and desc:
                        welfare_tags.append(desc)

            is_foreign = "zoneForeign" in tags_dict
            is_listed = "zone" in tags_dict

            sal_low = item.get("salaryLow")
            sal_high = item.get("salaryHigh")

            jobs.append({
                "job_no": item.get("jobNo", ""),
                "jobshort": jobshort,
                "job_url": job_url,
                "keyword": keyword,
                "category": category,
                "source": "104",
                "title": item.get("jobName", ""),
                "company": item.get("custName", ""),
                "location": item.get("jobAddrNoDesc", ""),
                "industry": item.get("coIndustryDesc", ""),
                "is_foreign": is_foreign,
                "is_listed": is_listed,
                "period": PERIOD_MAP.get(item.get("period", "0")),
                "appear_date": item.get("appearDate", ""),
                "salary_low": sal_low if (sal_low or 0) < 9_000_000 else None,
                "salary_high": sal_high if (sal_high or 0) < 9_000_000 else None,
                "remote_work": item.get("remoteWorkType", 0),
                "welfare_tags": welfare_tags,
                "description_snippet": item.get("description", ""),
                "skill": None,
                "specialty": None,
                "work_exp": None,
                "edu": None,
                "job_description": None,
                "job_category": None,
                "manage_resp": None,
            })

        print(f" [{keyword}] page {page}/{min(max_pages, total_p)} +{len(job_list)} = {len(jobs)}")

        if page >= total_p:
            print(f" [{keyword}] 已到最後一頁")
            break

        time.sleep(random.uniform(0.2, 0.6))

    return jobs


# ── Phase 2：詳情 API ────────────────────────────────────────
def enrich_detail(job: dict) -> dict:
    jobshort = job.get("jobshort", "")
    job_url = job.get("job_url", "")
    if not jobshort:
        return job

    try:
        detail_url = DETAIL_API_TPL % jobshort
        resp = crawler.get(
            detail_url,
            headers={"Referer": job_url},
            timeout=20,
        )
        resp.raise_for_status()

        if "application/json" not in resp.headers.get("Content-Type", ""):
            print(
                f" [jobshort={jobshort}] 非 JSON 回應, "
                f"status={resp.status_code}, content-type={resp.headers.get('Content-Type','')}, body={resp.text[:200]}"
            )
            return job

        data = resp.json().get("data", {}) or {}
        condition = data.get("condition", {}) or {}
        detail = data.get("jobDetail", {}) or {}

        job["skill"] = [s["description"] for s in condition.get("skill", []) if s.get("description")]
        job["specialty"] = [s["description"] for s in condition.get("specialty", []) if s.get("description")]
        job["work_exp"] = str(condition.get("workExp", "")) or None
        job["edu"] = str(condition.get("edu", "")) or None
        job["job_description"] = detail.get("jobDescription", "")
        job["job_category"] = [c["description"] for c in detail.get("jobCategory", []) if c.get("description")]
        job["manage_resp"] = detail.get("manageResp", "")
    except Exception as e:
        print(f" [jobshort={jobshort}] detail 失敗: {e}")

    return job


def enrich_details_parallel(jobs: list, max_workers: int = 5) -> list:
    """
    平行抓取 JD 詳情。
    - jobs: unique_jobs list
    - max_workers: 建議先 5，太高可能提高被 104 擋的風險
    """
    if not jobs:
        return jobs

    enriched_jobs = [None] * len(jobs)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {
            executor.submit(enrich_detail, job): idx
            for idx, job in enumerate(jobs)
        }

        completed = 0
        total = len(jobs)

        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                enriched_jobs[idx] = future.result()
            except Exception as e:
                print(f" [idx={idx}] detail 平行抓取失敗: {e}")
                enriched_jobs[idx] = jobs[idx]

            completed += 1
            if completed % 20 == 0 or completed == total:
                print(f"  detail 進度 {completed}/{total}")

    return enriched_jobs



# ── CLI args ─────────────────────────────────────────────────
def parse_args():
    parser = argparse.ArgumentParser(description="104 Testing Job Scraper")
    parser.add_argument(
        "--truncate",
        action="store_true",
        help="執行前清空 jd_raw（測試階段建議只在第一次跑時加上）",
    )
    return parser.parse_args()


# ── main ─────────────────────────────────────────────────────
def main():
    args = parse_args()

    print("=" * 60)
    print("🕷️ 104 Scraper 啟動 | category = Testing")
    print("=" * 60)

    if args.truncate:
        print("🗑️ 清空 jd_raw...")
        truncate_jd_raw()
        remaining = count_jd_raw()
        print("truncate 後 jd_raw 剩餘筆數:", remaining)
        if remaining != 0:
            raise RuntimeError("jd_raw 沒有清空，停止後續寫入")

    # Step 1：載入 Testing 關鍵字
    kw_groups = load_keywords_for_testing()
    testing_keywords = kw_groups["Testing"]
    print(f"\n📂 [Testing] 關鍵字數量：{len(testing_keywords)}")
    print("   範例關鍵字：", testing_keywords[:10])

    all_jobs = []
    category = "Testing"

    # Step 2：列表爬蟲
    print("\n🔎 Phase 1：列表 API 抓取...")
    for kw in testing_keywords:
        print("\n🔍 Keyword =", kw)
        jobs = fetch_list(kw, category=category, max_pages=MAX_PAGES)
        all_jobs.extend(jobs)
        time.sleep(random.uniform(0.2, 0.6))

    # 去重
    deduped = {j["job_no"]: j for j in all_jobs if j.get("job_no")}
    unique_jobs = list(deduped.values())
    print("\n✅ 共爬取 %d 筆（含重複），去重後 %d 筆" % (len(all_jobs), len(unique_jobs)))

    # Step 3：詳情補齊
    print("\n🔎 Phase 2：抓取 JD 詳情...")
    unique_jobs = enrich_details_parallel(unique_jobs, max_workers=5)

    
    # Step 4：寫入 Supabase jd_raw
    print("\n💾 存入 Supabase jd_raw...")
    save_to_supabase(unique_jobs)
    print("\n🎉 Scraper 完成！")


if __name__ == "__main__":
    main()