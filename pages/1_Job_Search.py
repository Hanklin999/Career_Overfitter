#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Page 1 — Job Search"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
from utils.supabase_client import _get, get_jd_raw_count, get_job_posting_count

st.set_page_config(page_title="Job Search | Career Overfitter", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@300;400;500&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
h1,h2,h3 { font-family: 'Syne', sans-serif; font-weight: 800; }
.tag { display:inline-block; border-radius:20px; padding:2px 10px; font-size:0.75rem; margin:2px; }
.tag-skill { background:#e8f0fe; border:1px solid #c5d8fd; color:#1a56db; }
.tag-role  { background:#fef3e8; border:1px solid #fdd5a0; color:#b45309; }
.tag-ind   { background:#f0fdf4; border:1px solid #bbf7d0; color:#15803d; }
.tag-flag  { background:#fdf4ff; border:1px solid #e9d5ff; color:#7c3aed; }
.salary    { font-weight:600; color:#0f0f0f; font-size:0.9rem; }
.detail-label { font-size:0.78rem; font-weight:700; color:#555; margin-top:10px; margin-bottom:3px; }
.detail-body  { font-size:0.82rem; color:#333; line-height:1.65; }
</style>
""", unsafe_allow_html=True)

st.markdown("<h1 style='margin-bottom:0'>🔍 Job Search</h1>", unsafe_allow_html=True)

raw_count     = get_jd_raw_count()
cleaned_count = get_job_posting_count()
c1, c2, c3   = st.columns(3)
c1.metric("jd_raw 總筆數", f"{raw_count:,}")
c2.metric("已清洗職缺",   f"{cleaned_count:,}")
c3.metric("清洗率", f"{cleaned_count/raw_count*100:.1f}%" if raw_count else "—")
st.markdown("---")

# ── 載入全部職缺（前端 filter）────────────────────────────
@st.cache_data(ttl=300)
def load_all_jobs():
    return _get("job_posting", {
        "select": (
            "job_no,title_clean,company_clean,location_county,"
            "industry_bucket,job_parent_category,job_sub_category,role_normalized,"
            "skill_canonical,salary_low,salary_high,salary_unit,"
            "work_exp_min,work_exp_max,edu_level,edu_level_int,"
            "remote_work,appear_date,quality_score,"
            "is_foreign,is_listed,"
            "job_description,manage_resp,job_category_raw"
        ),
        "order": "appear_date.desc",
        "limit": 3000,
    })

all_jobs = load_all_jobs()

# ── 建立互校驗索引 ────────────────────────────────────────
industries = sorted({j.get("industry_bucket") for j in all_jobs if j.get("industry_bucket")})
parents    = sorted({j.get("job_parent_category") for j in all_jobs if j.get("job_parent_category")})

ind_to_parents: dict = {}
par_to_industries: dict = {}
hierarchy: dict = {}

for j in all_jobs:
    ind  = j.get("industry_bucket")
    par  = j.get("job_parent_category")
    sub  = j.get("job_sub_category") or "其他"
    role = j.get("role_normalized")
    if ind and par:
        ind_to_parents.setdefault(ind, set()).add(par)
        par_to_industries.setdefault(par, set()).add(ind)
    if par and sub and role and role != "Unclassified":
        hierarchy.setdefault(par, {}).setdefault(sub, set()).add(role)

# ── Filters ──────────────────────────────────────────────
with st.expander("🔧 篩選條件", expanded=True):

    # 關鍵字 + 公司性質
    r1 = st.columns([3, 1, 1, 1, 1])
    with r1[0]: keyword      = st.text_input("職稱關鍵字", placeholder="e.g. 資料工程師")
    with r1[1]: filter_foreign = st.checkbox("🌍 外商")
    with r1[2]: filter_local   = st.checkbox("🏠 本土")
    with r1[3]: filter_listed  = st.checkbox("📈 上市櫃")
    with r1[4]: filter_remote  = st.checkbox("🌐 Remote")

    # 產業 ↔ 大類互校驗
    st.markdown("**產業 × 職能大類**")
    r2 = st.columns(2)
    with r2[0]:
        sel_industry = st.selectbox("產業", ["全部"] + industries, key="ind")
    valid_parents = sorted(ind_to_parents.get(sel_industry, set())) if sel_industry != "全部" else parents
    with r2[1]:
        sel_parent = st.selectbox("職能大類", ["全部"] + valid_parents, key="par")

    # 中類 + Role 多選
    r3 = st.columns(2)
    sub_options = sorted(hierarchy.get(sel_parent, {}).keys()) if sel_parent != "全部" else []
    with r3[0]:
        sel_sub = st.selectbox("職能中類", ["全部"] + sub_options, key="sub")
    if sel_parent != "全部":
        subs = hierarchy.get(sel_parent, {})
        if sel_sub != "全部":
            role_options = sorted(subs.get(sel_sub, set()))
        else:
            role_options = sorted({r for roles in subs.values() for r in roles})
    else:
        role_options = []
    with r3[1]:
        sel_roles = st.multiselect("Role（可多選）", role_options)

    # 薪資 + 學歷 + 筆數
    r4 = st.columns(3)
    with r4[0]:
        salary_min = st.number_input("最低月薪（千元）", min_value=0, max_value=300, value=0, step=5)
    with r4[1]:
        edu_options = ["不限", "高中以下", "高中", "專科", "大學", "碩士", "博士"]
        sel_edu = st.selectbox("最低學歷", edu_options)
    with r4[2]:
        limit = st.slider("顯示筆數", 10, 200, 50, 10)

# ── 前端 Filter ───────────────────────────────────────────
edu_int_map = {"不限": -1, "高中以下": 0, "高中": 1, "專科": 2, "大學": 3, "碩士": 4, "博士": 5}
min_edu_int = edu_int_map[sel_edu]

def job_passes(j):
    if keyword and keyword.lower() not in (j.get("title_clean") or "").lower():
        return False
    if sel_industry != "全部" and j.get("industry_bucket") != sel_industry:
        return False
    if sel_parent != "全部" and j.get("job_parent_category") != sel_parent:
        return False
    if sel_sub != "全部" and j.get("job_sub_category") != sel_sub:
        return False
    if sel_roles and j.get("role_normalized") not in sel_roles:
        return False
    if salary_min and (not j.get("salary_low") or j.get("salary_low") < salary_min * 1000):
        return False
    if min_edu_int >= 0:
        edu_int = j.get("edu_level_int")
        if edu_int is None or edu_int < min_edu_int:
            return False
    # 公司性質 OR 邏輯
    nature_active = filter_foreign or filter_local or filter_listed
    if nature_active:
        ok = False
        if filter_foreign and j.get("is_foreign"):            ok = True
        if filter_listed  and j.get("is_listed"):             ok = True
        if filter_local   and not j.get("is_foreign") and not j.get("is_listed"): ok = True
        if not ok:
            return False
    if filter_remote and not j.get("remote_work"):
        return False
    return True

filtered = [j for j in all_jobs if job_passes(j)]
total_found = len(filtered)
filtered = filtered[:limit]

st.markdown(f"<p style='color:#888;font-size:0.85rem;'>符合條件：{total_found} 筆，顯示前 {len(filtered)} 筆</p>", unsafe_allow_html=True)

if not filtered:
    st.info("目前沒有符合條件的職缺，請調整篩選條件。")
    st.stop()

# ── Job Cards（可展開）────────────────────────────────────
for job in filtered:
    title   = job.get("title_clean") or "（無職稱）"
    company = job.get("company_clean") or ""
    loc     = job.get("location_county") or ""
    role_n  = job.get("role_normalized") or ""
    ind_b   = job.get("industry_bucket") or ""
    skills  = job.get("skill_canonical") or []
    sal_low = job.get("salary_low")
    sal_hi  = job.get("salary_high")
    sal_u   = job.get("salary_unit") or "月薪"
    exp_min = job.get("work_exp_min")
    exp_max = job.get("work_exp_max")
    edu     = job.get("edu_level") or ""
    remote  = job.get("remote_work", 0)
    date    = job.get("appear_date") or ""
    quality = job.get("quality_score") or 0
    is_for  = job.get("is_foreign", False)
    is_lst  = job.get("is_listed", False)
    jd_text = job.get("job_description") or ""
    manage  = job.get("manage_resp") or ""
    cat_raw = job.get("job_category_raw") or ""

    salary_str = (
        f"{sal_low//1000}K–{sal_hi//1000}K／{sal_u}" if sal_low and sal_hi else
        f"{sal_low//1000}K+／{sal_u}" if sal_low else "薪資面議"
    )
    exp_str = (
        f"{exp_min}–{exp_max} 年" if exp_min is not None and exp_max is not None else
        f"{exp_min}+ 年" if exp_min is not None else ""
    )
    meta_parts = [p for p in [company, loc, exp_str, edu] if p]
    meta_str   = " · ".join(meta_parts)
    q_pct      = int(quality * 100)
    q_color    = "#15803d" if quality >= 0.7 else "#b45309" if quality >= 0.4 else "#aaa"

    flags = []
    if is_for:  flags.append("🌍 外商")
    if is_lst:  flags.append("📈 上市櫃")
    if not is_for and not is_lst: flags.append("🏠 本土")
    if remote:  flags.append("🌐 Remote")

    role_tag   = f'<span class="tag tag-role">{role_n}</span>' if role_n and role_n != "Unclassified" else ""
    ind_tag    = f'<span class="tag tag-ind">{ind_b}</span>' if ind_b else ""
    flag_tags  = " ".join(f'<span class="tag tag-flag">{f}</span>' for f in flags)
    skill_preview = "".join(f'<span class="tag tag-skill">{s}</span>' for s in (skills[:5] if isinstance(skills, list) else []))

    header = f"**{title}** · {company}　｜　{salary_str}　｜　{date}"

    with st.expander(header, expanded=False):
        st.markdown(f"""
        <div style='margin-bottom:10px;'>
          <div style='font-size:0.82rem;color:#555;margin-bottom:6px;'>{meta_str}</div>
          <div>{role_tag}{ind_tag}{flag_tags}</div>
          <div style='margin-top:6px;'>{skill_preview}</div>
          <div style='margin-top:4px;font-size:0.75rem;color:{q_color};'>品質分數 {q_pct}%</div>
        </div>
        """, unsafe_allow_html=True)

        if cat_raw:
            st.markdown(f"<div class='detail-label'>職類</div><div class='detail-body'>{cat_raw}</div>", unsafe_allow_html=True)

        if jd_text:
            st.markdown("<div class='detail-label'>職缺描述</div>", unsafe_allow_html=True)
            st.markdown(
                f"<div class='detail-body' style='max-height:280px;overflow-y:auto;"
                f"white-space:pre-wrap;border:1px solid #f0ede8;border-radius:6px;padding:10px;background:#fafaf8;'>"
                f"{jd_text[:2500]}{'...' if len(jd_text) > 2500 else ''}</div>",
                unsafe_allow_html=True,
            )

        if manage:
            st.markdown(f"<div class='detail-label'>管理職責</div><div class='detail-body'>{manage}</div>", unsafe_allow_html=True)

        if isinstance(skills, list) and len(skills) > 5:
            all_skill_tags = " ".join(f'<span class="tag tag-skill">{s}</span>' for s in skills)
            st.markdown(f"<div class='detail-label'>全部技能（{len(skills)} 項）</div>{all_skill_tags}", unsafe_allow_html=True)

st.markdown("---")
if st.button("📥 匯出為 CSV"):
    df  = pd.DataFrame(filtered)
    csv = df.to_csv(index=False, encoding="utf-8-sig")
    st.download_button("下載 CSV", data=csv, file_name="jobs_export.csv", mime="text/csv")
