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
DETAIL_API = "https://www.104.com.tw/job/ajax/content/{}"

LIST_SLEEP_MIN = 0.8
LIST_SLEEP_MAX = 1.5

DETAIL_SLEEP_MIN = 0.8
DETAIL_SLEEP_MAX = 1.8

KEYWORD_SLEEP_MIN = 1.5
KEYWORD_SLEEP_MAX = 3.0

BATCH_SIZE = 100
BATCH_SLEEP_MIN = 15
BATCH_SLEEP_MAX = 30


def resolve_keywords_csv() -> Path:
    candidates = [
        Path.cwd() / KEYWORDS_CSV,
        ROOT / KEYWORDS_CSV,
    ]

    github_workspace = os.environ.get("GITHUB_WORKSPACE")
    if github_workspace:
        candidates.append(Path(github_workspace) / KEYWORDS_CSV)

    for p in candidates:
        if p.exists():
            print(f"📌 keyword file = {p}")
            return p

    raise FileNotFoundError(f"Cannot find {KEYWORDS_CSV}")


def load_crawler_keywords() -> List[str]:
    path = resolve_keywords_csv()

    df = pd.read_csv(path, encoding="utf-8-sig").fillna("")

    if "keyword" not in df.columns:
        raise ValueError(f"{path.name} missing keyword column")

    keywords = []

    for kw in df["keyword"].astype(str):
        kw = kw.strip()

        if kw:
            keywords.append(kw)

    keywords = list(dict.fromkeys(keywords))

    print(f"📌 keyword count = {len(keywords)}")

    return keywords


def build_session() -> requests.Session:
    s = requests.Session()

    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        ),
        "Referer": "https://www.104.com.tw/jobs/search/",
        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    })

    warmup = s.get("https://www.104.com.tw/jobs/search/", timeout=10)
    print(f"🔥 warmup status = {warmup.status_code}")

    return s


crawler = build_session()


def sleep_random(low: float, high: float):
    time.sleep(random.uniform(low, high))


def parse_job(item: Dict, keyword: str) -> Optional[Dict]:
    link = item.get("link", {}).get("job")

    if not link:
        return None

    job_url = f"https:{link}" if link.startswith("//") else link
    job_url = job_url.split("?")[0]

    job_no = job_url.rstrip("/").split("/")[-1]

    return {
        "job_no": job_no,
        "keyword": keyword,
        "title": item.get("jobName"),
        "company": item.get("custName"),
        "industry": item.get("coIndustryDesc"),
        "location": item.get("jobAddrNoDesc"),
        "salary_low": item.get("salaryLow"),
        "salary_high": item.get("salaryHigh"),
        "appear_date": item.get("appearDate"),
        "description_snippet": item.get("description"),
        "job_url": job_url,
        "job_description": None,
        "skill": None,
        "specialty": None,
    }


def fetch_list(keyword: str, max_pages: int, past_days: int):
    jobs = []

    for page in range(1, max_pages + 1):

        r = crawler.get(
            LIST_API,
            params={
                "keyword": keyword,
                "page": page,
                "pageSize": 20,
                "order": 15,
                "asc": 0,
                "mode": "s",
                "past": past_days,
            },
            timeout=20,
        )

        r.raise_for_status()

        data = r.json()

        rows = data.get("data") or []

        if not rows:
            break

        for item in rows:
            parsed = parse_job(item, keyword)

            if parsed:
                jobs.append(parsed)

        print(f"[LIST] {keyword} page={page} jobs={len(rows)} total={len(jobs)}")

        sleep_random(LIST_SLEEP_MIN, LIST_SLEEP_MAX)

    return jobs


def enrich_detail(job: Dict):
    job_no = job["job_no"]

    try:
        r = crawler.get(
            DETAIL_API.format(job_no),
            headers={
                "Referer": job["job_url"]
            },
            timeout=20,
        )

        r.raise_for_status()

        data = r.json().get("data") or {}

        detail = data.get("jobDetail") or {}
        condition = data.get("condition") or {}

        job["job_description"] = detail.get("jobDescription")

        job["skill"] = [
            x.get("description")
            for x in condition.get("skill", [])
            if x.get("description")
        ]

        job["specialty"] = [
            x.get("description")
            for x in condition.get("specialty", [])
            if x.get("description")
        ]

    except Exception as e:
        print(f"[DETAIL] fail {job_no}: {e}")

    return job


def dedupe_jobs(jobs: List[Dict]):
    result = {}

    for j in jobs:
        result[j["job_no"]] = j

    return list(result.values())


def save_to_supabase(jobs: List[Dict]):
    if not jobs:
        return

    rows = []

    now = datetime.now(timezone.utc).isoformat()

    for j in jobs:
        rows.append({
            **j,
            "scraped_at": now,
        })

    for i in range(0, len(rows), 100):
        batch = rows[i:i+100]

        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/jd_raw",
            headers=SUPA_HEADERS,
            params={"on_conflict": "job_no"},
            data=json.dumps(batch, ensure_ascii=False).encode("utf-8"),
            timeout=60,
        )

        print(f"[UPSERT] batch={i//100+1} status={r.status_code}")


def parse_args():
    p = argparse.ArgumentParser()

    p.add_argument("--keyword-offset", type=int, default=0)
    p.add_argument("--keyword-limit", type=int, default=0)

    p.add_argument("--max-pages", type=int, default=5)
    p.add_argument("--past-days", type=int, default=30)

    p.add_argument("--skip-detail", action="store_true")
    p.add_argument("--detail-limit", type=int, default=0)

    p.add_argument("--include-all-companies", action="store_true")

    return p.parse_args()


def main():
    args = parse_args()

    keywords = load_crawler_keywords()

    if args.keyword_offset > 0:
        keywords = keywords[args.keyword_offset:]

    if args.keyword_limit > 0:
        keywords = keywords[:args.keyword_limit]

    print(f"📌 running keywords = {len(keywords)}")

    all_jobs = []

    for idx, kw in enumerate(keywords, start=1):
        print(f"[{idx}/{len(keywords)}] keyword={kw}")

        jobs = fetch_list(
            keyword=kw,
            max_pages=args.max_pages,
            past_days=args.past_days,
        )

        all_jobs.extend(jobs)

        sleep_random(KEYWORD_SLEEP_MIN, KEYWORD_SLEEP_MAX)

    unique_jobs = dedupe_jobs(all_jobs)

    print(f"📌 unique jobs = {len(unique_jobs)}")

    if not args.skip_detail:

        pending = unique_jobs

        if args.detail_limit > 0:
            pending = pending[:args.detail_limit]

        print(f"📌 detail pending = {len(pending)}")

        for idx, job in enumerate(pending, start=1):

            enrich_detail(job)

            if idx % BATCH_SIZE == 0:
                pause = random.uniform(BATCH_SLEEP_MIN, BATCH_SLEEP_MAX)
                print(f"💤 batch sleep {pause:.1f}s")
                time.sleep(pause)

            sleep_random(DETAIL_SLEEP_MIN, DETAIL_SLEEP_MAX)

    save_to_supabase(unique_jobs)

    print("✅ done")


if __name__ == "__main__":
    main()
