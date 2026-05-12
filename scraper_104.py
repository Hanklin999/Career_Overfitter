#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
104 職缺爬蟲（forsearch 版）

設計目標：
1. 使用 Job_taxonomy_forsearch.csv 的 keyword 欄位搜尋。
2. 每個 keyword 抓 5 頁，全量掃描。
3. 不限制外商 / 上市上櫃，抓全部職缺。
4. 先抓所有 keyword 的列表 job_no，全部完成後再去重，再補 detail。
5. 避免 list-only upsert 把既有 detail 欄位覆蓋成 NULL。
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
    raise RuntimeError("請在 .env 中設定 SUPABASE_URL 與 SUPABASE_KEY")

SUPA_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates",
}

ROOT = Path(__file__).resolve().parent.parent if Path(__file__).resolve().parent.name == "output" else Path(__file__).resolve().parent
KEYWORDS_CSV_CANDIDATES = [
    "Job_taxonomy_forsearch.csv",
    "crawler_keywords_compressed.csv",
]

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

# ── 速度設定：forsearch 全量版（安全不被封）──────────────
DEFAULT_LIST_SLEEP_MIN = 1.0
DEFAULT_LIST_SLEEP_MAX = 2.0

DEFAULT_DETAIL_SLEEP_MIN = 1.2
DEFAULT_DETAIL_SLEEP_MAX = 2.5

DEFAULT_KEYWORD_SLEEP_MIN = 2.5
DEFAULT_KEYWORD_SLEEP_MAX = 5.0

BATCH_SIZE = 50
BATCH_SLEEP_MIN = 30.0
BATCH_SLEEP_MAX = 60.0

DEFAULT_BACKOFF_BASE = 10.0
DEFAULT_MAX_PAGES = 5
DEFAULT_MAX_RETRIES = 4
DEFAULT_TIMEOUT = 25
DEFAULT_PAST_DAYS = 30
DEFAULT_KEYWORD_CAP = 0

# 連續假 404 幾次就判定 IP 被封，暫停
FAKE_404_THRESHOLD = 3
FAKE_404_PAUSE = 1800  # 30 分鐘

# 104 list tags 之外，補一些你真的會想看的公司白名單。
HIGH_VALUE_COMPANY_KEYWORDS = [
    # Global tech / platform
    "Google", "Meta", "Facebook", "Amazon", "AWS", "Microsoft", "Apple", "Netflix",
    "Uber", "Airbnb", "TikTok", "ByteDance", "LINE", "LinkedIn", "Salesforce", "Oracle",
    "SAP", "Adobe", "IBM", "NVIDIA", "AMD", "Intel", "Qualcomm", "ASML",
    # Taiwan / APAC tech
    "台積電", "TSMC", "聯發科", "MediaTek", "鴻海", "Foxconn", "華碩", "ASUS", "宏碁", "Acer",
    "廣達", "Quanta", "緯創", "Wistron", "仁寶", "Compal", "Trend Micro", "趨勢科技",
    "Appier", "Gogoro", "91APP", "KKBOX", "Klook", "foodpanda", "富邦媒", "momo",
    "蝦皮", "Shopee", "Sea", "酷澎", "Coupang", "PChome", "Yahoo",
    # Finance / consulting / professional service
    "McKinsey", "BCG", "Bain", "Deloitte", "PwC", "KPMG", "EY", "Accenture",
    "JPMorgan", "Goldman", "Morgan Stanley", "Citi", "Citibank", "HSBC", "Standard Chartered",
    "花旗", "滙豐", "渣打", "國泰", "富邦", "玉山", "中信", "台新", "星展", "DBS",
    # FMCG / pharma / industrial
    "P&G", "Unilever", "Nestle", "L'Oréal", "Loreal", "Coca-Cola", "Pepsi",
    "Merck", "MSD", "Pfizer", "Novartis", "Roche", "AstraZeneca", "AZ", "GSK", "Johnson",
    "Siemens", "GE", "Schneider", "Bosch", "3M", "Dell", "HP", "HPE",
]

# 用來排序 keyword。不是硬性過濾，而是讓前 80 個比較像商學院 / 分析 / tech-business 出路。
KEYWORD_PRIORITY_TERMS = [
    "資料", "數據", "分析", "商業分析", "商務分析", "BI", "Business Intelligence",
    "產品", "Product", "PM", "專案", "Project", "策略", "Strategy", "經營", "營運",
    "財務", "FP&A", "金融", "投資", "研究", "顧問", "Consultant", "Consulting",
    "市場", "行銷", "Growth", "成長", "Business Development", "商務開發",
    "供應鏈", "採購", "Sourcing", "Purchasing", "Supply Chain",
    "資料工程", "Data Engineer", "系統分析", "Software", "軟體",
]

# 明顯太泛或 104 搜尋效益較差的詞，可以降權。
LOW_VALUE_KEYWORD_TERMS = [
    "專員", "助理", "儲備幹部", "行政", "客服", "門市", "業務助理",
]


def resolve_existing_file(candidates: Sequence[str]) -> Path:
    for name in candidates:
        p = ROOT / name
        if p.exists():
            return p
    raise FileNotFoundError(f"找不到任何候選檔案: {candidates}")


def build_session() -> requests.Session:
    """建立 Session，先打首頁讓 Cloudflare 設定 cookie。"""
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
_consecutive_fake_404 = 0


def is_fake_404(resp: requests.Response) -> bool:
    """104 被封時可能回 404，但 body 很短或含 403/權限字樣。"""
    if resp.status_code != 404:
        return False
    body = resp.text or ""
    # 只有明確含封鎖關鍵字才算假 404，單純短 body 可能只是職缺下架
    if any(kw in body for kw in ["403", "使用者權限", "Forbidden", "Access Denied", "blocked"]):
        return True
    return False


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
    global _consecutive_fake_404

    for attempt in range(max_retries):
        try:
            resp = session.request(method, url, **kwargs)

            if is_fake_404(resp):
                _consecutive_fake_404 += 1
                print(f"🚨 疑似假 404（IP 被封）#{_consecutive_fake_404}: {url}")
                if _consecutive_fake_404 >= FAKE_404_THRESHOLD:
                    print(f"🛑 連續 {FAKE_404_THRESHOLD} 次假 404，暫停 {FAKE_404_PAUSE / 60:.0f} 分鐘...")
                    time.sleep(FAKE_404_PAUSE)
                    _consecutive_fake_404 = 0
                    session = build_session()
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
    job_no = item.get("jobNo") or job_url.split("/")[-1]
    if not job_no:
        return None

    raw_tags = item.get("tags") or {}
    tags_dict = raw_tags if isinstance(raw_tags, dict) else {}

    welfare_tags = []
    for k, v in tags_dict.items():
        desc = v.get("desc") if isinstance(v, dict) else str(v)
        if k.startswith("wf") and desc:
            welfare_tags.append(desc)

    # 104 tags: zoneForeign 常見為外商；zone 常見為上市上櫃 / 大企業相關標籤。
    is_foreign = bool(tags_dict.get("zoneForeign"))
    is_listed = bool(tags_dict.get("zone"))

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
        "skill": None,
        "specialty": None,
        "work_exp": None,
        "edu": None,
        "job_description": None,
        "job_category": None,
        "manage_resp": None,
    }


def normalize_keyword(keyword: str) -> str:
    return str(keyword or "").strip().replace("，", ",")


def keyword_score(keyword: str, mapped_roles_count: int = 0) -> int:
    text = keyword.lower()
    score = int(mapped_roles_count or 0)
    for term in KEYWORD_PRIORITY_TERMS:
        if term.lower() in text:
            score += 10
    for term in LOW_VALUE_KEYWORD_TERMS:
        if term.lower() in text:
            score -= 3
    # 太長的 keyword 通常比較窄，適度降權；短中文主詞通常比較適合當搜尋入口。
    if len(keyword) <= 6:
        score += 2
    elif len(keyword) >= 12:
        score -= 2
    return score


def load_crawler_keywords(keyword_cap: int = DEFAULT_KEYWORD_CAP, use_all_keywords: bool = False) -> List[str]:
    path = resolve_existing_file(KEYWORDS_CSV_CANDIDATES)
    df = pd.read_csv(path, encoding="utf-8-sig").fillna("")

    keyword_rows = []
    if "keyword" in df.columns:
        for _, row in df.iterrows():
            kw = normalize_keyword(row.get("keyword", ""))
            if not kw:
                continue
            raw_cnt = str(row.get("mapped_roles_count") or "")
            mapped_roles_count = int(raw_cnt) if raw_cnt.isdigit() else 0
            keyword_rows.append((kw, mapped_roles_count))
    elif len(df.columns) >= 4:
        keyword_col = df.columns[3]
        for _, row in df.iterrows():
            raw = normalize_keyword(row.get(keyword_col, ""))
            if not raw:
                continue
            for part in raw.split(","):
                kw = part.strip()
                if kw:
                    keyword_rows.append((kw, 0))
    else:
        raise ValueError(f"無法從 {path.name} 辨識 keyword 欄位")

    # dedupe，保留最高 mapped_roles_count
    keyword_map: Dict[str, int] = {}
    for kw, cnt in keyword_rows:
        keyword_map[kw] = max(keyword_map.get(kw, 0), cnt)

    keywords = list(keyword_map.keys())
    if use_all_keywords or keyword_cap <= 0:
        return sorted(keywords)

    ranked = sorted(
        keywords,
        key=lambda kw: (keyword_score(kw, keyword_map.get(kw, 0)), keyword_map.get(kw, 0), -len(kw), kw),
        reverse=True,
    )
    return ranked[:keyword_cap]


def is_high_value_company(job: Dict) -> bool:
    if bool(job.get("is_foreign")) or bool(job.get("is_listed")):
        return True

    company = str(job.get("company") or "")
    company_lower = company.lower()
    return any(k.lower() in company_lower for k in HIGH_VALUE_COMPANY_KEYWORDS)


def fetch_list(keyword: str, max_pages: int, past_days: int) -> List[Dict]:
    jobs: List[Dict] = []
    for page in range(1, max_pages + 1):
        try:
            resp = request_with_backoff(
                crawler,
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
    job_no = job.get("job_no")
    job_url = job.get("job_url")
    if not job_no:
        return job

    try:
        resp = request_with_backoff(
            crawler,
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
            prev = deduped[job_no]
            keywords = {str(prev.get("keyword") or "").strip(), str(job.get("keyword") or "").strip()}
            prev["keyword"] = ", ".join(sorted([x for x in keywords if x]))
            # 如果重複職缺其中一次有高價值標籤，要保留下來。
            prev["is_foreign"] = bool(prev.get("is_foreign")) or bool(job.get("is_foreign"))
            prev["is_listed"] = bool(prev.get("is_listed")) or bool(job.get("is_listed"))
    return list(deduped.values())


def get_existing_detail_job_nos() -> Set[str]:
    """只回傳已經有 detail 的 job_no，避免兩階段爬取時 list-only row 讓 detail 被跳過。"""
    existing: Set[str] = set()
    offset = 0
    while True:
        resp = requests.get(
            f"{SUPABASE_URL}/jd_raw",
            headers=SUPA_HEADERS,
            params={
                "select": "job_no",
                "job_description": "not.is.null",
                "limit": 1000,
                "offset": offset,
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


def build_supabase_record(job: Dict) -> Dict:
    """只在 detail 欄位有值時才送出，避免 skip-detail upsert 把既有 detail 覆蓋成 NULL。"""
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

    detail_fields = ["skill", "specialty", "work_exp", "edu", "job_description", "job_category", "manage_resp"]
    for field in detail_fields:
        value = job.get(field)
        if value not in (None, "", []):
            record[field] = value

    return record


def save_to_supabase(jobs: List[Dict]) -> None:
    if not jobs:
        print("⚠️ 沒有資料需要寫入 jd_raw")
        return

    records = [build_supabase_record(job) for job in jobs if job.get("job_no")]

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


def truncate_jd_raw() -> None:
    resp = requests.delete(
        f"{SUPABASE_URL}/jd_raw",
        headers={**SUPA_HEADERS, "Prefer": "count=exact"},
        params={"job_url": "neq.null"},
        timeout=60,
    )
    print(f"truncate jd_raw: HTTP {resp.status_code} | {resp.text[:200]}")
    resp.raise_for_status()


def parse_args():
    p = argparse.ArgumentParser(description="104 high-value job market radar -> jd_raw")
    p.add_argument("--truncate", action="store_true", help="清空 jd_raw 後重抓")
    p.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES, help="每個 keyword 最多抓幾頁；預設 3")
    p.add_argument("--past-days", type=int, default=DEFAULT_PAST_DAYS, help="抓近 N 天職缺；預設 30")
    p.add_argument("--keyword-limit", type=int, default=0, help="測試用，只取前 N 個 keyword；0=依 keyword-cap")
    p.add_argument("--keyword-cap", type=int, default=DEFAULT_KEYWORD_CAP, help="預設最多使用前 N 個高優先 keyword；0=全部")
    p.add_argument("--all-keywords", action="store_true", help="使用 CSV 全部 keywords，不做 cap")
    p.add_argument("--skip-detail", action="store_true", help="只抓列表，不補 detail")
    p.add_argument("--include-all-companies", action="store_true", help="（已棄用，現在預設全部抓取）")
    p.add_argument("--detail-all", action="store_true", help="對保留下來的所有職缺補 detail；預設已經因高價值公司過濾")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    keywords = load_crawler_keywords(keyword_cap=args.keyword_cap, use_all_keywords=args.all_keywords)
    if args.keyword_limit and args.keyword_limit > 0:
        keywords = keywords[:args.keyword_limit]

    print("=" * 72)
    print(
        "Scraper start | "
        f"keywords={len(keywords)} | max_pages={args.max_pages} | past_days={args.past_days} | "
        f"include_all=True | skip_detail={args.skip_detail}"
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

    # 不做公司過濾，全部職缺都保留
    print(f"全部職缺（不限公司類型）: {len(unique_jobs)} 筆")

    if not args.skip_detail:
        existing_detail_nos = get_existing_detail_job_nos()
        print(f"已有 detail 的 job_no: {len(existing_detail_nos)}")

        pending = [j for j in unique_jobs if j["job_no"] not in existing_detail_nos]
        print(f"待抓 detail: {len(pending)} 筆")

        for idx, job in enumerate(pending, start=1):
            enrich_detail(job)
            print(f"[DETAIL] {idx}/{len(pending)} {job['job_no']} ✓")

            polite_sleep(DEFAULT_DETAIL_SLEEP_MIN, DEFAULT_DETAIL_SLEEP_MAX)

            if idx % BATCH_SIZE == 0:
                pause = random.uniform(BATCH_SLEEP_MIN, BATCH_SLEEP_MAX)
                print(f"💤 已抓 {idx} 筆，批次休息 {pause / 60:.1f} 分鐘...")
                time.sleep(pause)

    save_to_supabase(unique_jobs)
    print("✅ Scraper 完成")


if __name__ == "__main__":
    main()
