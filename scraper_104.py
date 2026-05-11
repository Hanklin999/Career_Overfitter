#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import os
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("請在 .env 中設定 SUPABASE_URL 與 SUPABASE_KEY")

SUPA_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates",
}

ROOT = Path(__file__).resolve().parent.parent if Path(__file__).resolve().parent.name == 'output' else Path(__file__).resolve().parent
KEYWORDS_CSV_CANDIDATES = [
    "crawler_keywords_compressed.csv",
    "Job_taxonomy_forsearch.csv",
]

LIST_API = "https://www.104.com.tw/jobs/search/api/jobs"
DETAIL_API_TPL = "https://www.104.com.tw/job/ajax/content/%s"

PERIOD_MAP = {
    0: None, 1: "1", 2: "1~3", 3: "3~5", 4: "5~10", 5: "10+",
}

# ── 速度設定（保守版，不容易被封）────────────────────────────────
DEFAULT_LIST_SLEEP_MIN    = 3.0    # 列表頁之間
DEFAULT_LIST_SLEEP_MAX    = 7.0
DEFAULT_DETAIL_SLEEP_MIN  = 5.0    # detail 之間
DEFAULT_DETAIL_SLEEP_MAX  = 12.0
DEFAULT_KEYWORD_SLEEP_MIN = 8.0    # keyword 之間
DEFAULT_KEYWORD_SLEEP_MAX = 18.0
BATCH_SIZE                = 30     # 每幾筆 detail 大休息一次
BATCH_SLEEP_MIN           = 120.0  # 大休息 2~5 分鐘
BATCH_SLEEP_MAX           = 300.0

DEFAULT_BACKOFF_BASE  = 10.0
DEFAULT_MAX_PAGES     = 5
DEFAULT_MAX_RETRIES   = 4
DEFAULT_TIMEOUT       = 25
DEFAULT_PAST_DAYS     = 30

# 連續假 404 幾次就判定 IP 被封，暫停
FAKE_404_THRESHOLD    = 3
FAKE_404_PAUSE        = 1800  # 被封就暫停 30 分鐘


def resolve_existing_file(candidates: List[str]) -> Path:
    for name in candidates:
        p = ROOT / name
        if p.exists():
            return p
    raise FileNotFoundError(f"找不到任何候選檔案: {candidates}")


def build_session() -> requests.Session:
    """建立 Session，先打首頁讓 Cloudflare 設定 cookie"""
    s = requests.Session()
    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8",
        "Referer": "https://www.104.com.tw/jobs/search/",
    })
    try:
        warmup = s.get("https://www.104.com.tw/jobs/search/", timeout=10)
        print(f"🔥 暖機請求: HTTP {warmup.status_code}，cookie 已設定")
    except Exception as e:
        print(f"⚠️ 104 暖機請求失敗: {e}")
    return s


crawler = build_session()

# 連續假 404 計數器（全域）
_consecutive_fake_404 = 0


def is_fake_404(resp: requests.Response) -> bool:
    """
    104 被封時回 404，但 body 很短或含 403/權限字樣
    真正下架的 404 body 通常有 jobNo not found 之類的訊息
    """
    if resp.status_code != 404:
        return False
    body = resp.text
    if len(body) < 200:
        return True
    if any(kw in body for kw in ["403", "使用者權限", "Forbidden", "Access Denied", "blocked"]):
        return True
    return False


def polite_sleep(low: float, high: float):
    t = random.uniform(low, high)
    time.sleep(t)


def chunked(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def request_with_backoff(
    session: requests.Session,
    method: str,
    url: str,
    *,
    max_retries: int = DEFAULT_MAX_RETRIES,
    **kwargs,
) -> requests.Response:
    global _consecutive_fake_404

    for attempt in range(max_retries):
        try:
            resp = session.request(method, url, **kwargs)

            # ── 假 404 偵測（IP 被封）────────────────────────────
            if is_fake_404(resp):
                _consecutive_fake_404 += 1
                print(f"🚨 疑似假 404（IP 被封）#{_consecutive_fake_404}: {url}")
                if _consecutive_fake_404 >= FAKE_404_THRESHOLD:
                    print(f"🛑 連續 {FAKE_404_THRESHOLD} 次假 404，暫停 {FAKE_404_PAUSE/60:.0f} 分鐘...")
                    time.sleep(FAKE_404_PAUSE)
                    _consecutive_fake_404 = 0
                    # 重建 session 拿新 cookie
                    session = build_session()
                wait = DEFAULT_BACKOFF_BASE * (2 ** attempt) + random.uniform(1, 3)
                time.sleep(wait)
                continue

            # ── 真正的 404（職缺下架）────────────────────────────
            if resp.status_code == 404:
                _consecutive_fake_404 = 0  # 真 404 不計入
                resp.raise_for_status()    # 讓外層 catch 處理

            # ── 流量限制 / 伺服器錯誤────────────────────────────
            if resp.status_code in (429, 500, 502, 503, 504):
                _consecutive_fake_404 = 0
                wait = DEFAULT_BACKOFF_BASE * (2 ** attempt) + random.uniform(1, 3)
                print(f"⚠️ HTTP {resp.status_code}，等待 {wait:.1f}s 後重試: {url}")
                time.sleep(wait)
                continue

            # ── 成功────────────────────────────────────────────
            _consecutive_fake_404 = 0
            resp.raise_for_status()
            return resp

        except requests.exceptions.HTTPError as e:
            # 真 404 直接拋出，不重試
            if e.response is not None and e.response.status_code == 404:
                raise
            if attempt == max_retries - 1:
                raise
            wait = DEFAULT_BACKOFF_BASE * (2 ** attempt) + random.uniform(1, 3)
            print(f"⚠️ 請求失敗，等待 {wait:.1f}s 後重試: {e}")
            time.sleep(wait)

        except requests.exceptions.RequestException as e:
            if attempt == max_retries - 1:
                raise
            wait = DEFAULT_BACKOFF_BASE * (2 ** attempt) + random.uniform(1, 3)
            print(f"⚠️ 請求失敗，等待 {wait:.1f}s 後重試: {e}")
            time.sleep(wait)

    raise RuntimeError("request_with_backoff reached unexpected branch")


def parse_job_list_item(item: Dict, keyword: str) -> Optional[Dict]:
    link = ((item.get("link") or {}).get("job") if isinstance(item.get("link"), dict) else None) or item.get("link")
    if not link:
        return None
    job_url = f"https:{link}" if str(link).startswith("//") else str(link)
    job_url = job_url.split("?")[0].rstrip("/")
    job_no = item.get("jobNo") or job_url.split("/")[-1]
    if not job_no:
        return None

    raw_tags = item.get("tags") or {}
    welfare_tags = []
    tags_dict = raw_tags if isinstance(raw_tags, dict) else {}
    for k, v in tags_dict.items():
        desc = v.get("desc") if isinstance(v, dict) else str(v)
        if k.startswith("wf") and desc:
            welfare_tags.append(desc)

    is_foreign = bool(tags_dict.get("zoneForeign"))
    is_listed  = bool(tags_dict.get("zone"))

    salary_low  = item.get("salaryLow")
    salary_high = item.get("salaryHigh")
    if salary_low  and salary_low  > 9_000_000: salary_low  = None
    if salary_high and salary_high > 9_000_000: salary_high = None

    return {
        "job_no": str(job_no),
        "source": "104",
        "category": "all_jobs",
        "keyword": keyword,
        "title": item.get("jobName"),
        "company": item.get("custName"),
        "location": item.get("jobAddrNoDesc"),
        "industry": item.get("coIndustryDesc"),
        "is_foreign": is_foreign,
        "is_listed": is_listed,
        "job_url": job_url,
        "period": PERIOD_MAP.get(item.get("period"), None),
        "appear_date": item.get("appearDate"),
        "salary_low": salary_low,
        "salary_high": salary_high,
        "remote_work": item.get("remoteWorkType", 0),
        "welfare_tags": welfare_tags,
        "description_snippet": item.get("description"),
        "skill": None, "specialty": None, "work_exp": None,
        "edu": None, "job_description": None,
        "job_category": None, "manage_resp": None,
    }


def load_crawler_keywords() -> List[str]:
    path = resolve_existing_file(KEYWORDS_CSV_CANDIDATES)
    df = pd.read_csv(path, encoding="utf-8-sig").fillna("")

    if "keyword" in df.columns:
        keywords = [str(x).strip() for x in df["keyword"].tolist() if str(x).strip()]
        return sorted(set(keywords))

    if len(df.columns) >= 4:
        keyword_col = df.columns[3]
        keywords = set()
        for _, row in df.iterrows():
            raw = str(row.get(keyword_col, "")).strip()
            if not raw:
                continue
            for part in raw.replace("，", ",").split(","):
                part = part.strip()
                if part:
                    keywords.add(part)
        return sorted(keywords)

    raise ValueError(f"無法從 {path.name} 辨識 keyword 欄位")


def fetch_list(keyword: str, max_pages: int, past_days: int) -> List[Dict]:
    jobs: List[Dict] = []
    for page in range(1, max_pages + 1):
        try:
            resp = request_with_backoff(
                crawler, "GET", LIST_API,
                params={
                    "keyword": keyword, "order": "15", "asc": "0",
                    "page": str(page), "mode": "s", "ro": "0",
                    "jobsource": "index_s", "hotJob": "0",
                    "keywordType": "label", "searchJobs": "1",
                    "pageSize": "20", "past": str(past_days),
                },
                timeout=DEFAULT_TIMEOUT,
            )
        except Exception as e:
            print(f"[{keyword}] page {page} 列表抓取失敗: {e}")
            break

        if "application/json" not in (resp.headers.get("Content-Type") or ""):
            print(f"[{keyword}] page {page} 非 JSON 回應，停止")
            break

        data = resp.json()
        job_list    = data.get("data") or []
        total_pages = int((((data.get("metadata") or {}).get("pagination") or {}).get("lastPage")) or 1)

        if not job_list:
            print(f"[{keyword}] page {page} 無資料，停止")
            break

        for item in job_list:
            parsed = parse_job_list_item(item, keyword)
            if parsed:
                jobs.append(parsed)

        print(f"[LIST] {keyword} page {page}/{min(max_pages, total_pages)} -> page_jobs={len(job_list)} total={len(jobs)}")
        if page >= total_pages:
            break
        polite_sleep(DEFAULT_LIST_SLEEP_MIN, DEFAULT_LIST_SLEEP_MAX)
    return jobs


def enrich_detail(job: Dict) -> Dict:
    job_no  = job.get("job_no")
    job_url = job.get("job_url")
    if not job_no:
        return job

    try:
        resp = request_with_backoff(
            crawler, "GET",
            DETAIL_API_TPL % job_no,
            headers={"Referer": job_url or "https://www.104.com.tw/jobs/search/"},
            timeout=DEFAULT_TIMEOUT,
        )
        if "application/json" not in (resp.headers.get("Content-Type") or ""):
            print(f"[DETAIL] {job_no} 非 JSON，跳過")
            return job

        data      = (resp.json() or {}).get("data") or {}
        condition = data.get("condition") or {}
        detail    = data.get("jobDetail") or {}

        job["skill"]           = [x.get("description") for x in (condition.get("skill")      or []) if x.get("description")]
        job["specialty"]       = [x.get("description") for x in (condition.get("specialty")  or []) if x.get("description")]
        job["work_exp"]        = str(condition.get("workExp") or "") or None
        job["edu"]             = str(condition.get("edu")     or "") or None
        job["job_description"] = detail.get("jobDescription")
        job["job_category"]    = [x.get("description") for x in (detail.get("jobCategory")   or []) if x.get("description")]
        job["manage_resp"]     = detail.get("manageResp")

    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            print(f"[DETAIL] {job_no} 職缺已下架（真 404），跳過")
        else:
            print(f"[DETAIL] {job_no} 抓取失敗: {e}")
    except Exception as e:
        print(f"[DETAIL] {job_no} 抓取失敗: {e}")

    return job


def deduplicate_jobs(jobs: List[Dict]) -> List[Dict]:
    deduped: Dict[str, Dict] = {}
    for job in jobs:
        job_no = job.get("job_no")
        if not job_no:
            continue
        if job_no not in deduped:
            deduped[job_no] = job
        else:
            prev     = deduped[job_no]
            keywords = {str(prev.get("keyword") or "").strip(), str(job.get("keyword") or "").strip()}
            prev["keyword"] = ", ".join(sorted([x for x in keywords if x]))
    return list(deduped.values())


def get_existing_job_nos() -> set:
    existing = set()
    offset   = 0
    while True:
        resp = requests.get(
            f"{SUPABASE_URL}/jd_raw",
            headers=SUPA_HEADERS,
            params={"select": "job_no", "limit": 1000, "offset": offset},
            timeout=30,
        )
        rows = resp.json()
        if not rows:
            break
        existing.update(r["job_no"] for r in rows)
        offset += 1000
        if len(rows) < 1000:
            break
    return existing


def save_to_supabase(jobs: List[Dict]) -> None:
    if not jobs:
        print("⚠️ 沒有資料需要寫入 jd_raw")
        return
    now_iso = datetime.now(timezone.utc).isoformat()
    records = [{
        "job_no": job.get("job_no"),
        "source": job.get("source", "104"),
        "category": job.get("category", "all_jobs"),
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
    } for job in jobs]

    ok = fail = 0
    for idx, batch in enumerate(chunked(records, 100), start=1):
        try:
            resp = requests.post(
                f"{SUPABASE_URL}/jd_raw",
                headers=SUPA_HEADERS,
                params={"on_conflict": "job_no"},
                data=json.dumps(batch, ensure_ascii=False).encode("utf-8"),
                timeout=60,
            )
            if resp.status_code in (200, 201):
                ok += len(batch)
                print(f"[UPSERT] batch {idx} ok: {len(batch)}")
            else:
                fail += len(batch)
                print(f"[UPSERT] batch {idx} HTTP {resp.status_code}: {resp.text[:400]}")
        except Exception as e:
            fail += len(batch)
            print(f"[UPSERT] batch {idx} error: {e}")
    print(f"✅ jd_raw 寫入完成: success={ok}, fail={fail}")


def truncate_jd_raw():
    resp = requests.delete(
        f"{SUPABASE_URL}/jd_raw",
        headers={**SUPA_HEADERS, "Prefer": "count=exact"},
        params={"job_url": "neq.null"},
        timeout=60,
    )
    print(f"truncate jd_raw: HTTP {resp.status_code} | {resp.text[:200]}")
    resp.raise_for_status()


def parse_args():
    p = argparse.ArgumentParser(description="104 all-job scraper -> jd_raw")
    p.add_argument("--truncate",       action="store_true", help="清空 jd_raw 後重抓")
    p.add_argument("--max-pages",      type=int, default=DEFAULT_MAX_PAGES)
    p.add_argument("--past-days",      type=int, default=DEFAULT_PAST_DAYS)
    p.add_argument("--keyword-limit",  type=int, default=0, help="測試用，只取前 N 個 keyword；0=全部")
    p.add_argument("--skip-detail",    action="store_true", help="只抓列表，不補 detail")
    return p.parse_args()


def main():
    args     = parse_args()
    keywords = load_crawler_keywords()
    if args.keyword_limit and args.keyword_limit > 0:
        keywords = keywords[:args.keyword_limit]

    print("=" * 72)
    print(f"Scraper start | keywords={len(keywords)} | max_pages={args.max_pages} | past_days={args.past_days}")
    print("=" * 72)

    if args.truncate:
        truncate_jd_raw()

    # ── 抓列表 ────────────────────────────────────────────────────
    all_jobs: List[Dict] = []
    for i, kw in enumerate(keywords, start=1):
        print("-" * 72)
        print(f"[{i}/{len(keywords)}] keyword = {kw}")
        jobs = fetch_list(kw, max_pages=args.max_pages, past_days=args.past_days)
        all_jobs.extend(jobs)
        polite_sleep(DEFAULT_KEYWORD_SLEEP_MIN, DEFAULT_KEYWORD_SLEEP_MAX)

    unique_jobs = deduplicate_jobs(all_jobs)
    print(f"list jobs={len(all_jobs)} | unique job_no={len(unique_jobs)}")

    # ── 抓 detail ─────────────────────────────────────────────────
    if not args.skip_detail:
        existing_nos = get_existing_job_nos()
        print(f"已有 detail 的 job_no: {len(existing_nos)}")

        pending = [j for j in unique_jobs if j["job_no"] not in existing_nos]
        print(f"待抓 detail: {len(pending)} 筆")

        for idx, job in enumerate(pending, start=1):
            enrich_detail(job)
            print(f"[DETAIL] {idx}/{len(pending)} {job['job_no']} ✓")

            # 每筆之間隨機休息
            polite_sleep(DEFAULT_DETAIL_SLEEP_MIN, DEFAULT_DETAIL_SLEEP_MAX)

            # 每 BATCH_SIZE 筆大休息一次
            if idx % BATCH_SIZE == 0:
                pause = random.uniform(BATCH_SLEEP_MIN, BATCH_SLEEP_MAX)
                print(f"💤 已抓 {idx} 筆，批次休息 {pause/60:.1f} 分鐘...")
                time.sleep(pause)

    # ── 寫入 Supabase ─────────────────────────────────────────────
    save_to_supabase(unique_jobs)
    print("✅ Scraper 完成")


if __name__ == "__main__":
    main()
