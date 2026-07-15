#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Page 1 — Job Search"""

import sys, re
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
from utils.supabase_client import _get, get_jd_raw_count, get_job_posting_count
from utils import rag_retrieval
from utils.ui_taxonomy import (
    get_industry_parents, get_industry_subs,
    get_role_parents, get_role_subs, get_roles,
    filter_rows, format_industry_label, format_role_label,
    filter_label, FILTER_STYLE,
)

st.set_page_config(page_title="Job Search | Career Overfitter", layout="wide")

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
.tag-cat {{
    display: inline-block; border-radius: 12px; padding: 2px 10px;
    font-size: 0.73rem; font-weight: 500; margin: 2px 3px 2px 0;
    background: #f3f0ea; color: #4a3b28; border: 1px solid #e0d9cf;
}}
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
    transition: background 0.15s;
}}
.link-104:hover {{ background:#fdeae6; text-decoration:none; }}
{FILTER_STYLE}
</style>
""", unsafe_allow_html=True)

st.markdown("<h1 style='margin-bottom:0'>🔍 Job Search</h1>", unsafe_allow_html=True)

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


# ── Job Card renderer（結構化篩選結果 / 語意搜尋結果共用） ─────
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
            {role_tag}{ind_tag}{flag_tags}{extra_badge_html}&nbsp;&nbsp;{q_badge}
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


# ── 語意搜尋（AI，用向量相似度） ─────────────────────────
st.markdown("### 🧠 語意搜尋（AI）")
st.caption(
    "用一句話描述你想找的工作，AI 會用向量相似度從真實職缺資料庫裡找出最相關的結果，"
    "跟下面的結構化篩選是獨立的兩種找法，互不影響。"
)

if not rag_retrieval.is_available():
    st.info("尚未設定 RAG 檢索（需要先跑過 sql/001_enable_pgvector_rag.sql 並執行過 backfill_embeddings.py），語意搜尋暫時無法使用。")
else:
    semantic_query = st.text_input(
        "描述你想找的工作",
        placeholder="例如：想找能用 Python 做行銷成效分析、不用寫太多 code 的工作",
        key="semantic_query_input",
    )
    semantic_count = st.slider("語意搜尋顯示筆數", 5, 30, 10, 5, key="semantic_count")

    if st.button("🔍 開始語意搜尋", type="primary") and semantic_query.strip():
        with st.spinner("檢索中..."):
            semantic_results = rag_retrieval.retrieve_similar_jobs(semantic_query, match_count=semantic_count)
        st.session_state["semantic_search_results"] = semantic_results
        st.session_state["semantic_search_query"] = semantic_query

    semantic_results = st.session_state.get("semantic_search_results", [])
    if semantic_results:
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
                # 資料在目前載入的 all_jobs（最新 3000 筆）裡，直接重用完整卡片渲染。
                render_job_card(full_job, extra_badge_html=sim_badge)
            else:
                # RPC 是查整張 job_posting 表，可能撈到超過 all_jobs 3000 筆上限之外的
                # 舊資料；這種情況用 RPC 本身回傳的精簡欄位做一個簡化卡片，
                # 至少能看標題、角色分類、職缺描述片段跟 104 連結。
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



# ── Filters ───────────────────────────────────────────────
with st.expander("🔧 篩選條件", expanded=True):

    keyword = st.text_input("職稱關鍵字", placeholder="e.g. 資料工程師")

    st.markdown(filter_label("🏢 公司性質", first=True), unsafe_allow_html=True)
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

    st.markdown(filter_label("🎯 選擇職能"), unsafe_allow_html=True)
    role_parent_opts = ["全部"] + get_role_parents(all_jobs,
                                                    industry_parent=sel_industry,
                                                    industry_sub=sel_industry_sub)
    r_job1 = st.columns(2)
    with r_job1[0]:
        sel_parent = st.selectbox("職能大類", role_parent_opts, key="par")
    with r_job1[1]:
        role_sub_opts = ["全部"] + (get_role_subs(all_jobs, sel_parent,
                                                   industry_parent=sel_industry,
                                                   industry_sub=sel_industry_sub)
                                    if sel_parent != "全部" else [])
        sel_sub = st.selectbox("職能中類", role_sub_opts, key="sub",
                               disabled=(sel_parent == "全部"))

    role_opts = get_roles(all_jobs, role_parent=sel_parent, role_sub=sel_sub,
                          industry_parent=sel_industry, industry_sub=sel_industry_sub)
    sel_roles = st.multiselect("職能別（可多選）", role_opts)

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
    if keyword and keyword.lower() not in (j.get("title_clean") or "").lower():
        return False
    if sel_industry != "全部"     and j.get("industry_bucket") != sel_industry:      return False
    if sel_industry_sub != "全部" and j.get("industry_raw") != sel_industry_sub:      return False
    if sel_parent != "全部"       and j.get("job_parent_category") != sel_parent:     return False
    if sel_sub != "全部"          and j.get("job_sub_category") != sel_sub:           return False
    if sel_roles and j.get("role_normalized") not in sel_roles:                        return False
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
    st.info("目前沒有符合條件的職缺，請調整篩選條件。")
    st.stop()


# ── Job Cards（結構化篩選結果） ─────────────────────────────
for job in filtered:
    render_job_card(job)


st.markdown("---")
if st.button("📥 匯出為 CSV"):
    df  = pd.DataFrame(filtered)
    csv = df.to_csv(index=False, encoding="utf-8-sig")
    st.download_button("下載 CSV", data=csv, file_name="jobs_export.csv", mime="text/csv")
