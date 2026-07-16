#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Page 5 — Jobs (Explore Opportunities)

跟舊版 Job Search 最大的差別：篩選的入口是 Career Path（先選 Product
Analytics，才看到 Growth Analyst / Marketplace Analyst 這些子分類），
不是 Job Title 關鍵字或原始職能大類/中類。語意搜尋也先告訴你「這聽起來
像哪些 Career Path」，再列出職缺 — 職缺永遠是最後一步，不是第一步。
"""

import sys, re
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
from collections import Counter

from utils.supabase_client import _get, get_jd_raw_count, get_job_posting_count
from utils import rag_retrieval
from utils import career_taxonomy as ct
from utils.ui_taxonomy import (
    get_industry_parents, get_industry_subs,
    filter_label, FILTER_STYLE,
)

st.set_page_config(page_title="Jobs | Career Overfitter", layout="wide")

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@300;400;500&display=swap');
html, body, [class*="css"] {{ font-family: 'DM Sans', sans-serif; background:#f9f8f6; }}
h1,h2,h3 {{ font-family: 'Syne', sans-serif; font-weight: 800; color:#111; }}
.tag {{
    display: inline-block; border-radius: 4px; padding: 2px 9px;
    font-size: 0.74rem; font-weight: 500; margin: 2px 3px 2px 0; letter-spacing: 0.02em;
}}
.tag-skill {{ background:#e8edf5; color:#1e3a5f; }}
.tag-role  {{ background:#f0ebe2; color:#5c3d11; }}
.tag-flag  {{ background:#ebebeb; color:#333; }}
.tag-ind   {{ background:#f0ebe2; color:#5c3d11; }}
.tag-path  {{ background:#e0f2e9; color:#1e5c3f; }}
.job-meta {{ font-size:0.81rem; color:#666; margin:4px 0 8px 0; }}
.detail-label {{
    font-size:0.76rem; font-weight:700; color:#777;
    margin-top:10px; margin-bottom:3px; text-transform:uppercase; letter-spacing:0.06em;
}}
.detail-body {{ font-size:0.83rem; color:#222; line-height:1.7; }}
.quality-badge {{ font-size:0.72rem; font-weight:600; padding:1px 7px; border-radius:3px; }}
.link-104 {{
    display: inline-flex; align-items: center; gap: 4px;
    font-size: 0.78rem; font-weight: 600; color: #e54d2e;
    text-decoration: none; padding: 3px 10px;
    border: 1px solid #f5c2b8; border-radius: 4px; background: #fff8f7;
}}
.link-104:hover {{ background:#fdeae6; text-decoration:none; }}
.path-hint {{
    border:1px solid #cfe3d8; background:#f2f8f5; border-radius:10px;
    padding:0.9rem 1rem; margin-bottom:0.8rem;
}}
{FILTER_STYLE}
</style>
""", unsafe_allow_html=True)

st.markdown("<h1 style='margin-bottom:0'>🎯 Explore Opportunities</h1>", unsafe_allow_html=True)
st.caption("先選 Career Path，職缺永遠是最後一步。")

raw_count     = get_jd_raw_count()
cleaned_count = get_job_posting_count()
c1, c2, c3   = st.columns(3)
c1.metric("jd_raw 總筆數", f"{raw_count:,}")
c2.metric("已清洗職缺",    f"{cleaned_count:,}")
c3.metric("清洗率", f"{cleaned_count/raw_count*100:.1f}%" if raw_count else "—")
st.markdown("---")


@st.cache_data(ttl=300)
def load_all_jobs():
    return _get("job_posting", {
        "select": (
            "job_no,title_clean,company_clean,location_county,"
            "industry_bucket,industry_raw,"
            "job_parent_category,job_sub_category,role_normalized,"
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


def parse_cat_raw(raw) -> list:
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    s = str(raw).strip().strip("[]")
    items = re.findall(r"['\"]([^'\"]+)['\"]", s)
    return items if items else [x.strip() for x in s.split(",") if x.strip()]


def render_job_card(job, extra_badge_html: str = ""):
    title    = job.get("title_clean") or "（無職稱）"
    company  = job.get("company_clean") or ""
    loc      = job.get("location_county") or ""
    role_n   = job.get("role_normalized") or ""
    ind_b    = job.get("industry_bucket") or ""
    skills   = job.get("skill_canonical") or []
    sal_low  = job.get("salary_low")
    sal_hi   = job.get("salary_high")
    sal_u    = job.get("salary_unit") or "月薪"
    exp_min  = job.get("work_exp_min")
    exp_max  = job.get("work_exp_max")
    edu      = job.get("edu_level") or ""
    remote   = job.get("remote_work", 0)
    date     = job.get("appear_date") or ""
    quality  = job.get("quality_score") or 0
    is_for   = job.get("is_foreign", False)
    is_lst   = job.get("is_listed", False)
    jd_text  = job.get("job_description") or ""
    manage   = job.get("manage_resp") or ""
    cat_raw  = job.get("job_category_raw") or ""
    job_no   = job.get("job_no") or ""

    career_domain = ct.get_domain(role_n)

    salary_str = (
        f"{sal_low//1000}K–{sal_hi//1000}K／{sal_u}" if sal_low and sal_hi else
        f"{sal_low//1000}K+／{sal_u}"                 if sal_low            else "薪資面議"
    )
    exp_str  = (
        f"{exp_min}–{exp_max} 年" if exp_min is not None and exp_max is not None else
        f"{exp_min}+ 年"          if exp_min is not None                          else ""
    )
    meta_str = " · ".join(p for p in [company, loc, exp_str, edu] if p)
    q_pct    = int(quality * 100)
    q_bg     = "#d1fae5" if quality >= 0.7 else "#fef3c7" if quality >= 0.4 else "#f3f4f6"
    q_fg     = "#065f46" if quality >= 0.7 else "#78350f" if quality >= 0.4 else "#6b7280"

    flags = []
    if is_for:                       flags.append("外商")
    elif not is_for and not is_lst:  flags.append("本土")
    if is_lst:                       flags.append("上市櫃")
    if remote:                       flags.append("Remote")

    path_tag   = f'<span class="tag tag-path">🧭 {career_domain}</span>' if career_domain else ""
    role_tag   = f'<span class="tag tag-role">{role_n}</span>' if role_n and role_n != "Unclassified" else ""
    ind_tag    = f'<span class="tag tag-ind">{ind_b}</span>'   if ind_b else ""
    flag_tags  = " ".join(f'<span class="tag tag-flag">{f}</span>' for f in flags)
    skill_tags = "".join(f'<span class="tag tag-skill">{s}</span>' for s in (skills[:5] if isinstance(skills, list) else []))
    q_badge    = f'<span class="quality-badge" style="background:{q_bg};color:{q_fg};">品質 {q_pct}%</span>'

    link_104_html = ""
    if job_no:
        url_104 = f"https://www.104.com.tw/job/{job_no}"
        link_104_html = (
            f'<a href="{url_104}" target="_blank" rel="noopener noreferrer" class="link-104">'
            f'<svg width="12" height="12" viewBox="0 0 24 24" fill="none" '
            f'stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">'
            f'<path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/>'
            f'<polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>'
            f'</svg>104 查看原始職缺</a>'
        )

    cat_items      = parse_cat_raw(cat_raw)
    cat_chips_html = ""
    if cat_items:
        chips = "".join(f'<span class="tag-cat">{c}</span>' for c in cat_items)
        cat_chips_html = f"<div class='detail-label'>職類</div><div style='margin-top:4px;'>{chips}</div>"

    header = f"**{title}** · {company}　｜　{salary_str}　｜　{date}"

    with st.expander(header, expanded=False):
        st.markdown(f"""
        <div style='padding:4px 0 10px 0;'>
          <div class='job-meta'>{meta_str}</div>
          <div style='margin-bottom:6px;display:flex;align-items:center;flex-wrap:wrap;gap:4px;'>
            {path_tag}{role_tag}{ind_tag}{flag_tags}{extra_badge_html}&nbsp;&nbsp;{q_badge}
            <span style='flex:1'></span>{link_104_html}
          </div>
          <div>{skill_tags}</div>
        </div>
        """, unsafe_allow_html=True)

        if cat_chips_html:
            st.markdown(cat_chips_html, unsafe_allow_html=True)

        if jd_text:
            st.markdown("<div class='detail-label'>職缺描述</div>", unsafe_allow_html=True)
            st.markdown(
                f"<div class='detail-body' style='max-height:260px;overflow-y:auto;"
                f"white-space:pre-wrap;border:1px solid #e5e2db;border-radius:6px;"
                f"padding:12px;background:#fafaf8;'>"
                f"{jd_text[:2500]}{'…' if len(jd_text) > 2500 else ''}</div>",
                unsafe_allow_html=True,
            )

        if manage:
            st.markdown(f"<div class='detail-label'>管理職責</div><div class='detail-body'>{manage}</div>",
                        unsafe_allow_html=True)

        if isinstance(skills, list) and len(skills) > 5:
            all_skill_tags = "".join(f'<span class="tag tag-skill">{s}</span>' for s in skills)
            st.markdown(
                f"<div class='detail-label'>全部技能（{len(skills)} 項）</div>"
                f"<div style='margin-top:4px;'>{all_skill_tags}</div>",
                unsafe_allow_html=True,
            )


# ── 你想做什麼樣的工作？（先分流到 Career Path，再列職缺） ──
st.markdown("### 💬 你想做什麼樣的工作？")
st.caption(
    "不用想職稱關鍵字，直接描述你喜歡做的事。系統會先告訴你這聽起來像哪些 Career Path，"
    "再列出對應的真實職缺 — 跟下面的結構化篩選是獨立的兩種找法。"
)

if not rag_retrieval.is_available():
    st.info("尚未設定 RAG 檢索（需要先跑過 sql/001_enable_pgvector_rag.sql 並執行過 backfill_embeddings.py），這個功能暫時無法使用。")
else:
    semantic_query = st.text_input(
        "描述你想做的工作",
        placeholder="例如：我喜歡做實驗分析，但不想碰太重的 ML；或：我喜歡跟人溝通、用 SQL 拉數據",
        key="semantic_query_input",
    )
    semantic_count = st.slider("最多列出幾筆職缺", 5, 30, 10, 5, key="semantic_count")

    if st.button("🔍 找出符合的 Career Path", type="primary") and semantic_query.strip():
        with st.spinner("檢索中..."):
            semantic_results = rag_retrieval.retrieve_similar_jobs(semantic_query, match_count=semantic_count)
        st.session_state["semantic_search_results"] = semantic_results
        st.session_state["semantic_search_query"] = semantic_query

    semantic_results = st.session_state.get("semantic_search_results", [])
    if semantic_results:
        # 先算出這批檢索結果落在哪些 Career Path，讓使用者先看「方向」
        domain_hits = Counter()
        for r in semantic_results:
            role_n = r.get("role_normalized")
            d = ct.get_domain(role_n)
            if d:
                domain_hits[d] += 1

        if domain_hits:
            top_paths = domain_hits.most_common(3)
            path_chips = " ".join(
                f'<span class="tag tag-path">🧭 {d}（{n} 筆）</span>' for d, n in top_paths
            )
            st.markdown(
                f"<div class='path-hint'>這聽起來最像：{path_chips}</div>",
                unsafe_allow_html=True,
            )

        st.markdown(
            f"「{st.session_state.get('semantic_search_query', '')}」共找到 "
            f"**{len(semantic_results)}** 筆相關職缺（依相似度排序）："
        )

        all_jobs_by_no = {j.get("job_no"): j for j in all_jobs}

        for r in semantic_results:
            job_no     = r.get("job_no")
            similarity = r.get("similarity")
            sim_txt    = f"{similarity:.2f}" if isinstance(similarity, (int, float)) else "—"
            sim_badge  = (
                f'<span class="tag" style="background:#ecfdf5;border:1px solid #a7f3d0;'
                f'color:#047857;">相似度 {sim_txt}</span>'
            )

            full_job = all_jobs_by_no.get(job_no)
            if full_job:
                render_job_card(full_job, extra_badge_html=sim_badge)
            else:
                title  = r.get("title_clean") or "（無職稱）"
                role_n = r.get("role_normalized") or ""
                desc   = r.get("job_description") or ""
                url_104 = f"https://www.104.com.tw/job/{job_no}" if job_no else ""

                with st.expander(f"**{title}**　·　相似度 {sim_txt}", expanded=False):
                    if role_n:
                        st.markdown(f'<span class="tag tag-role">{role_n}</span>', unsafe_allow_html=True)
                    if desc:
                        st.markdown(
                            f"<div class='detail-body' style='margin-top:8px;'>"
                            f"{desc[:600]}{'…' if len(desc) > 600 else ''}</div>",
                            unsafe_allow_html=True,
                        )
                    if url_104:
                        st.markdown(f"[104 查看原始職缺]({url_104})")

st.markdown("---")


# ── Filters — Career Path 是第一個、最主要的篩選條件 ───────
with st.expander("🔧 篩選條件", expanded=True):

    st.markdown(filter_label("🧭 Career Path", first=True), unsafe_allow_html=True)
    incoming_role = st.session_state.pop("jobs_filter_role", None)

    path_cols = st.columns(2)
    with path_cols[0]:
        domain_opts = ["全部"] + ct.DOMAIN_ORDER
        default_domain_idx = 0
        if incoming_role:
            d = ct.get_domain(incoming_role)
            if d:
                default_domain_idx = domain_opts.index(d)
        sel_career_domain = st.selectbox("Career Path（領域）", domain_opts, index=default_domain_idx, key="career_domain_filter")
    with path_cols[1]:
        if sel_career_domain != "全部":
            sub_role_opts = ct.list_roles_in_domain(sel_career_domain)
            default_roles = [incoming_role] if incoming_role in sub_role_opts else []
            sel_career_roles = st.multiselect(
                "子分類職稱（可多選，未選＝該領域全部）", sub_role_opts, default=default_roles, key="career_role_filter",
            )
        else:
            sel_career_roles = []
            st.caption("先選一個 Career Path 領域，才能選子分類職稱")

    keyword = st.text_input("職稱關鍵字（進階，選填）", placeholder="e.g. 資料工程師")

    st.markdown(filter_label("🏢 公司性質"), unsafe_allow_html=True)
    sel_nature = st.multiselect(
        "公司類型（未選＝全部）", options=["外商", "本土"], default=["外商", "本土"], key="nature",
        help="可複選；清空選項代表不限制"
    )
    sel_listing: list = []
    if "本土" in sel_nature:
        sel_listing = st.multiselect(
            "↳ 本土上市條件（未選＝全部）",
            options=["上市櫃", "非上市櫃"], default=["上市櫃", "非上市櫃"], key="listing",
        )
    filter_remote = st.checkbox("Remote 優先")

    st.markdown(filter_label("🏭 選擇產業"), unsafe_allow_html=True)
    r_ind = st.columns(2)
    ind_parent_opts = ["全部"] + get_industry_parents(all_jobs)
    with r_ind[0]:
        sel_industry = st.selectbox("產業大類", ind_parent_opts, key="ind")
    with r_ind[1]:
        ind_sub_opts = ["全部"] + (get_industry_subs(all_jobs, sel_industry) if sel_industry != "全部" else [])
        sel_industry_sub = st.selectbox("產業別", ind_sub_opts, key="ind_sub",
                                        disabled=(sel_industry == "全部"))

    st.markdown(filter_label("⚙️ 其他條件"), unsafe_allow_html=True)
    r4 = st.columns(3)
    with r4[0]:
        salary_min = st.number_input("最低月薪（千元）", min_value=0, max_value=300, value=0, step=5)
    with r4[1]:
        edu_options = ["不限", "高中以下", "高中", "專科", "大學", "碩士", "博士"]
        sel_edu = st.selectbox("最低學歷", edu_options)
    with r4[2]:
        limit = st.slider("顯示筆數", 10, 200, 50, 10)


# ── Filter logic ──────────────────────────────────────────
edu_int_map = {"不限": -1, "高中以下": 0, "高中": 1, "專科": 2, "大學": 3, "碩士": 4, "博士": 5}
min_edu_int = edu_int_map[sel_edu]
nature_is_all  = not sel_nature or set(sel_nature) == {"外商", "本土"}
listing_is_all = not sel_listing or set(sel_listing) == {"上市櫃", "非上市櫃"}


def job_passes(j) -> bool:
    role_n = j.get("role_normalized")
    if sel_career_domain != "全部":
        if ct.get_domain(role_n) != sel_career_domain:
            return False
        # sel_career_roles 是「合併後」的子分類職稱（display_role），
        # role_n 是原始職稱，兩者要透過 get_display_role 對齊，
        # 不然合併顯示後這裡永遠比對不到，篩選會整批漏掉。
        if sel_career_roles and ct.get_display_role(role_n) not in sel_career_roles:
            return False
    if keyword and keyword.lower() not in (j.get("title_clean") or "").lower():
        return False
    if sel_industry != "全部"     and j.get("industry_bucket") != sel_industry:      return False
    if sel_industry_sub != "全部" and j.get("industry_raw") != sel_industry_sub:      return False
    if salary_min and (not j.get("salary_low") or j.get("salary_low") < salary_min * 1000):
        return False
    if min_edu_int >= 0:
        edu_int = j.get("edu_level_int")
        if edu_int is None or edu_int < min_edu_int:
            return False
    if not nature_is_all:
        is_for = bool(j.get("is_foreign"))
        is_lst = bool(j.get("is_listed"))
        ok = False
        if "外商" in sel_nature and is_for:
            ok = True
        if "本土" in sel_nature and not is_for:
            if listing_is_all:
                ok = True
            else:
                if "上市櫃" in sel_listing and is_lst:    ok = True
                if "非上市櫃" in sel_listing and not is_lst: ok = True
        if not ok:
            return False
    else:
        if not listing_is_all:
            is_for = bool(j.get("is_foreign"))
            is_lst = bool(j.get("is_listed"))
            if not is_for:
                ok = False
                if "上市櫃" in sel_listing and is_lst:    ok = True
                if "非上市櫃" in sel_listing and not is_lst: ok = True
                if not ok:
                    return False
    if filter_remote and not j.get("remote_work"):
        return False
    return True


filtered    = [j for j in all_jobs if job_passes(j)]
total_found = len(filtered)
filtered    = filtered[:limit]

st.markdown(
    f"<p style='color:#888;font-size:0.85rem;'>符合條件：<b>{total_found}</b> 筆，顯示前 {len(filtered)} 筆</p>",
    unsafe_allow_html=True,
)

if not filtered:
    st.info("目前沒有符合條件的職缺，請調整篩選條件（例如換一個 Career Path，或放寬其他條件）。")
    st.stop()


for job in filtered:
    render_job_card(job)


st.markdown("---")
if st.button("📥 匯出為 CSV"):
    df  = pd.DataFrame(filtered)
    csv = df.to_csv(index=False, encoding="utf-8-sig")
    st.download_button("下載 CSV", data=csv, file_name="jobs_export.csv", mime="text/csv")
