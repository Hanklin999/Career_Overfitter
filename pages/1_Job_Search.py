#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Page 1 — Job Search
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
from utils.supabase_client import (
    get_job_postings,
    get_jd_raw_count,
    get_job_posting_count,
)

st.set_page_config(page_title="Job Search | Career Overfitter", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@300;400;500&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
h1,h2,h3 { font-family: 'Syne', sans-serif; font-weight: 800; }
.job-card { border:1px solid #e0ddd7; border-radius:10px; padding:1.2rem 1.4rem; margin-bottom:0.8rem; background:#fff; }
.job-title { font-family:'Syne',sans-serif; font-weight:700; font-size:1.05rem; color:#0f0f0f; }
.job-meta { font-size:0.82rem; color:#666; margin:4px 0 8px 0; }
.tag { display:inline-block; border-radius:20px; padding:2px 10px; font-size:0.75rem; margin:2px; }
.tag-skill { background:#e8f0fe; border:1px solid #c5d8fd; color:#1a56db; }
.tag-role  { background:#fef3e8; border:1px solid #fdd5a0; color:#b45309; }
.tag-ind   { background:#f0fdf4; border:1px solid #bbf7d0; color:#15803d; }
.salary    { font-weight:600; color:#0f0f0f; font-size:0.9rem; }
</style>
""", unsafe_allow_html=True)

st.markdown("<h1 style='margin-bottom:0'>🔍 Job Search</h1>", unsafe_allow_html=True)

raw_count = get_jd_raw_count()
cleaned_count = get_job_posting_count()
c1, c2, c3 = st.columns(3)
c1.metric("jd_raw 總筆數", f"{raw_count:,}")
c2.metric("已清洗職缺", f"{cleaned_count:,}")
c3.metric("清洗率", f"{cleaned_count/raw_count*100:.1f}%" if raw_count else "—")

st.markdown("---")

# ── 載入 role 階層 ────────────────────────────────────────
@st.cache_data(ttl=600)
def get_role_hierarchy():
    """從 job_posting 撈 parent/sub/role 三層結構"""
    from utils.supabase_client import _get
    rows = _get("job_posting", {
        "select": "job_parent_category,job_sub_category,role_normalized",
        "limit": 5000,
    })
    hierarchy = {}  # parent -> sub -> set(roles)
    for r in rows:
        parent = r.get("job_parent_category") or "其他"
        sub = r.get("job_sub_category") or "其他"
        role = r.get("role_normalized")
        if not role or role == "Unclassified":
            continue
        hierarchy.setdefault(parent, {}).setdefault(sub, set()).add(role)
    return hierarchy

@st.cache_data(ttl=600)
def get_industry_list_raw():
    from utils.supabase_client import _get
    rows = _get("job_posting", {"select": "industry_bucket", "limit": 3000})
    inds = sorted({r["industry_bucket"] for r in rows if r.get("industry_bucket")})
    return ["全部"] + inds

hierarchy = get_role_hierarchy()
industries = get_industry_list_raw()

# ── Filters ──────────────────────────────────────────────
with st.expander("🔧 篩選條件", expanded=True):
    row1 = st.columns([2, 2, 2, 1])
    with row1[0]:
        keyword = st.text_input("職稱關鍵字", placeholder="e.g. 資料工程師")
    with row1[1]:
        industry = st.selectbox("產業", industries)
    with row1[2]:
        remote_only = st.checkbox("Remote only")

    st.markdown("**Role 篩選（大類 → 中類 → 多選細項）**")
    rc1, rc2, rc3 = st.columns(3)

    parent_options = ["全部"] + sorted(hierarchy.keys())
    with rc1:
        selected_parent = st.selectbox("大類", parent_options)

    sub_options = ["全部"]
    if selected_parent != "全部" and selected_parent in hierarchy:
        sub_options += sorted(hierarchy[selected_parent].keys())
    with rc2:
        selected_sub = st.selectbox("中類", sub_options)

    role_options = []
    if selected_parent != "全部":
        subs = hierarchy.get(selected_parent, {})
        if selected_sub != "全部":
            role_options = sorted(subs.get(selected_sub, set()))
        else:
            for roles in subs.values():
                role_options += list(roles)
            role_options = sorted(set(role_options))
    with rc3:
        selected_roles = st.multiselect("Role（可多選）", role_options)

    s1, s2 = st.columns(2)
    with s1:
        salary_min = st.number_input("最低月薪（千元）", min_value=0, max_value=300, value=0, step=5)
    with s2:
        limit = st.slider("顯示筆數", 10, 100, 30, 10)

# ── Fetch ─────────────────────────────────────────────────
salary_min_val = int(salary_min * 1000) if salary_min else None

# 多選 role 處理：先撈再 filter
all_jobs = get_job_postings(
    industry=industry,
    keyword=keyword or None,
    salary_min=salary_min_val,
    remote_only=remote_only,
    limit=500,  # 撈多一點再前端 filter
)

# 前端 filter role（多選）
if selected_roles:
    jobs = [j for j in all_jobs if j.get("role_normalized") in selected_roles]
elif selected_parent != "全部":
    valid_roles = set()
    subs = hierarchy.get(selected_parent, {})
    if selected_sub != "全部":
        valid_roles = subs.get(selected_sub, set())
    else:
        for roles in subs.values():
            valid_roles.update(roles)
    jobs = [j for j in all_jobs if j.get("role_normalized") in valid_roles]
else:
    jobs = all_jobs

jobs = jobs[:limit]

st.markdown(f"<p style='color:#888;font-size:0.85rem;'>找到 {len(jobs)} 筆職缺</p>", unsafe_allow_html=True)

if not jobs:
    st.info("目前沒有符合條件的職缺，請調整篩選條件。")
    st.stop()

# ── Job Cards ─────────────────────────────────────────────
for job in jobs:
    title = job.get("title_clean") or "（無職稱）"
    company = job.get("company_clean") or ""
    location = job.get("location_county") or ""
    role_n = job.get("role_normalized") or ""
    industry_b = job.get("industry_bucket") or ""
    skills = job.get("skill_canonical") or []
    salary_low = job.get("salary_low")
    salary_high = job.get("salary_high")
    salary_unit = job.get("salary_unit") or "月薪"
    exp_min = job.get("work_exp_min")
    exp_max = job.get("work_exp_max")
    edu = job.get("edu_level") or ""
    remote = job.get("remote_work", 0)
    appear_date = job.get("appear_date") or ""
    quality = job.get("quality_score") or 0

    if salary_low and salary_high:
        salary_str = f"{salary_low//1000}K–{salary_high//1000}K／{salary_unit}"
    elif salary_low:
        salary_str = f"{salary_low//1000}K+／{salary_unit}"
    else:
        salary_str = "薪資面議"

    if exp_min is not None and exp_max is not None:
        exp_str = f"{exp_min}–{exp_max} 年"
    elif exp_min is not None:
        exp_str = f"{exp_min}+ 年"
    else:
        exp_str = ""

    role_tag = f'<span class="tag tag-role">{role_n}</span>' if role_n and role_n != "Unclassified" else ""
    ind_tag = f'<span class="tag tag-ind">{industry_b}</span>' if industry_b else ""
    remote_tag = '<span class="tag tag-ind">🌐 Remote</span>' if remote else ""
    skill_tags = "".join(f'<span class="tag tag-skill">{s}</span>' for s in (skills[:5] if isinstance(skills, list) else []))

    meta_parts = [p for p in [company, location, exp_str, edu] if p]
    meta_str = " · ".join(meta_parts)
    quality_pct = int(quality * 100)
    quality_color = "#15803d" if quality >= 0.7 else "#b45309" if quality >= 0.4 else "#aaa"

    st.markdown(f"""
    <div class="job-card">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;">
        <div style="flex:1;">
          <div class="job-title">{title}</div>
          <div class="job-meta">{meta_str}</div>
          <div>{role_tag}{ind_tag}{remote_tag}</div>
          <div style="margin-top:6px;">{skill_tags}</div>
        </div>
        <div style="text-align:right;min-width:120px;">
          <div class="salary">{salary_str}</div>
          <div style="font-size:0.75rem;color:{quality_color};margin-top:4px;">品質 {quality_pct}%</div>
          <div style="font-size:0.75rem;color:#aaa;">{appear_date}</div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("---")
if st.button("📥 匯出為 CSV"):
    df = pd.DataFrame(jobs)
    csv = df.to_csv(index=False, encoding="utf-8-sig")
    st.download_button("下載 CSV", data=csv, file_name="jobs_export.csv", mime="text/csv")
