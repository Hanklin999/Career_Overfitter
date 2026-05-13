#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import math
import os
import re
import time
from datetime import date, datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests
from dotenv import load_dotenv

try:
    from google import genai
except Exception:
    genai = None

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("缺少 SUPABASE_URL / SUPABASE_KEY")

SUPA_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json; charset=utf-8",
    "Accept": "application/json",
    "Prefer": "resolution=merge-duplicates",
}

ROOT = Path(__file__).resolve().parent.parent if Path(__file__).resolve().parent.name == 'output' else Path(__file__).resolve().parent


def resolve_existing_file(candidates):
    for name in candidates:
        p = ROOT / name
        if p.exists():
            return p
    raise FileNotFoundError(f"找不到任何候選檔案: {candidates}")


ROLE_TAXONOMY_PATH = resolve_existing_file(["Job_taxonomy_byRole.csv"])
SKILL_TAXONOMY_PATH = resolve_existing_file(["skill_taxonomy-2.csv", "skill_taxonomy.csv"])
ROLE_ALIAS_PATH = resolve_existing_file(["role_alias.csv"])
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


def safe_list(val) -> list:
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
            r = json.loads(val)
            return r if isinstance(r, list) else []
        except Exception:
            return []
    return []


def fetch_jd_raw(limit=1000, only_new=False):
    params = {
        "select": ",".join([
            "job_no", "source", "category", "keyword", "title", "company", "location",
            "industry", "is_foreign", "is_listed", "period", "appear_date",
            "salary_low", "salary_high", "remote_work", "welfare_tags",
            "description_snippet", "skill", "specialty", "work_exp", "edu",
            "job_description", "job_category", "manage_resp"
        ]),
        "limit": str(limit),
        "order": "scraped_at.desc",
    }
    r = requests.get(f"{SUPABASE_URL}/jd_raw", headers=SUPA_HEADERS, params=params, timeout=60)
    r.raise_for_status()
    rows = r.json()

    if not only_new:
        return rows

    r2 = requests.get(
        f"{SUPABASE_URL}/job_posting",
        headers=SUPA_HEADERS,
        params={"select": "job_no", "limit": str(limit * 3)},
        timeout=60,
    )
    existing = set()
    if r2.status_code in (200, 206):
        existing = {x.get("job_no") for x in r2.json() if x.get("job_no")}
    return [row for row in rows if row.get("job_no") not in existing]


def chunked(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


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
    if low is None:
        return None, None, None
    # 0 視為無薪資資訊
    if low == 0:
        return None, None, None
    if low > 100_000:
        return int(low // 12), (int(high // 12) if high and high > 0 else None), "年薪"
    return int(low), (int(high) if high and high > 0 else None), "月薪"


def normalize_location(loc):
    loc = clean_text(loc)
    if not loc:
        return None, True
    tw_keys = ["台北", "臺北", "新北", "桃園", "新竹", "台中", "臺中", "台南", "臺南", "高雄", "基隆", "宜蘭", "苗栗", "彰化", "南投", "雲林", "嘉義", "屏東", "花蓮", "台東", "臺東", "澎湖"]
    foreign_keys = ["remote", "singapore", "japan", "tokyo", "hong kong", "china", "shanghai", "beijing", "seoul", "usa", "london"]
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
        return txt or None, None, None
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
    if role_normalized:
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


def load_role_alias():
    df = pd.read_csv(ROLE_ALIAS_PATH, encoding="utf-8-sig").fillna("")
    alias_map = {}
    for _, row in df.iterrows():
        role = clean_text(row.get("role_normalized"))
        alias = norm_for_match(row.get("alias"))
        if role and alias:
            alias_map.setdefault(role, []).append(alias)
    return alias_map


def load_role_taxonomy():
    df = pd.read_csv(ROLE_TAXONOMY_PATH, encoding="utf-8-sig").fillna("")

    # 支援 3 欄或 4 欄 taxonomy
    base_cols = ["job_parent_category", "job_sub_category", "job_skill_name"]
    df = df.copy()

    role_records = df[base_cols].drop_duplicates().to_dict("records")
    role_map, title_index, alias_index = {}, [], []
    role_alias_map = load_role_alias()

    for _, row in df.iterrows():
        role = clean_text(row.get("job_skill_name"))
        if not role:
            continue

        role_map[role] = {
            "job_parent_category": clean_text(row.get("job_parent_category")),
            "job_sub_category": clean_text(row.get("job_sub_category")),
        }

        title_index.append((norm_for_match(role), role))

        # 1) 讀 role_alias.csv
        for alias in role_alias_map.get(role, []):
            alias_index.append((alias, role))

        # 2) 讀 Job_taxonomy_byRole.csv 第四欄：中文職位名稱關鍵字
        kw_text = row.get("中文職位名稱關鍵字", "")
        for kw in str(kw_text).split(","):
            kw_norm = norm_for_match(kw)
            if kw_norm:
                alias_index.append((kw_norm, role))

    return role_records, role_map, title_index, alias_index


def load_skill_alias_catalog():
    df = pd.read_csv(SKILL_ALIAS_PATH, encoding="utf-8-sig").fillna("")
    catalog = {}
    for _, row in df.iterrows():
        canonical = clean_text(row.get("canonical_skill_name"))
        alias = str(row.get("alias") or "").strip()
        if canonical and alias:
            catalog.setdefault(canonical, []).append(alias)
    return catalog


def load_skill_taxonomy():
    df = pd.read_csv(SKILL_TAXONOMY_PATH, encoding="utf-8-sig")
    df = df.iloc[:, :3].copy()
    df.columns = ["skill_parent_category", "skill_sub_category", "canonical_skill_name"]
    df = df.fillna("").drop_duplicates()
    records = df.to_dict("records")
    skill_set = set()
    skill_meta = {}
    for r in records:
        canonical = clean_text(r["canonical_skill_name"])
        skill_set.add(canonical)
        skill_meta[canonical] = {
            "skill_parent_category": clean_text(r["skill_parent_category"]),
            "skill_sub_category": clean_text(r["skill_sub_category"]),
        }
    return records, skill_set, skill_meta


ROLE_RECORDS, ROLE_MAP, ROLE_TITLE_INDEX, ROLE_ALIAS_INDEX = load_role_taxonomy()
SKILL_CATALOG = load_skill_alias_catalog()
SKILL_RECORDS, SKILL_SET, SKILL_META = load_skill_taxonomy()

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


def try_rule_role(job):
    title = norm_for_match(job.get("title"))
    keyword = norm_for_match(job.get("keyword"))
    category = norm_for_match(job.get("category"))
    desc = norm_for_match(job.get("description_snippet"))

    if not any([title, keyword, category, desc]):
        return None, None, None, 0.0, "no text"

    # Dangerous short aliases should not be matched in weak fields.
    # Example: PO can appear inside support/reporting; PM can mean many things.
    DANGEROUS_SHORT_ALIASES = {
        "po", "pm", "ba", "sa", "qa", "hr", "it", "ae", "rm", "bd", "bi",
        "da", "ds", "de", "ml", "ai", "fe", "be"
    }

    def is_safe_alias(alias_norm):
        if not alias_norm:
            return False
        if alias_norm in DANGEROUS_SHORT_ALIASES:
            return False
        # Very short English aliases are risky unless matched in title exact logic.
        if re.fullmatch(r"[a-z]{1,3}", alias_norm):
            return False
        return True

    def contains_match(alias_norm, field_text):
        if not alias_norm or not field_text:
            return False

        # For Chinese keywords, simple substring is fine.
        if re.search(r"[\u4e00-\u9fff]", alias_norm):
            return alias_norm in field_text

        # For English keywords, use word-boundary-like matching.
        pattern = rf"(?<![a-z0-9]){re.escape(alias_norm)}(?![a-z0-9])"
        return re.search(pattern, field_text, flags=re.IGNORECASE) is not None

    # 1) Title exact match for canonical role names.
    for role_norm, role in ROLE_TITLE_INDEX:
        if role_norm and role_norm == title:
            meta = ROLE_MAP[role]
            return (
                meta["job_parent_category"],
                meta["job_sub_category"],
                role,
                0.99,
                f"title exact: {role_norm}"
            )

    candidates = {}

    def add_score(role, score, reason):
        if not role:
            return
        if role not in candidates:
            candidates[role] = {"score": 0.0, "reasons": []}
        candidates[role]["score"] += score
        candidates[role]["reasons"].append(reason)

    # 2) Weighted alias matching.
    # Strongest: title
    for alias_norm, role in ROLE_ALIAS_INDEX:
        if not alias_norm:
            continue

        # Title can use short aliases, but only with safer boundary matching.
        if contains_match(alias_norm, title):
            # Short aliases get lower title score because they are ambiguous.
            if alias_norm in DANGEROUS_SHORT_ALIASES or re.fullmatch(r"[a-z]{1,3}", alias_norm):
                add_score(role, 45, f"title short alias: {alias_norm}")
            else:
                add_score(role, 100, f"title alias: {alias_norm}")

        # Non-title fields: only safe aliases.
        if not is_safe_alias(alias_norm):
            continue

        if contains_match(alias_norm, keyword):
            add_score(role, 45, f"keyword alias: {alias_norm}")

        if contains_match(alias_norm, category):
            add_score(role, 30, f"category alias: {alias_norm}")

        # Description is weakest. Require longer aliases to avoid noise.
        if len(alias_norm) >= 5 and contains_match(alias_norm, desc):
            add_score(role, 8, f"desc alias: {alias_norm}")

    # 3) Canonical role name matching, also weighted.
    for role_norm, role in ROLE_TITLE_INDEX:
        if not role_norm:
            continue

        if contains_match(role_norm, title):
            add_score(role, 90, f"title canonical: {role_norm}")

        if contains_match(role_norm, keyword):
            add_score(role, 40, f"keyword canonical: {role_norm}")

        if contains_match(role_norm, category):
            add_score(role, 25, f"category canonical: {role_norm}")

        if len(role_norm) >= 5 and contains_match(role_norm, desc):
            add_score(role, 6, f"desc canonical: {role_norm}")

    # 4) Pick top scored role.
    if candidates:
        best_role, payload = max(candidates.items(), key=lambda x: x[1]["score"])
        best_score = payload["score"]

        # Confidence scaling.
        # >=100 usually means title hit.
        # 45~99 means weaker but usable.
        if best_score >= 100:
            conf = 0.95
        elif best_score >= 70:
            conf = 0.88
        elif best_score >= 45:
            conf = 0.78
        else:
            conf = 0.0

        if conf > 0:
            meta = ROLE_MAP[best_role]
            return (
                meta["job_parent_category"],
                meta["job_sub_category"],
                best_role,
                round(conf, 3),
                f"weighted match score={best_score:.1f}; " + "; ".join(payload["reasons"][:5])
            )

    # 5) Fuzzy title fallback against canonical role names only.
    best_role, best_score = None, 0.0
    for role_norm, role in ROLE_TITLE_INDEX:
        score = SequenceMatcher(None, title, role_norm).ratio() if title and role_norm else 0.0
        if score > best_score:
            best_role, best_score = role, score

    if best_role and best_score >= 0.86:
        meta = ROLE_MAP[best_role]
        return (
            meta["job_parent_category"],
            meta["job_sub_category"],
            best_role,
            round(best_score, 3),
            f"fuzzy title: {best_score:.3f}"
        )

    return None, None, None, 0.0, "rule no confident match" 


def try_rule_skills(job):
    pools = []
    for field in ["description_snippet", "job_description"]:
        v = clean_text(job.get(field))
        if v:
            pools.append(v)
    for field in ["skill", "specialty", "job_category"]:
        vals = safe_list(job.get(field))
        for v in vals:
            if v:
                pools.append(str(v))
    norm_text = "\n".join(pools).lower()
    found, seen = [], set()
    for canonical, patterns in SKILL_PATTERNS:
        for pat in patterns:
            if pat.search(norm_text):
                if canonical not in seen:
                    seen.add(canonical)
                    found.append(canonical)
                break
    return found[:20], len(found)


def should_use_llm(rule_role_conf, skill_count, job):
    jd_len = len(clean_text(job.get("job_description")) or "")
    if rule_role_conf >= 0.90 and skill_count >= 3:
        return False
    if jd_len < 80 and rule_role_conf >= 0.86:
        return False
    return True


def build_llm_prompt(job, rule_role, rule_skills):
    title = norm_for_match(job.get("title"))
    role_choices = []
    for role_norm, role in ROLE_TITLE_INDEX:
        score = SequenceMatcher(None, title, role_norm).ratio() if title and role_norm else 0.0
        if score >= 0.55:
            role_choices.append(role)
    if not role_choices:
        role_choices = list(ROLE_MAP.keys())[:30]
    skill_choices = list(rule_skills)
    if len(skill_choices) < 80:
        for canonical, _ in SKILL_PATTERNS:
            if canonical not in skill_choices:
                skill_choices.append(canonical)
            if len(skill_choices) >= 80:
                break
    jd = clean_text(job.get("job_description")) or clean_text(job.get("description_snippet")) or ""
    jd = jd[:3000]
    return f'''你是一個職缺分類專家。請根據職稱與 JD，在限定清單內做分類與技能標準化。\n\n職缺資料：\n- title: {clean_text(job.get("title"))}\n- company: {clean_text(job.get("company"))}\n- industry: {clean_text(job.get("industry"))}\n- category: {clean_text(job.get("category"))}\n- keyword: {clean_text(job.get("keyword"))}\n- description_snippet: {clean_text(job.get("description_snippet"))}\n- job_description: {jd}\n\n規則引擎初判：\n- rule_role: {rule_role}\n- rule_skills: {rule_skills}\n\n可選 role_normalized（只能選一個；若無法判斷可輸出 Unclassified）：\n{json.dumps(role_choices, ensure_ascii=False)}\n\n可選 skill_canonical（只能從這個清單選，最多 15 個）：\n{json.dumps(skill_choices[:80], ensure_ascii=False)}\n\n請只輸出 JSON：\n{{\n  "job_parent_category": "string or null",\n  "job_sub_category": "string or null",\n  "role_normalized": "string",\n  "role_confidence": 0.0,\n  "skill_raw": ["string"],\n  "skill_canonical": ["string"],\n  "llm_reason": "string"\n}}'''


def call_gemini(job, rule_role, rule_skills):
    if not GEMINI_API_KEY or genai is None:
        return None
    client = genai.Client(api_key=GEMINI_API_KEY)
    resp = client.models.generate_content(model=MODEL_NAME, contents=build_llm_prompt(job, rule_role, rule_skills))
    text = (getattr(resp, "text", None) or "").strip()
    text = re.sub(r"^```json\s*", "", text)
    text = re.sub(r"^```\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    data = json.loads(text)
    role = clean_text(data.get("role_normalized")) or "Unclassified"
    if role in ROLE_MAP:
        data["job_parent_category"] = ROLE_MAP[role]["job_parent_category"]
        data["job_sub_category"] = ROLE_MAP[role]["job_sub_category"]
    else:
        data["job_parent_category"] = None
        data["job_sub_category"] = None
        data["role_normalized"] = "Unclassified"
    skills, seen = [], set()
    for s in data.get("skill_canonical") or []:
        s = clean_text(s)
        if s in SKILL_SET and s not in seen:
            seen.add(s)
            skills.append(s)
    data["skill_canonical"] = skills[:15]
    return data


def transform_row(job, enable_llm=False, llm_sleep_sec=0.8):
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

    rule_parent, rule_sub, rule_role, rule_conf, rule_reason = try_rule_role(job)
    rule_skills, skill_count = try_rule_skills(job)

    final_parent, final_sub, final_role, final_conf = rule_parent, rule_sub, rule_role or "Unclassified", rule_conf
    final_skill_raw, final_skills = list(rule_skills), list(rule_skills)
    llm_reason, llm_model, llm_processed_at = f"rule: {rule_reason}", None, None

    if enable_llm and should_use_llm(rule_conf, skill_count, job):
        try:
            llm = call_gemini(job, rule_role, rule_skills)
            if llm:
                llm_role = llm.get("role_normalized")
                llm_skills = llm.get("skill_canonical") or []
                if llm_role and llm_role != "Unclassified":
                    final_parent = llm.get("job_parent_category")
                    final_sub = llm.get("job_sub_category")
                    final_role = llm_role
                    final_conf = llm.get("role_confidence") or max(rule_conf, 0.75)
                merged, seen = [], set()
                for s in list(rule_skills) + list(llm_skills):
                    if s in SKILL_SET and s not in seen:
                        seen.add(s)
                        merged.append(s)
                final_skills = merged[:15]
                final_skill_raw = llm.get("skill_raw") or final_skills
                llm_reason = llm.get("llm_reason") or llm_reason
                llm_model = MODEL_NAME
                llm_processed_at = datetime.now(timezone.utc).isoformat()
                time.sleep(llm_sleep_sec)
        except Exception as e:
            llm_reason = f"llm_failed: {e}; fallback_rule: {rule_reason}"

    quality_score = compute_quality_score(clean_text(job.get("job_description")), final_role, final_skills, salary_low_norm, work_exp_min, edu_level)
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
        "job_parent_category": final_parent,
        "job_sub_category": final_sub,
        "role_normalized": final_role,
        "role_confidence": round(float(final_conf), 3) if final_conf is not None else None,
        "skill_raw": final_skill_raw,
        "skill_canonical": final_skills,
        "llm_model": llm_model,
        "llm_reason": llm_reason,
        "quality_score": quality_score,
        "freshness_score": freshness_score,
        "raw_payload": job,
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "llm_processed_at": llm_processed_at,
    }


def parse_args():
    p = argparse.ArgumentParser(description="Clean jd_raw -> job_posting")
    p.add_argument("--limit", type=int, default=500)
    p.add_argument("--only-new", action="store_true")
    p.add_argument("--enable-llm", action="store_true")
    p.add_argument("--llm-sleep", type=float, default=0.8)
    return p.parse_args()


def main():
    args = parse_args()
    rows = fetch_jd_raw(limit=args.limit, only_new=args.only_new)
    print(f"讀到 jd_raw {len(rows)} 筆")
    outputs = []
    skipped = 0
    llm_used = 0
    QUALITY_THRESHOLD = 0.3  # quality_score 低於此值不寫入
    for idx, row in enumerate(rows, start=1):
        rec = transform_row(row, enable_llm=args.enable_llm, llm_sleep_sec=args.llm_sleep)
        if rec.get("llm_processed_at"):
            llm_used += 1
        q = rec.get("quality_score") or 0
        if q < QUALITY_THRESHOLD:
            skipped += 1
            print(f"[{idx}/{len(rows)}] SKIP (quality={q:.2f}) - {row.get('job_no')} - {clean_text(row.get('title'))}")
            continue
        outputs.append(rec)
        print(f"[{idx}/{len(rows)}] ok - {row.get('job_no')} - {clean_text(row.get('title'))} | role={rec.get('role_normalized')} | skills={len(rec.get('skill_canonical') or [])} | q={q:.2f} | llm={'Y' if rec.get('llm_processed_at') else 'N'}")
    upsert_job_posting(outputs)
    print(f"完成：寫入 job_posting {len(outputs)} 筆；跳過低品質 {skipped} 筆；LLM 使用 {llm_used} 筆")


if __name__ == "__main__":
    main()
