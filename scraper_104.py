#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
104 crawler: fixed-keyword taxonomy + all companies + full detail.

Keyword source is strictly:
- File name: Job_taxonomy_forsearch.csv
- Column name: keyword

No fallback. No other keyword file.
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
    raise RuntimeError("Missing SUPABASE_URL or SUPABASE_KEY")

SUPA_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates",
}

ROOT = Path(__file__).resolve().parent
KEYWORDS_CSV = "Job_taxonomy_forsearch.csv"

LIST_API = "https://www.104.com.tw/jobs/search/api/jobs"
DETAIL_API_TPL = "https://www.104.com.tw/job/ajax/content/{}"

PERIOD_MAP = {
    0: None,
    1: "1",
    2: "1~3",
    3: "3~5",
    4: "5~10",
    5: "10+",
}

# IMPORTANT:
# List/keyword crawling was not the bottleneck, so keep it fast.
LIST_SLEEP_MIN = 0.3
LIST_SLEEP_MAX = 0.8

KEYWORD_SLEEP_MIN = 0.5
KEYWORD_SLEEP_MAX = 1.0

# Detail is the slow/risky part, so only detail is throttled.
DETAIL_SLEEP_MIN = 1.5
DETAIL_SLEEP_MAX = 3.0

BATCH_SIZE = 50
BATCH_SLEEP_MIN = 30.0
BATCH_SLEEP_MAX = 60.0

DEFAULT_MAX_PAGES = 5
DEFAULT_PAST_DAYS = 30
DEFAULT_TIMEOUT = 25
DEFAULT_MAX_RETRIES = 4
DEFAULT_BACKOFF_BASE = 10.0

FAKE_404_THRESHOLD = 3
FAKE_404_PAUSE = 1800

crawler: Optional[requests.Session] = None
_consecutive_fake_404 = 0


def resolve_keywords_csv() -> Path:
    candidates = [
        Path.cwd() / KEYWORDS_CSV,
        ROOT / KEYWORDS_CSV,
    ]

    github_workspace = os.environ.get("GITHUB_WORKSPACE")
    if github_workspace:
        candidates.append(Path(github_workspace) / KEYWORDS_CSV)

    seen = set()
    for p in candidates:
        p = p.resolve()
        if p in seen:
            continue
        seen.add(p)

        if p.exists():
            print(f"📌 keyword file = {p}")
            return p

    checked = "\n".join(str(p.resolve()) for p in candidates)
    raise FileNotFoundError(
        f"Cannot find {KEYWORDS_CSV}. This crawler only reads this file.\nChecked:\n{checked}"
    )


def load_crawler_keywords() -> List[str]:
    path = resolve_keywords_csv()
    df = pd.read_csv(path, encoding="utf-8-sig").fillna("")

    if "keyword" not in df.columns:
        raise ValueError(f"{path.name} missing required column: keyword")

    keywords: List[str] = []
    for kw in df["keyword"].astype(str):
        kw = kw.strip()
        if kw:
            keywords.append(kw)

    # preserve file order, dedupe only exact duplicates
    keywords = list(dict.fromkeys(keywords))

    print(f"📌 keyword source = {path.name}")
    print(f"📌 keyword column = keyword")
    print(f"📌 keyword count = {len(keywords)}")
    print(f"📌 first 10 keywords = {keywords[:10]}")

    return keywords


def build_session() -> requests.Session:
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
        print(f"🔥 warmup status = {warmup.status_code}")
    except Exception as e:
        print(f"⚠️ warmup failed: {e}")

    return s


def get_session() -> requests.Session:
    global crawler
    if crawler is None:
        crawler = build_session()
    return crawler


def sleep_random(low: float, high: float) -> None:
    time.sleep(random.uniform(low, high))


def chunked(seq: Sequence[Dict], size: int) -> Iterable[Sequence[Dict]]:
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def is_fake_404(resp: requests.Response) -> bool:
    if resp.status_code != 404:
        return False

    body = resp.text or ""
    blocked_terms = ["403", "使用者權限", "Forbidden", "Access Denied", "blocked"]
    return any(t in body for t in blocked_terms)


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
                print(f"🚨 fake 404 / blocked #{_consecutive_fake_404}: {url}")

                if _consecutive_fake_404 >= FAKE_404_THRESHOLD:
                    print(f"🛑 blocked repeatedly; sleep {FAKE_404_PAUSE / 60:.0f} minutes")
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
                print(f"⚠️ HTTP {resp.status_code}; retry after {wait:.1f}s: {url}")
                time.sleep(wait)
                continue

            _consecutive_fake_404 = 0
            resp.raise_for_status()
            return resp

        except requests.exceptions.HTTPError:
            raise

        except requests.exceptions.RequestException as e:
            if attempt == max_retries - 1:
                raise

            wait = DEFAULT_BACKOFF_BASE * (2 ** attempt) + random.uniform(1, 3)
            print(f"⚠️ request failed; retry after {wait:.1f}s: {e}")
            time.sleep(wait)

    raise RuntimeError("request_with_backoff reached unexpected branch")


def parse_job_list_item(item: Dict, keyword: str) -> Optional[Dict]:
    raw_link = item.get("link")

    if isinstance(raw_link, dict):
        link = raw_link.get("job")
    else:
        link = raw_link

    if not link:
        return None

    job_url = f"https:{link}" if str(link).startswith("//") else str(link)
    job_url = job_url.split("?")[0].rstrip("/")

    # Use URL short id for detail endpoint.
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


def fetch_list(keyword: str, max_pages: int, past_days: int) -> List[Dict]:
    session = get_session()
    jobs: List[Dict] = []

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
            print(f"[{keyword}] page {page} list failed: {e}")
            break

        if "application/json" not in (resp.headers.get("Content-Type") or ""):
            print(f"[{keyword}] page {page} non-JSON response; stop")
            break

        data = resp.json()
        rows = data.get("data") or []
        total_pages = int((((data.get("metadata") or {}).get("pagination") or {}).get("lastPage")) or 1)

        if not rows:
            print(f"[{keyword}] page {page} empty; stop")
            break

        added = 0
        for item in rows:
            parsed = parse_job_list_item(item, keyword)
            if parsed:
                jobs.append(parsed)
                added += 1

        print(
            f"[LIST] {keyword} page {page}/{min(max_pages, total_pages)} "
            f"page_jobs={len(rows)} added={added} total={len(jobs)}"
        )

        if page >= total_pages:
            break

        sleep_random(LIST_SLEEP_MIN, LIST_SLEEP_MAX)

    return jobs


def enrich_detail(job: Dict) -> Dict:
    session = get_session()
    job_no = job.get("job_no")
    job_url = job.get("job_url")

    if not job_no:
        return job

    try:
        resp = request_with_backoff(
            session,
            "GET",
            DETAIL_API_TPL.format(job_no),
            headers={"Referer": job_url or "https://www.104.com.tw/jobs/search/"},
            timeout=DEFAULT_TIMEOUT,
        )

        if "application/json" not in (resp.headers.get("Content-Type") or ""):
            print(f"[DETAIL] {job_no} non-JSON; skip")
            return job

        data = (resp.json() or {}).get("data") or {}
        detail = data.get("jobDetail") or {}
        condition = data.get("condition") or {}

        job["job_description"] = detail.get("jobDescription")
        job["job_category"] = [x.get("description") for x in (detail.get("jobCategory") or []) if x.get("description")]
        job["manage_resp"] = detail.get("manageResp")

        job["skill"] = [x.get("description") for x in (condition.get("skill") or []) if x.get("description")]
        job["specialty"] = [x.get("description") for x in (condition.get("specialty") or []) if x.get("description")]
        job["work_exp"] = str(condition.get("workExp") or "") or None
        job["edu"] = str(condition.get("edu") or "") or None

    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            print(f"[DETAIL] {job_no} 404; skip")
        else:
            print(f"[DETAIL] {job_no} failed: {e}")

    except Exception as e:
        print(f"[DETAIL] {job_no} failed: {e}")

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
    now = datetime.now(timezone.utc).isoformat()

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
        "scraped_at": now,
    }

    if include_detail_fields:
        for field in ["skill", "specialty", "work_exp", "edu", "job_description", "job_category", "manage_resp"]:
            value = job.get(field)
            record[field] = value if value not in ("", []) else None

    return record


def save_to_supabase(jobs: List[Dict], *, include_detail_fields: bool) -> None:
    if not jobs:
        print("⚠️ no jobs to save")
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

    print(f"✅ jd_raw upsert done: success={ok}, fail={fail}")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="104 all-company full-detail scraper")

    p.add_argument("--truncate", action="store_true", help="Reserved. Not used by default.")
    p.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES)
    p.add_argument("--past-days", type=int, default=DEFAULT_PAST_DAYS)

    p.add_argument("--keyword-offset", type=int, default=0)
    p.add_argument("--keyword-limit", type=int, default=0)

    p.add_argument("--skip-detail", action="store_true")
    p.add_argument("--detail-limit", type=int, default=0)

    # kept for workflow compatibility; default behavior already includes all companies
    p.add_argument("--include-all-companies", action="store_true")

    return p.parse_args()


def main() -> None:
    args = parse_args()

    keywords = load_crawler_keywords()

    if args.keyword_offset > 0:
        keywords = keywords[args.keyword_offset:]

    if args.keyword_limit > 0:
        keywords = keywords[:args.keyword_limit]

    print("=" * 72)
    print(
        "Scraper start | "
        f"keyword_offset={args.keyword_offset} | keywords={len(keywords)} | "
        f"max_pages={args.max_pages} | past_days={args.past_days} | "
        f"all_companies=True | skip_detail={args.skip_detail} | detail_limit={args.detail_limit}"
    )
    print("=" * 72)

    all_jobs: List[Dict] = []
    for idx, kw in enumerate(keywords, start=1):
        print("-" * 72)
        print(f"[{idx}/{len(keywords)}] keyword = {kw}")

        jobs = fetch_list(kw, max_pages=args.max_pages, past_days=args.past_days)
        all_jobs.extend(jobs)

        sleep_random(KEYWORD_SLEEP_MIN, KEYWORD_SLEEP_MAX)

    unique_jobs = deduplicate_jobs(all_jobs)
    print(f"list jobs={len(all_jobs)} | unique job_no={len(unique_jobs)}")

    include_detail_fields = False

    if not args.skip_detail:
        existing_detail_nos = get_existing_detail_job_nos()
        print(f"已有 detail 的 job_no: {len(existing_detail_nos)}")

        pending = [j for j in unique_jobs if j["job_no"] not in existing_detail_nos]

        if args.detail_limit > 0:
            pending = pending[:args.detail_limit]

        print(f"待抓 detail: {len(pending)}")

        for idx, job in enumerate(pending, start=1):
            enrich_detail(job)
            print(f"[DETAIL] {idx}/{len(pending)} {job['job_no']} ✓")

            sleep_random(DETAIL_SLEEP_MIN, DETAIL_SLEEP_MAX)

            if idx % BATCH_SIZE == 0:
                pause = random.uniform(BATCH_SLEEP_MIN, BATCH_SLEEP_MAX)
                print(f"💤 detail batch sleep {pause:.1f}s")
                time.sleep(pause)

        include_detail_fields = bool(pending)

    save_to_supabase(unique_jobs, include_detail_fields=include_detail_fields)
    print("✅ done")


if __name__ == "__main__":
    main()
