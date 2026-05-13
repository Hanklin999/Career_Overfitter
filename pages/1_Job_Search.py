#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Page 1 — Job Search"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import re
import streamlit as st
import pandas as pd
from utils.supabase_client import _get, get_jd_raw_count, get_job_posting_count

st.set_page_config(page_title="Job Search | Career Overfitter", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@300;400;500&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; background:#f9f8f6; }
h1,h2,h3 { font-family: 'Syne', sans-serif; font-weight: 800; color:#111; }

/* ── Tag 系統：3 種語意色 ── */
.tag {
    display: inline-block;
    border-radius: 4px;
    padding: 2px 9px;
    font-size: 0.74rem;
    font-weight: 500;
    margin: 2px 3px 2px 0;
    letter-spacing: 0.02em;
}
.tag-skill { background:#e8edf5; color:#1e3a5f; }
.tag-role  { background:#f0ebe2; color:#5c3d11; }
.tag-flag  { background:#ebebeb; color:#333; }
.tag-ind   { background:#f0ebe2; color:#5c3d11; }

/* ── 職類 chip（圓角 pill 樣式，有別於方形 tag） ── */
.tag-cat {
    display: inline-block;
    border-radius: 12px;
    padding: 2px 10px;
    font-size: 0.73rem;
    font-weight: 500;
    margin: 2px 3px 2px 0;
    background: #f3f0ea;
    color: #4a3b28;
    border: 1px solid #e0d9cf;
}

.salary { font-weight:700; color:#111; font-size:0.92rem; }
.job-meta { font-size:0.81rem; color:#666; margin:4px 0 8px 0; }
.detail-label {
    font-size:0.76rem; font-weight:700; color:#777;
    margin-top:10px; margin-bottom:3px;
    text-transform:uppercase; letter-spacing:0.06em;
}
.detail-body  { font-size:0.83rem; color:#222; line-height:1.7; }
.quality-badge { font-size:0.72rem; font-weight:600; padding:1px 7px; border-radius:3px; }

/* ── 104 外部連結按鈕 ── */
.link-104 {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 0.78rem;
    font-weight: 600;
    color: #e54d2e;
    text-decoration: none;
    padding: 3px 10px;
    border: 1px solid #f5c2b8;
    border-radius: 4px;
    background: #fff8f7;
    transition: background 0.15s;
}
.link-104:hover { background:#fdeae6; text-decoration:none; }

/* ── 篩選區塊分組標題 ── */
.filter-section-label {
    font-size: 0.72rem;
    font-weight: 700;
    color: #888;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin: 14px 0 6px 0;
    padding: 6px 0 4px 0;
    border-top: 1px solid #e5e2db;
}
.filter-section-label.first { border-top: none; margin-top: 0; }
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


# ── 載入全部職缺 ──────────────────────────────────────────
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

ind_to_parents:    dict = {}
par_to_industries: dict = {}
hierarchy:         dict = {}

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


# ── 職類 raw string → list helper ────────────────────────
def parse_cat_raw(raw) -> list:
    """
    接受以下各種輸入，均回傳 Python list[str]：
      - Python list（直接回傳）
      - "['A', 'B', 'C']" 字串（Postgres array 轉字串）
      - "A,B,C" 純逗號字串
      - None / 空值
    """
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    s = str(raw).strip().strip("[]")
    items = re.findall(r"['\"]([^'\"]+)['\"]", s)
    if items:
        return items
    # fallback：逗號分隔
    return [x.strip() for x in s.split(",") if x.strip()]


# ── Filters ──────────────────────────────────────────────
with st.expander("🔧 篩選條件", expanded=True):

    # 關鍵字
    keyword = st.text_input("職稱關鍵字", placeholder="e.g. 資料工程師")

    # ── 公司性質 ─────────────────────────────────────────
    st.markdown("<div class='filter-section-label first'>🏢 公司性質</div>",
                unsafe_allow_html=True)

    nature_options = ["外商", "本土"]
    sel_nature = st.multiselect(
        "公司類型（未選＝全部）",
        options=nature_options,
        default=nature_options,
        key="nature",
        help="可複選；清空選項代表不限制"
    )

    # 只有「本土」被選中才顯示上市子篩選
    sel_listing: list = []
    if "本土" in sel_nature:
        listing_options = ["上市櫃", "非上市櫃"]
        sel_listing = st.multiselect(
            "↳ 本土上市條件（未選＝全部）",
            options=listing_options,
            default=listing_options,
            key="listing",
        )

    filter_remote = st.checkbox("Remote 優先")

    # ── 選擇產業 ─────────────────────────────────────────
    st.markdown("<div class='filter-section-label'>🏭 選擇產業</div>",
                unsafe_allow_html=True)
    r_ind = st.columns(2)
    with r_ind[0]:
        sel_industry = st.selectbox("產業大類", ["全部"] + industries, key="ind")
    with r_ind[1]:
        # 預留「產業別」欄位（待資料建置後可直接啟用）
        st.selectbox(
            "產業別",
            ["全部"],
            key="ind_sub",
            disabled=True,
            help="細分產業別（資料建置中，即將上線）"
        )

    # ── 選擇職能 ─────────────────────────────────────────
    st.markdown("<div class='filter-section-label'>🎯 選擇職能</div>",
                unsafe_allow_html=True)

    valid_parents = (
        sorted(ind_to_parents.get(sel_industry, set()))
        if sel_industry != "全部" else parents
    )
    r_job1 = st.columns(2)
    with r_job1[0]:
        sel_parent = st.selectbox("職能大類", ["全部"] + valid_parents, key="par")
    sub_options = sorted(hierarchy.get(sel_parent, {}).keys()) if sel_parent != "全部" else []
    with r_job1[1]:
        sel_sub = st.selectbox("職能中類", ["全部"] + sub_options, key="sub")

    r_job2 = st.columns(2)
    if sel_parent != "全部":
        subs = hierarchy.get(sel_parent, {})
        role_options = (
            sorted(subs.get(sel_sub, set())) if sel_sub != "全部"
            else sorted({r for roles in subs.values() for r in roles})
        )
    else:
        role_options = []
    with r_job2[0]:
        sel_roles = st.multiselect("職能別（可多選）", role_options)

    # ── 其他條件 ─────────────────────────────────────────
    st.markdown("<div class='filter-section-label'>⚙️ 其他條件</div>",
                unsafe_allow_html=True)
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

# 判斷「公司性質」是否等同全選（不需過濾）
nature_is_all  = not sel_nature or set(sel_nature) == {"外商", "本土"}
listing_is_all = not sel_listing or set(sel_listing) == {"上市櫃", "非上市櫃"}


def job_passes(j) -> bool:
    # 職稱關鍵字
    if keyword and keyword.lower() not in (j.get("title_clean") or "").lower():
        return False

    # 產業 / 職能 / 職能別
    if sel_industry != "全部" and j.get("industry_bucket") != sel_industry:
        return False
    if sel_parent != "全部" and j.get("job_parent_category") != sel_parent:
        return False
    if sel_sub != "全部" and j.get("job_sub_category") != sel_sub:
        return False
    if sel_roles and j.get("role_normalized") not in sel_roles:
        return False

    # 薪資 / 學歷
    if salary_min and (not j.get("salary_low") or j.get("salary_low") < salary_min * 1000):
        return False
    if min_edu_int >= 0:
        edu_int = j.get("edu_level_int")
        if edu_int is None or edu_int < min_edu_int:
            return False

    # ── 公司性質篩選 ─────────────────────────────────────
    if not nature_is_all:
        is_for = bool(j.get("is_foreign"))
        is_lst = bool(j.get("is_listed"))
        ok = False
        # 外商
        if "外商" in sel_nature and is_for:
            ok = True
        # 本土：再判斷上市條件
        if "本土" in sel_nature and not is_for:
            if listing_is_all:
                ok = True
            else:
                if "上市櫃" in sel_listing and is_lst:
                    ok = True
                if "非上市櫃" in sel_listing and not is_lst:
                    ok = True
        if not ok:
            return False
    else:
        # 全選 nature，但若本土的上市條件有篩選（非全選）仍需過濾
        if not listing_is_all:
            is_for = bool(j.get("is_foreign"))
            is_lst = bool(j.get("is_listed"))
            if not is_for:  # 只對本土公司套用上市條件
                ok = False
                if "上市櫃" in sel_listing and is_lst:
                    ok = True
                if "非上市櫃" in sel_listing and not is_lst:
                    ok = True
                if not ok:
                    return False

    # Remote
    if filter_remote and not j.get("remote_work"):
        return False

    return True


filtered    = [j for j in all_jobs if job_passes(j)]
total_found = len(filtered)
filtered    = filtered[:limit]

st.markdown(
    f"<p style='color:#888;font-size:0.85rem;'>"
    f"符合條件：<b>{total_found}</b> 筆，顯示前 {len(filtered)} 筆</p>",
    unsafe_allow_html=True,
)

if not filtered:
    st.info("目前沒有符合條件的職缺，請調整篩選條件。")
    st.stop()


# ── Job Cards ─────────────────────────────────────────────
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
    job_no  = job.get("job_no") or ""

    # 薪資 / 年資 / meta
    salary_str = (
        f"{sal_low//1000}K–{sal_hi//1000}K／{sal_u}" if sal_low and sal_hi else
        f"{sal_low//1000}K+／{sal_u}"                 if sal_low            else "薪資面議"
    )
    exp_str = (
        f"{exp_min}–{exp_max} 年" if exp_min is not None and exp_max is not None else
        f"{exp_min}+ 年"          if exp_min is not None                          else ""
    )
    meta_parts = [p for p in [company, loc, exp_str, edu] if p]
    meta_str   = " · ".join(meta_parts)

    # 品質徽章
    q_pct = int(quality * 100)
    q_bg  = "#d1fae5" if quality >= 0.7 else "#fef3c7" if quality >= 0.4 else "#f3f4f6"
    q_fg  = "#065f46" if quality >= 0.7 else "#78350f" if quality >= 0.4 else "#6b7280"

    # 旗標 tags
    flags = []
    if is_for:                       flags.append("外商")
    elif not is_for and not is_lst:  flags.append("本土")
    if is_lst:                       flags.append("上市櫃")
    if remote:                       flags.append("Remote")

    role_tag  = (f'<span class="tag tag-role">{role_n}</span>'
                 if role_n and role_n != "Unclassified" else "")
    ind_tag   = f'<span class="tag tag-ind">{ind_b}</span>' if ind_b else ""
    flag_tags = " ".join(f'<span class="tag tag-flag">{f}</span>' for f in flags)
    skill_tags = "".join(
        f'<span class="tag tag-skill">{s}</span>'
        for s in (skills[:5] if isinstance(skills, list) else [])
    )
    q_badge = (
        f'<span class="quality-badge" style="background:{q_bg};color:{q_fg};">'
        f'品質 {q_pct}%</span>'
    )

    # ── 104 原始職缺連結 ──────────────────────────────────
    link_104_html = ""
    if job_no:
        url_104 = f"https://www.104.com.tw/job/{job_no}"
        link_104_html = (
            f'<a href="{url_104}" target="_blank" rel="noopener noreferrer" class="link-104">'
            f'<svg width="12" height="12" viewBox="0 0 24 24" fill="none" '
            f'stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">'
            f'<path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/>'
            f'<polyline points="15 3 21 3 21 9"/>'
            f'<line x1="10" y1="14" x2="21" y2="3"/>'
            f'</svg>'
            f'104 查看原始職缺</a>'
        )

    # ── 職類 chips（parse list-like string → pill chips） ──
    cat_items = parse_cat_raw(cat_raw)
    cat_chips_html = ""
    if cat_items:
        chips = "".join(f'<span class="tag-cat">{c}</span>' for c in cat_items)
        cat_chips_html = (
            f"<div class='detail-label'>職類</div>"
            f"<div style='margin-top:4px;'>{chips}</div>"
        )

    header = f"**{title}** · {company}　｜　{salary_str}　｜　{date}"

    with st.expander(header, expanded=False):
        st.markdown(f"""
        <div style='padding:4px 0 10px 0;'>
          <div class='job-meta'>{meta_str}</div>
          <div style='margin-bottom:6px;display:flex;align-items:center;flex-wrap:wrap;gap:4px;'>
            {role_tag}{ind_tag}{flag_tags}&nbsp;&nbsp;{q_badge}
            <span style='flex:1'></span>
            {link_104_html}
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
            st.markdown(
                f"<div class='detail-label'>管理職責</div>"
                f"<div class='detail-body'>{manage}</div>",
                unsafe_allow_html=True,
            )

        if isinstance(skills, list) and len(skills) > 5:
            all_skill_tags = "".join(
                f'<span class="tag tag-skill">{s}</span>' for s in skills
            )
            st.markdown(
                f"<div class='detail-label'>全部技能（{len(skills)} 項）</div>"
                f"<div style='margin-top:4px;'>{all_skill_tags}</div>",
                unsafe_allow_html=True,
            )


st.markdown("---")
if st.button("📥 匯出為 CSV"):
    df  = pd.DataFrame(filtered)
    csv = df.to_csv(index=False, encoding="utf-8-sig")
    st.download_button("下載 CSV", data=csv, file_name="jobs_export.csv", mime="text/csv")
