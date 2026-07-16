#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import math
import os
import re
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("缺少 SUPABASE_URL / SUPABASE_KEY")

SUPA_HEADERS = {
    "apikey": SUPABASE_KEY,
    # 新版 sb_secret_... key 不是 JWT，不能塞進 Authorization: Bearer header
    # （會被 PostgREST 判定不合法直接 401），只需要 apikey header。
    "Content-Type": "application/json; charset=utf-8",
    "Accept": "application/json",
    "Prefer": "resolution=merge-duplicates",
}

ROOT = Path(__file__).resolve().parent


def resolve_existing_file(candidates):
    for name in candidates:
        p = ROOT / name
        if p.exists():
            return p
    raise FileNotFoundError(f"找不到任何候選檔案: {candidates}")


ROLE_TAXONOMY_PATH = resolve_existing_file(["Job_taxonomy_byRole.csv"])
SKILL_ALIAS_PATH = resolve_existing_file(["skill_alias-2.csv", "skill_alias.csv"])


def clean_text(x):
    if x is None:
        return None
    x = str(x)
    x = re.sub(r"<[^>]+>", " ", x)
    x = re.sub(r"\s+", " ", x).strip()
    return x or None


def norm_for_match(s):
    s = clean_text(s) or ""
    s = s.lower().replace("/", " ")
    s = re.sub(r"[^\w\u4e00-\u9fff\+\.# ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def split_keywords(raw):
    if raw is None:
        return []
    s = str(raw).strip()
    if not s:
        return []
    parts = re.split(r"[,，、/\n]+", s)
    out = []
    seen = set()
    for p in parts:
        p = clean_text(p)
        if not p:
            continue
        n = norm_for_match(p)
        if not n or n in seen:
            continue
        seen.add(n)
        out.append((p, n))
    return out


def safe_list(val):
    if val is None:
        return []
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        val = val.strip()
        if not val:
            return []
        if val.startswith("{") and val.endswith("}"):
            return [i.strip().strip('"') for i in val[1:-1].split(",") if i.strip().strip('"')]
        try:
            parsed = json.loads(val)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


def chunked(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def fetch_jd_raw(limit=1000, only_new=False, batch_size=1000):
    select_cols = ",".join([
        "job_no", "source", "category", "keyword", "title", "company", "location",
        "industry", "is_foreign", "is_listed", "period", "appear_date",
        "salary_low", "salary_high", "remote_work", "welfare_tags",
        "description_snippet", "skill", "specialty", "work_exp", "edu",
        "job_description", "job_category", "manage_resp"
    ])

    all_rows = []
    offset = 0
    while len(all_rows) < limit:
        end = min(offset + batch_size - 1, limit - 1)
        headers = {**SUPA_HEADERS, "Range-Unit": "items", "Range": f"{offset}-{end}"}
        params = {"select": select_cols, "order": "scraped_at.desc"}
        r = requests.get(f"{SUPABASE_URL}/jd_raw", headers=headers, params=params, timeout=60)
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        all_rows.extend(batch)
        print(f"已抓取 {len(all_rows)} 筆 jd_raw（本批 {len(batch)} 筆，range={offset}-{end}）")
        if len(batch) < batch_size:
            break
        offset += len(batch)

    rows = all_rows[:limit]
    if not only_new:
        return rows

    existing = set()
    offset = 0
    while True:
        end = offset + batch_size - 1
        headers = {**SUPA_HEADERS, "Range-Unit": "items", "Range": f"{offset}-{end}"}
        r2 = requests.get(
            f"{SUPABASE_URL}/job_posting",
            headers=headers,
            params={"select": "job_no", "order": "processed_at.desc"},
            timeout=60,
        )
        if r2.status_code not in (200, 206):
            break
        batch2 = r2.json()
        if not batch2:
            break
        existing.update(x.get("job_no") for x in batch2 if x.get("job_no"))
        if len(batch2) < batch_size:
            break
        offset += len(batch2)

    return [row for row in rows if row.get("job_no") not in existing]


def upsert_job_posting(records):
    if not records:
        print("沒有資料需要寫入 job_posting")
        return
    for i, batch in enumerate(chunked(records, 100), start=1):
        r = requests.post(
            f"{SUPABASE_URL}/job_posting",
            headers=SUPA_HEADERS,
            params={"on_conflict": "job_no"},
            data=json.dumps(batch, ensure_ascii=False).encode("utf-8"),
            timeout=60,
        )
        if r.status_code not in (200, 201):
            print(f"batch {i} HTTP {r.status_code}: {r.text[:500]}")
        else:
            print(f"batch {i} ok: {len(batch)}")


def normalize_salary(low, high):
    if low is None or low == 0:
        return None, None, None
    if low > 100_000:
        return int(low // 12), (int(high // 12) if high and high > 0 else None), "年薪"
    return int(low), (int(high) if high and high > 0 else None), "月薪"


def normalize_location(loc):
    loc = clean_text(loc)
    if not loc:
        return None, True
    tw_keys = ["台北", "臺北", "新北", "桃園", "新竹", "台中", "臺中", "台南", "臺南", "高雄", "基隆", "宜蘭", "苗栗", "彰化", "南投", "雲林", "嘉義", "屏東", "花蓮", "台東", "臺東", "澎湖"]
    foreign_keys = ["remote", "singapore", "japan", "tokyo", "hong kong", "china", "shanghai", "beijing", "seoul", "usa", "london", "thailand"]
    if any(k in loc for k in tw_keys):
        return loc, True
    if any(k in loc.lower() for k in foreign_keys):
        return loc, False
    return loc, True


def clean_location_county(raw):
    if not raw or not isinstance(raw, str):
        return None
    raw = raw.strip().replace(" ", "")
    if len(raw) >= 3 and raw[2] in ("市", "縣"):
        return raw[:3]
    return None


def map_industry_bucket(industry):
    if not industry:
        return "Other"
    s = industry.lower()
    if any(k in s for k in ["科技", "資訊", "軟體", "it", "tech", "semiconductor", "半導體", "ic設計", "電腦", "網路"]):
        return "Tech"
    if any(k in s for k in ["金融", "銀行", "保險", "投資", "finance", "bank", "券商", "信託", "期貨", "資產管理"]):
        return "Finance"
    if any(k in s for k in ["顧問", "consulting", "會計", "audit", "kpmg", "pwc", "deloitte", "ey "]):
        return "Consulting"
    if any(k in s for k in ["電商", "零售", "retail", "e-commerce", "百貨", "超市", "量販"]):
        return "Retail"
    if any(k in s for k in ["物流", "運輸", "航運", "倉儲", "快遞", "logistics", "supply chain"]):
        return "Logistics"
    if any(k in s for k in ["醫療", "生技", "pharma", "biotech", "healthcare", "製藥", "醫院", "診所"]):
        return "Healthcare"
    if any(k in s for k in ["製造", "工業", "電子", "manufacturing", "汽車", "機械", "化工", "紡織", "食品", "飲料", "金屬", "塑膠", "橡膠", "石化", "造紙", "建材", "建設", "不動產", "水電", "能源", "環保", "農業", "林業", "漁業", "旅遊", "餐飲", "飯店", "教育", "學校", "出版", "廣告", "媒體", "政府", "非營利"]):
        return "Traditional"
    return "Other"


def parse_work_exp(period_raw, work_exp_raw):
    txt = clean_text(work_exp_raw) or clean_text(period_raw) or ""
    low = txt.lower()
    if not txt:
        return None, None, None
    if re.search(r"不拘|不限|none", low):
        return txt, 0, None
    for pat in [r"(\d+)\s*~\s*(\d+)", r"(\d+)\s*-\s*(\d+)"]:
        m = re.search(pat, low)
        if m:
            return txt, int(m.group(1)), int(m.group(2))
    m = re.search(r"(\d+)\s*\+", low)
    if m:
        return txt, int(m.group(1)), None
    m = re.search(r"(\d+)", low)
    if m:
        return txt, int(m.group(1)), None
    return txt, None, None


EDU_LEVEL_ORDER = [("高中以下", 0), ("高中", 1), ("專科", 2), ("大學", 3), ("碩士", 4), ("博士", 5)]


def extract_min_edu(edu_raw):
    s = (clean_text(edu_raw) or "").lower()
    if not s or "不拘" in s or "不限" in s or s == "null":
        return None, None
    labels = []
    for label, level in EDU_LEVEL_ORDER:
        keys = [label]
        if label == "高中":
            keys += ["高職", "high school"]
        if label == "大學":
            keys += ["bachelor", "university", "college"]
        if label == "碩士":
            keys += ["master"]
        if label == "博士":
            keys += ["phd", "doctor"]
        if any(k in s for k in keys):
            labels.append((label, level))
    if not labels:
        return None, None
    return min(labels, key=lambda x: x[1])


def compute_quality_score(job_description, role_normalized, skill_canonical, salary_low, work_exp_min, edu_level):
    score = 0.0
    if len(job_description or "") > 100:
        score += 0.35
    if skill_canonical:
        score += 0.20
    if role_normalized and role_normalized != "Unclassified":
        score += 0.20
    if salary_low:
        score += 0.10
    if work_exp_min is not None:
        score += 0.10
    if edu_level:
        score += 0.05
    return round(score, 3)


def compute_freshness_score(appear_date_str):
    if not appear_date_str:
        return 0.0
    try:
        d = date.fromisoformat(str(appear_date_str)[:10])
        delta_days = (date.today() - d).days
        return round(math.exp(-0.023 * delta_days), 3)
    except Exception:
        return 0.0


def load_role_taxonomy():
    df = pd.read_csv(ROLE_TAXONOMY_PATH, encoding="utf-8-sig").fillna("")
    rows = []
    for _, row in df.iterrows():
        role = clean_text(row.get("job_skill_name"))
        if not role:
            continue
        parent = clean_text(row.get("job_parent_category"))
        sub = clean_text(row.get("job_sub_category"))
        zh_keywords = split_keywords(row.get("中文職位名稱關鍵字"))
        en_aliases = [
            (role, norm_for_match(role)),
        ]
        seen = {norm_for_match(role)}
        for raw, normed in zh_keywords:
            if normed not in seen:
                seen.add(normed)
                en_aliases.append((raw, normed))
        rows.append({
            "role": role,
            "parent": parent,
            "sub": sub,
            "aliases": en_aliases,
        })
    return rows


def load_skill_alias_catalog():
    df = pd.read_csv(SKILL_ALIAS_PATH, encoding="utf-8-sig").fillna("")
    catalog = {}
    for _, row in df.iterrows():
        canonical = clean_text(row.get("canonical_skill_name"))
        alias = str(row.get("alias") or "").strip()
        if canonical and alias:
            catalog.setdefault(canonical, []).append(alias)
    return catalog


ROLE_INDEX = load_role_taxonomy()
SKILL_CATALOG = load_skill_alias_catalog()

SKILL_PATTERNS = []
for canonical, aliases in SKILL_CATALOG.items():
    compiled = []
    for alias in aliases:
        al = alias.lower()
        pat = rf"(?<![a-z0-9/]){re.escape(al)}(?![a-z0-9/])"
        try:
            compiled.append(re.compile(pat, re.IGNORECASE))
        except re.error:
            pass
    SKILL_PATTERNS.append((canonical, compiled))


def try_rule_skills(job):
    pools = []
    for field in ["title", "description_snippet", "job_description"]:
        v = clean_text(job.get(field))
        if v:
            pools.append(v)
    for field in ["skill", "specialty", "job_category"]:
        for v in safe_list(job.get(field)):
            if v:
                pools.append(str(v))
    norm_text = "\n".join(pools).lower()
    found = []
    seen = set()
    for canonical, patterns in SKILL_PATTERNS:
        for pat in patterns:
            if pat.search(norm_text):
                if canonical not in seen:
                    seen.add(canonical)
                    found.append(canonical)
                break
    return found[:20]


def alias_score_in_text(alias_norm, text_norm):
    if not alias_norm or not text_norm:
        return 0.0, ""
    if alias_norm == text_norm:
        return 1.0, f"exact:{alias_norm}"
    if alias_norm in text_norm:
        base = 0.93 if len(alias_norm) >= 4 else 0.88
        return base, f"contain:{alias_norm}"
    tokens = [t for t in alias_norm.split() if t]
    if len(tokens) >= 2 and all(t in text_norm for t in tokens):
        return 0.82, f"all_tokens:{'|'.join(tokens)}"
    return 0.0, ""


def match_role_from_text(text, source_label):
    text_norm = norm_for_match(text)
    if not text_norm:
        return None

    best = None
    for entry in ROLE_INDEX:
        role_best = None
        for alias_raw, alias_norm in entry["aliases"]:
            score, why = alias_score_in_text(alias_norm, text_norm)
            if score <= 0:
                continue
            bonus = min(len(alias_norm) / 50.0, 0.05)
            final_score = round(score + bonus, 4)
            candidate = {
                "score": final_score,
                "parent": entry["parent"],
                "sub": entry["sub"],
                "role": entry["role"],
                "reason": f"{source_label}:{why}",
                "alias": alias_raw,
            }
            if role_best is None or candidate["score"] > role_best["score"]:
                role_best = candidate
        if role_best is None:
            continue
        if best is None or role_best["score"] > best["score"]:
            best = role_best
    return best


def try_rule_role(job, rule_skills):
    title_hit = match_role_from_text(job.get("title"), "title")
    if title_hit and title_hit["score"] >= 0.90:
        return title_hit["parent"], title_hit["sub"], title_hit["role"], title_hit["score"], title_hit["reason"]

    skill_text = " ".join([s for s in (rule_skills or []) if s])
    skill_hit = match_role_from_text(skill_text, "skill")
    if skill_hit and skill_hit["score"] >= 0.92:
        return skill_hit["parent"], skill_hit["sub"], skill_hit["role"], skill_hit["score"], skill_hit["reason"]

    jd_text = " ".join([
        clean_text(job.get("description_snippet")) or "",
        (clean_text(job.get("job_description")) or "")[:1200],
    ])
    jd_hit = match_role_from_text(jd_text, "jd")
    if jd_hit and jd_hit["score"] >= 0.95:
        return jd_hit["parent"], jd_hit["sub"], jd_hit["role"], jd_hit["score"], jd_hit["reason"]

    return None, None, "Unclassified", 0.0, "no confident match from job_taxonomy keywords (title->skill->jd)"


def has_minimum_fields(job):
    return all([
        clean_text(job.get("job_no")),
        clean_text(job.get("title")),
        clean_text(job.get("company")),
        clean_text(job.get("industry")),
    ])


def transform_row(job):
    title_raw = clean_text(job.get("title"))
    company_raw = clean_text(job.get("company"))
    location_raw = clean_text(job.get("location"))
    location_clean, is_taiwan = normalize_location(location_raw)
    location_county = clean_location_county(location_raw)
    industry_raw = clean_text(job.get("industry"))
    industry_bucket = map_industry_bucket(industry_raw)
    period_raw = clean_text(job.get("period"))
    work_exp_raw = clean_text(job.get("work_exp"))
    work_exp_raw_final, work_exp_min, work_exp_max = parse_work_exp(period_raw, work_exp_raw)
    edu_raw = clean_text(job.get("edu"))
    edu_level, edu_level_int = extract_min_edu(edu_raw)
    salary_low_norm, salary_high_norm, salary_unit = normalize_salary(job.get("salary_low"), job.get("salary_high"))

    rule_skills = try_rule_skills(job)
    rule_parent, rule_sub, rule_role, rule_conf, rule_reason = try_rule_role(job, rule_skills)

    quality_score = compute_quality_score(clean_text(job.get("job_description")), rule_role, rule_skills, salary_low_norm, work_exp_min, edu_level)
    freshness_score = compute_freshness_score(job.get("appear_date"))

    return {
        "job_no": job.get("job_no"),
        "source": job.get("source") or "104",
        "title_raw": title_raw,
        "title_clean": title_raw,
        "company_raw": company_raw,
        "company_clean": company_raw,
        "location_raw": location_raw,
        "location_clean": location_clean,
        "location_county": location_county,
        "is_taiwan": is_taiwan,
        "industry_raw": industry_raw,
        "industry_bucket": industry_bucket,
        "period_raw": period_raw,
        "work_exp_raw": work_exp_raw_final,
        "work_exp_min": work_exp_min,
        "work_exp_max": work_exp_max,
        "edu_raw": edu_raw,
        "edu_level": edu_level,
        "edu_level_int": edu_level_int,
        "appear_date": str(job.get("appear_date"))[:10] if job.get("appear_date") else None,
        "salary_low": salary_low_norm,
        "salary_high": salary_high_norm,
        "salary_unit": salary_unit,
        "remote_work": job.get("remote_work") or 0,
        "description_snippet": clean_text(job.get("description_snippet")),
        "job_description": clean_text(job.get("job_description")),
        "job_category_raw": job.get("job_category"),
        "manage_resp": clean_text(job.get("manage_resp")),
        "job_parent_category": rule_parent,
        "job_sub_category": rule_sub,
        "role_normalized": rule_role,
        "role_confidence": round(float(rule_conf), 3) if rule_conf is not None else None,
        "skill_raw": safe_list(job.get("skill")) or list(rule_skills),
        "skill_canonical": list(rule_skills),
        "llm_model": None,
        "llm_reason": f"rule: {rule_reason}",
        "quality_score": quality_score,
        "freshness_score": freshness_score,
        "raw_payload": job,
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "llm_processed_at": None,
        "is_foreign": job.get("is_foreign"),
        "is_listed": job.get("is_listed"),
    }


def parse_args():
    p = argparse.ArgumentParser(description="Clean jd_raw -> job_posting")
    p.add_argument("--limit", type=int, default=500)
    p.add_argument("--only-new", action="store_true")
    p.add_argument("--quality-threshold", type=float, default=0.10)
    p.add_argument("--batch-size", type=int, default=1000)
    return p.parse_args()


def main():
    args = parse_args()
    rows = fetch_jd_raw(limit=args.limit, only_new=args.only_new, batch_size=args.batch_size)
    print(f"讀到 jd_raw {len(rows)} 筆")
    outputs = []
    skipped = 0
    no_skill_count = 0
    unclassified_count = 0

    for idx, row in enumerate(rows, start=1):
        if not has_minimum_fields(row):
            skipped += 1
            print(f"[{idx}/{len(rows)}] SKIP (missing base fields) - {row.get('job_no')} - {clean_text(row.get('title'))}")
            continue

        rec = transform_row(row)
        if not rec.get("skill_canonical"):
            no_skill_count += 1
        if rec.get("role_normalized") == "Unclassified":
            unclassified_count += 1

        q = rec.get("quality_score") or 0
        if q < args.quality_threshold:
            skipped += 1
            print(f"[{idx}/{len(rows)}] SKIP (quality={q:.2f}) - {row.get('job_no')} - {clean_text(row.get('title'))}")
            continue

        outputs.append(rec)
        print(
            f"[{idx}/{len(rows)}] ok - {row.get('job_no')} - {clean_text(row.get('title'))} | "
            f"role={rec.get('role_normalized')} | conf={rec.get('role_confidence')} | "
            f"skills={len(rec.get('skill_canonical') or [])} | q={q:.2f} | {rec.get('llm_reason')}"
        )

    upsert_job_posting(outputs)
    print(f"完成：寫入 job_posting {len(outputs)} 筆；跳過 {skipped} 筆")
    print(f"無技能但仍保留 {no_skill_count} 筆；Unclassified {unclassified_count} 筆")


if __name__ == "__main__":
    main()
