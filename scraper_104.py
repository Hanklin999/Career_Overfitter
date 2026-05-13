#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
104 職缺爬蟲：全公司 + 全 detail + keyword chunking 版

設計重點：
1. 固定讀取 Job_taxonomy_forsearch.csv 作為 keyword source。
2. 預設抓全部公司，不做外商 / 上市上櫃過濾。
3. 支援 --keyword-offset / --keyword-limit，讓 GitHub Actions matrix 分段跑。
4. 預設補 detail；只有指定 --skip-detail 才跳過 detail。
5. 支援 --detail-limit，避免單一 chunk 補 detail 過久。0 代表不限制。
6. 寫入 Supabase 時使用 upsert；list-only row 不會覆蓋既有 detail 欄位為 NULL。
"""

import argparse
import json
import os
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("請在 .env 或 GitHub Secrets 中設定 SUPABASE_URL 與 SUPABASE_KEY")

SUPA_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates",
}

ROOT = Path(__file__).resolve().parent
KEYWORDS_CSV = "Job_taxonomy_forsearch.csv"

LIST_API = "https://www.104.com.tw/jobs/search/api/jobs"
DETAIL_API_TPL = "https://www.104.com.tw/job/ajax/content/%s"

PERIOD_MAP = {
    0: None,
    1: "1",
    2: "1~3",
    3: "3~5",
    4: "5~10",
    5: "10+",
}

# 全公司 + detail 版：每個 chunk 很小，所以 sleep 不需要太激進。
DEFAULT_LIST_SLEEP_MIN = 0.8
DEFAULT_LIST_SLEEP_MAX = 1.5

DEFAULT_DETAIL_SLEEP_MIN = 0.8
DEFAULT_DETAIL_SLEEP_MAX = 1.8

DEFAULT_KEYWORD_SLEEP_MIN = 1.5
DEFAULT_KEYWORD_SLEEP_MAX = 3.0

BATCH_SIZE = 100
BATCH_SLEEP_MIN = 15.0
BATCH_SLEEP_MAX = 30.0

DEFAULT_BACKOFF_BASE = 10.0
DEFAULT_MAX_PAGES = 5
DEFAULT_MAX_RETRIES = 4
DEFAULT_TIMEOUT = 25
DEFAULT_PAST_DAYS = 30

FAKE_404_THRESHOLD = 3
FAKE_404_PAUSE = 1800  # 30 minutes

crawler: Optional[requests.Session] = None
_consecutive_fake_404 = 0


def build_session() -> requests.Session:
    """建立 Session，先打 104 搜尋頁取得 cookie。"""
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


def get_session() -> requests.Session:
    global crawler
    if crawler is None:
        crawler = build_session()
    return crawler


def is_fake_404(resp: requests.Response) -> bool:
    """104 被擋時有機會回 fake 404；只在 body 出現封鎖語彙時判定。"""
    if resp.status_code != 404:
        return False

    body = resp.text or ""
    blocked_keywords = ["403", "使用者權限", "Forbidden", "Access Denied", "blocked"]
    return any(kw in body for kw in blocked_keywords)


def polite_sleep(low: float, high: float) -> None:
    time.sleep(random.uniform(low, high))


def chunked(seq: Sequence[Dict], size: int) -> Iterable[Sequence[Dict]]:
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
    global _consecutive_fake_404, crawler

    for attempt in range(max_retries):
        try:
            resp = session.request(method, url, **kwargs)

            if is_fake_404(resp):
                _consecutive_fake_404 += 1
                print(f"🚨 疑似假 404 / 被擋 #{_consecutive_fake_404}: {url}")

                if _consecutive_fake_404 >= FAKE_404_THRESHOLD:
                    print(f"🛑 連續 {FAKE_404_THRESHOLD} 次疑似被擋，暫停 {FAKE_404_PAUSE / 60:.0f} 分鐘...")
                    time.sleep(FAKE_404_PAUSE)
                    _consecutive_fake_404 = 0
                    crawler = build_session()
                    session = crawler

                wait = DEFAULT_BACKOFF_BASE * (2 ** attempt) + random.uniform(1, 3)
                time.sleep(wait)
                continue

            if resp.status_code == 404:
                _consecutive_fake_404 = 0
                resp.raise_for_status()

            if resp.status_code in (429, 500, 502, 503, 504):
                _consecutive_fake_404 = 0
                wait = DEFAULT_BACKOFF_BASE * (2 ** attempt) + random.uniform(1, 3)
                print(f"⚠️ HTTP {resp.status_code}，等待 {wait:.1f}s 後重試: {url}")
                time.sleep(wait)
                continue

            _consecutive_fake_404 = 0
            resp.raise_for_status()
            return resp

        except requests.exceptions.HTTPError as e:
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

    # 104 ajax content 通常吃職缺 URL 最後一段短碼，不吃 list API 的數字 jobNo。
    job_no = job_url.split("/")[-1].strip()
    if not job_no:
        return None

    raw_tags = item.get("tags") or {}
    tags_dict = raw_tags if isinstance(raw_tags, dict) else {}

    welfare_tags = []
    for k, v in tags_dict.items():
        desc = v.get("desc") if isinstance(v, dict) else str(v)
        if k.startswith("wf") and desc:
            welfare_tags.append(desc)

    salary_low = item.get("salaryLow")
    salary_high = item.get("salaryHigh")
    if salary_low and salary_low > 9_000_000:
        salary_low = None
    if salary_high and salary_high > 9_000_000:
        salary_high = None

    return {
        "job_no": str(job_no),
        "source": "104",
        "category": "all_jobs",
        "keyword": keyword,
        "title": item.get("jobName"),
        "company": item.get("custName"),
        "location": item.get("jobAddrNoDesc"),
        "industry": item.get("coIndustryDesc"),
        "is_foreign": bool(tags_dict.get("zoneForeign")),
        "is_listed": bool(tags_dict.get("zone")),
        "job_url": job_url,
        "period": PERIOD_MAP.get(item.get("period"), None),
        "appear_date": item.get("appearDate"),
        "salary_low": salary_low,
        "salary_high": salary_high,
        "remote_work": item.get("remoteWorkType", 0),
        "welfare_tags": welfare_tags,
        "description_snippet": item.get("description"),
        "skill": None,
        "specialty": None,
        "work_exp": None,
        "edu": None,
        "job_description": None,
        "job_category": None,
        "manage_resp": None,
    }


def normalize_keyword(value: object) -> str:
    return str(value or "").strip().replace("，", ",")


def load_crawler_keywords() -> List[str]:
    path = ROOT / KEYWORDS_CSV
    if not path.exists():
        raise FileNotFoundError(f"找不到 keyword 檔案：{path}")

    df = pd.read_csv(path, encoding="utf-8-sig").fillna("")

    if "keyword" in df.columns:
        keyword_col = "keyword"
    elif len(df.columns) >= 4:
        keyword_col = df.columns[3]
    else:
        raise ValueError(f"{KEYWORDS_CSV} 欄位不足，無法辨識 keyword 欄位")

    keywords = set()
    for _, row in df.iterrows():
        raw = normalize_keyword(row.get(keyword_col, ""))
        if not raw:
            continue

        for part in raw.split(","):
            kw = part.strip()
            if kw:
                keywords.add(kw)

    result = sorted(keywords)
    print(f"📌 keyword source = {KEYWORDS_CSV} | unique keywords = {len(result)}")
    return result


def fetch_list(keyword: str, max_pages: int, past_days: int) -> List[Dict]:
    jobs: List[Dict] = []
    session = get_session()

    for page in range(1, max_pages + 1):
        try:
            resp = request_with_backoff(
                session,
                "GET",
                LIST_API,
                params={
                    "keyword": keyword,
                    "order": "15",
                    "asc": "0",
                    "page": str(page),
                    "mode": "s",
                    "ro": "0",
                    "jobsource": "index_s",
                    "hotJob": "0",
                    "keywordType": "label",
                    "searchJobs": "1",
                    "pageSize": "20",
                    "past": str(past_days),
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
        job_list = data.get("data") or []
        total_pages = int((((data.get("metadata") or {}).get("pagination") or {}).get("lastPage")) or 1)

        if not job_list:
            print(f"[{keyword}] page {page} 無資料，停止")
            break

        page_added = 0
        for item in job_list:
            parsed = parse_job_list_item(item, keyword)
            if parsed:
                jobs.append(parsed)
                page_added += 1

        print(
            f"[LIST] {keyword} page {page}/{min(max_pages, total_pages)} "
            f"-> page_jobs={len(job_list)} added={page_added} total={len(jobs)}"
        )

        if page >= total_pages:
            break

        polite_sleep(DEFAULT_LIST_SLEEP_MIN, DEFAULT_LIST_SLEEP_MAX)

    return jobs


def enrich_detail(job: Dict) -> Dict:
    job_no = job.get("job_no")
    job_url = job.get("job_url")
    if not job_no:
        return job

    session = get_session()

    try:
        resp = request_with_backoff(
            session,
            "GET",
            DETAIL_API_TPL % job_no,
            headers={"Referer": job_url or "https://www.104.com.tw/jobs/search/"},
            timeout=DEFAULT_TIMEOUT,
        )

        if "application/json" not in (resp.headers.get("Content-Type") or ""):
            print(f"[DETAIL] {job_no} 非 JSON，跳過")
            return job

        data = (resp.json() or {}).get("data") or {}
        condition = data.get("condition") or {}
        detail = data.get("jobDetail") or {}

        job["skill"] = [x.get("description") for x in (condition.get("skill") or []) if x.get("description")]
        job["specialty"] = [x.get("description") for x in (condition.get("specialty") or []) if x.get("description")]
        job["work_exp"] = str(condition.get("workExp") or "") or None
        job["edu"] = str(condition.get("edu") or "") or None
        job["job_description"] = detail.get("jobDescription")
        job["job_category"] = [x.get("description") for x in (detail.get("jobCategory") or []) if x.get("description")]
        job["manage_resp"] = detail.get("manageResp")

    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            print(f"[DETAIL] {job_no} 職缺已下架或 detail 不可用（404），跳過")
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
            prev = deduped[job_no]
            keywords = {
                str(prev.get("keyword") or "").strip(),
                str(job.get("keyword") or "").strip(),
            }
            prev["keyword"] = ", ".join(sorted([x for x in keywords if x]))
            prev["is_foreign"] = bool(prev.get("is_foreign")) or bool(job.get("is_foreign"))
            prev["is_listed"] = bool(prev.get("is_listed")) or bool(job.get("is_listed"))

    return list(deduped.values())


def get_existing_detail_job_nos() -> Set[str]:
    """只回傳已有 job_description 的 job_no，避免 list-only row 讓 detail 被跳過。"""
    existing: Set[str] = set()
    offset = 0

    while True:
        resp = requests.get(
            f"{SUPABASE_URL}/jd_raw",
            headers=SUPA_HEADERS,
            params={
                "select": "job_no",
                "job_description": "not.is.null",
                "limit": "1000",
                "offset": str(offset),
            },
            timeout=30,
        )
        resp.raise_for_status()
        rows = resp.json()

        if not rows:
            break

        existing.update(r["job_no"] for r in rows if r.get("job_no"))
        offset += 1000

        if len(rows) < 1000:
            break

    return existing


def build_supabase_record(job: Dict, include_detail_fields: bool) -> Dict:
    now_iso = datetime.now(timezone.utc).isoformat()

    record = {
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
        "scraped_at": now_iso,
    }

    if include_detail_fields:
        for field in ["skill", "specialty", "work_exp", "edu", "job_description", "job_category", "manage_resp"]:
            value = job.get(field)
            record[field] = value if value not in ("", []) else None

    return record


def save_to_supabase(jobs: List[Dict], *, include_detail_fields: bool) -> None:
    if not jobs:
        print("⚠️ 沒有資料需要寫入 jd_raw")
        return

    records = [
        build_supabase_record(job, include_detail_fields=include_detail_fields)
        for job in jobs
        if job.get("job_no")
    ]

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
                print(f"[UPSERT] batch {idx} HTTP {resp.status_code}: {resp.text[:500]}")

        except Exception as e:
            fail += len(batch)
            print(f"[UPSERT] batch {idx} error: {e}")

    print(f"✅ jd_raw 寫入完成: success={ok}, fail={fail}")


def truncate_jd_raw() -> None:
    resp = requests.delete(
        f"{SUPABASE_URL}/jd_raw",
        headers={**SUPA_HEADERS, "Prefer": "count=exact"},
        params={"job_url": "neq.null"},
        timeout=60,
    )
    print(f"truncate jd_raw: HTTP {resp.status_code} | {resp.text[:300]}")
    resp.raise_for_status()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="104 all-company full-detail scraper -> jd_raw")

    p.add_argument("--truncate", action="store_true", help="清空 jd_raw 後重抓")
    p.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES, help="每個 keyword 最多抓幾頁")
    p.add_argument("--past-days", type=int, default=DEFAULT_PAST_DAYS, help="抓近 N 天職缺")
    p.add_argument("--keyword-offset", type=int, default=0, help="從第幾個 keyword 開始抓，用於 GitHub Actions chunking")
    p.add_argument("--keyword-limit", type=int, default=0, help="只抓 N 個 keyword；0=不限制")
    p.add_argument("--skip-detail", action="store_true", help="只抓列表，不補 detail")
    p.add_argument("--detail-limit", type=int, default=0, help="本 chunk 最多補幾筆 detail；0=不限制")

    # 保留相容性：目前預設就是全公司，所以這個 flag 不做任何過濾邏輯。
    p.add_argument("--include-all-companies", action="store_true", help="相容舊 workflow；目前預設即為全公司")
    p.add_argument("--detail-all", action="store_true", help="相容舊參數；目前預設即為補所有 pending detail")

    return p.parse_args()


def main() -> None:
    args = parse_args()

    keywords = load_crawler_keywords()

    if args.keyword_offset > 0:
        keywords = keywords[args.keyword_offset:]

    if args.keyword_limit and args.keyword_limit > 0:
        keywords = keywords[:args.keyword_limit]

    print("=" * 72)
    print(
        "Scraper start | "
        f"keyword_offset={args.keyword_offset} | keywords={len(keywords)} | "
        f"max_pages={args.max_pages} | past_days={args.past_days} | "
        f"all_companies=True | skip_detail={args.skip_detail} | detail_limit={args.detail_limit}"
    )
    print("=" * 72)

    if args.truncate:
        truncate_jd_raw()

    all_jobs: List[Dict] = []
    for i, kw in enumerate(keywords, start=1):
        print("-" * 72)
        print(f"[{i}/{len(keywords)}] keyword = {kw}")
        jobs = fetch_list(kw, max_pages=args.max_pages, past_days=args.past_days)
        all_jobs.extend(jobs)
        polite_sleep(DEFAULT_KEYWORD_SLEEP_MIN, DEFAULT_KEYWORD_SLEEP_MAX)

    unique_jobs = deduplicate_jobs(all_jobs)
    print(f"list jobs={len(all_jobs)} | unique job_no={len(unique_jobs)}")
    print(f"全部職缺（不限公司類型）: {len(unique_jobs)} 筆")

    include_detail_fields = False

    if not args.skip_detail:
        existing_detail_nos = get_existing_detail_job_nos()
        print(f"已有 detail 的 job_no: {len(existing_detail_nos)}")

        pending = [j for j in unique_jobs if j["job_no"] not in existing_detail_nos]

        if args.detail_limit and args.detail_limit > 0:
            pending = pending[:args.detail_limit]

        print(f"待抓 detail: {len(pending)} 筆")
        pending_nos = {j["job_no"] for j in pending}

        for idx, job in enumerate(pending, start=1):
            enrich_detail(job)
            print(f"[DETAIL] {idx}/{len(pending)} {job['job_no']} ✓")

            polite_sleep(DEFAULT_DETAIL_SLEEP_MIN, DEFAULT_DETAIL_SLEEP_MAX)

            if idx % BATCH_SIZE == 0:
                pause = random.uniform(BATCH_SLEEP_MIN, BATCH_SLEEP_MAX)
                print(f"💤 已抓 {idx} 筆，批次休息 {pause / 60:.1f} 分鐘...")
                time.sleep(pause)

        # 只有這次有真的補 detail，才把 detail 欄位送進 upsert。
        include_detail_fields = bool(pending_nos)

    save_to_supabase(unique_jobs, include_detail_fields=include_detail_fields)
    print("✅ Scraper 完成")


if __name__ == "__main__":
    main()
