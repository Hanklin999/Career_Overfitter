#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
共用 Supabase 查詢工具
所有 page 透過此模組讀取資料，避免重複實作連線邏輯。
"""

import os
import requests
import streamlit as st
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

HEADERS = {
    "apikey": SUPABASE_KEY,
    # 注意：新版 sb_secret_... key 不是 JWT，如果塞進 Authorization: Bearer
    # header 會被 PostgREST 判定成不合法的 JWT 直接拒絕（401）。新版 key
    # 只需要放在 apikey header，不要再加 Authorization header。
    "Content-Type": "application/json",
    "Accept": "application/json",
}


def _get(table: str, params: Dict[str, Any], timeout: int = 30) -> List[Dict]:
    """基礎 GET，自動處理錯誤並回傳 list。"""
    if not SUPABASE_URL or not SUPABASE_KEY:
        st.error("❌ 請在 .env 設定 SUPABASE_URL 與 SUPABASE_KEY")
        return []
    try:
        resp = requests.get(
            f"{SUPABASE_URL}/{table}",
            headers=HEADERS,
            params=params,
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json() or []
    except Exception as e:
        st.error(f"DB 查詢失敗 ({table}): {e}")
        return []


# ── job_posting 查詢 ──────────────────────────────────────

@st.cache_data(ttl=300)
def get_job_postings(
    role: Optional[str] = None,
    industry: Optional[str] = None,
    keyword: Optional[str] = None,
    salary_min: Optional[int] = None,
    remote_only: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> List[Dict]:
    params: Dict[str, Any] = {
        "select": (
            "job_no,title_clean,company_clean,location_county,"
            "industry_bucket,role_normalized,skill_canonical,"
            "salary_low,salary_high,salary_unit,"
            "work_exp_min,work_exp_max,edu_level,"
            "remote_work,appear_date,quality_score"
        ),
        "order": "appear_date.desc",
        "limit": limit,
        "offset": offset,
    }
    if role and role != "全部":
        params["role_normalized"] = f"eq.{role}"
    if industry and industry != "全部":
        params["industry_bucket"] = f"eq.{industry}"
    if keyword:
        params["title_clean"] = f"ilike.*{keyword}*"
    if salary_min:
        params["salary_low"] = f"gte.{salary_min}"
    if remote_only:
        params["remote_work"] = "neq.0"
    return _get("job_posting", params)


@st.cache_data(ttl=600)
def get_role_list() -> List[str]:
    rows = _get("job_posting", {"select": "role_normalized", "limit": 2000})
    roles = sorted({r["role_normalized"] for r in rows if r.get("role_normalized") and r["role_normalized"] != "Unclassified"})
    return ["全部"] + roles


@st.cache_data(ttl=600)
def get_industry_list() -> List[str]:
    rows = _get("job_posting", {"select": "industry_bucket", "limit": 2000})
    industries = sorted({r["industry_bucket"] for r in rows if r.get("industry_bucket")})
    return ["全部"] + industries


@st.cache_data(ttl=600)
def get_skill_demand(top_n: int = 30) -> List[Dict]:
    """統計 skill_canonical 出現頻率（從 job_posting 展開）。"""
    rows = _get("job_posting", {"select": "skill_canonical", "limit": 5000})
    from collections import Counter
    counter: Counter = Counter()
    for row in rows:
        skills = row.get("skill_canonical") or []
        if isinstance(skills, list):
            counter.update(skills)
    return [{"skill": k, "count": v} for k, v in counter.most_common(top_n)]


@st.cache_data(ttl=600)
def get_salary_by_role() -> List[Dict]:
    rows = _get(
        "job_posting",
        {
            "select": "role_normalized,salary_low,salary_high,salary_unit",
            "salary_low": "not.is.null",
            "limit": 3000,
        },
    )
    return rows


@st.cache_data(ttl=600)
def get_jd_raw_count() -> int:
    resp_headers = {"Range-Unit": "items", "Range": "0-0", **HEADERS, "Prefer": "count=exact"}
    try:
        r = requests.get(f"{SUPABASE_URL}/jd_raw", headers=resp_headers, params={"select": "job_no"}, timeout=15)
        content_range = r.headers.get("Content-Range", "*/0")
        return int(content_range.split("/")[-1])
    except Exception:
        return 0


@st.cache_data(ttl=600)
def get_job_posting_count() -> int:
    resp_headers = {"Range-Unit": "items", "Range": "0-0", **HEADERS, "Prefer": "count=exact"}
    try:
        r = requests.get(f"{SUPABASE_URL}/job_posting", headers=resp_headers, params={"select": "job_no"}, timeout=15)
        content_range = r.headers.get("Content-Range", "*/0")
        return int(content_range.split("/")[-1])
    except Exception:
        return 0


@st.cache_data(ttl=300)
def get_analytics_rows(limit: int = 5000) -> List[Dict]:
    """Analytics Career Map 系列頁面共用的批次查詢。
    欄位涵蓋 domain/tech-depth 分類、薪資、技能、公司等彙整所需的所有欄位。"""
    return _get("job_posting", {
        "select": (
            "job_no,title_clean,company_clean,location_county,"
            "industry_bucket,industry_raw,"
            "job_parent_category,job_sub_category,role_normalized,"
            "skill_canonical,salary_low,salary_high,salary_unit,"
            "work_exp_min,work_exp_max,edu_level,"
            "remote_work,appear_date,quality_score"
        ),
        "order": "appear_date.desc",
        "limit": limit,
    })
