#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Page 2 — Career Map

Analytics > Domain > Sub-role 的階層地圖（sunburst），點一個 sub-role
展開角色詳情：這個角色實際在做什麼、常見職稱、市場需求、薪資中位數、
熱門技能、常見公司、履歷適配度，最後才是實際職缺列表。
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import streamlit as st
import plotly.graph_objects as go

from utils.supabase_client import get_analytics_rows
from utils import career_taxonomy as ct

st.set_page_config(page_title="Career Map | Career Overfitter", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@300;400;500&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; background:#f9f8f6; }
h1,h2,h3 { font-family: 'Syne', sans-serif; font-weight: 800; color:#111; }
.role-header { display:flex; align-items:center; gap:10px; margin-bottom:2px; }
.role-name { font-family:'Syne',sans-serif; font-weight:800; font-size:1.6rem; color:#111; }
.depth-badge {
    display:inline-block; padding:3px 11px; border-radius:999px;
    font-size:0.76rem; font-weight:700; background:#e8edf5; color:#1e3a5f;
}
.domain-badge {
    display:inline-block; padding:3px 11px; border-radius:999px;
    font-size:0.76rem; font-weight:600; background:#f0ebe2; color:#5c3d11; margin-left:6px;
}
.do-list { font-size:0.95rem; line-height:2.0; color:#222; }
.stat-box {
    border:1px solid #e0ddd7; border-radius:12px; background:#fff;
    padding:0.9rem 1rem; text-align:center;
}
.stat-num { font-size:1.5rem; font-weight:800; color:#1e3a5f; font-family:'Syne',sans-serif; }
.stat-label { font-size:0.75rem; color:#8b8175; margin-top:2px; }
.tag-skill { display:inline-block; background:#e8edf5; color:#1e3a5f; border-radius:4px;
    padding:2px 9px; font-size:0.78rem; margin:2px 4px 2px 0; }
.tag-company { display:inline-block; background:#f3f0ea; color:#4a3b28; border-radius:4px;
    padding:2px 9px; font-size:0.78rem; margin:2px 4px 2px 0; }
</style>
""", unsafe_allow_html=True)

st.markdown("<h1 style='margin-bottom:4px'>🧭 Career Map</h1>", unsafe_allow_html=True)
st.markdown(
    "<p style='color:#5f5a54;margin-top:0'>先看地圖，再看角色，最後才看職缺 — 點一個節點展開。</p>",
    unsafe_allow_html=True,
)
st.markdown("---")

rows = get_analytics_rows()

# ── 建 sunburst 資料：root -> domain -> role ──────────────
ids, labels, parents, values = [], [], [], []
ids.append("Analytics"); labels.append("Analytics"); parents.append(""); values.append(0)

role_summaries_all = ct.build_role_summary(rows)
summary_by_role = {s["role_normalized"]: s for s in role_summaries_all}

for domain in ct.DOMAIN_ORDER:
    domain_id = f"domain::{domain}"
    domain_total = sum(s["count"] for s in role_summaries_all if s["domain"] == domain)
    ids.append(domain_id); labels.append(domain.replace(" Analytics", "")); parents.append("Analytics")
    values.append(max(domain_total, 1))

    for role in ct.list_roles_in_domain(domain):
        s = summary_by_role.get(role)
        count = s["count"] if s else 0
        ids.append(f"role::{domain}::{role}")
        labels.append(role)
        parents.append(domain_id)
        values.append(max(count, 0.3))  # 給沒資料的角色留一點視覺空間

fig = go.Figure(go.Sunburst(
    ids=ids, labels=labels, parents=parents, values=values,
    branchvalues="total",
    marker=dict(colors=["#f4f2ee"] + ["#c9d8ea"] * len(ct.DOMAIN_ORDER) + ["#2563a8"] * (len(ids) - 1 - len(ct.DOMAIN_ORDER)),
                line=dict(color="white", width=1.5)),
    hovertemplate="<b>%{label}</b><br>%{value:.0f} 筆職缺<extra></extra>",
    maxdepth=3,
))
fig.update_layout(
    margin=dict(l=0, r=0, t=10, b=10), height=520,
    paper_bgcolor="white", font=dict(family="DM Sans", color="#111", size=13),
)

clicked_role = None
clicked_domain = st.session_state.get("career_map_domain")

try:
    event = st.plotly_chart(fig, use_container_width=True, on_select="rerun", key="career_sunburst")
    pts = None
    if event is not None:
        sel = event.get("selection") if isinstance(event, dict) else getattr(event, "selection", None)
        if sel:
            pts = sel.get("points") if isinstance(sel, dict) else getattr(sel, "points", None)
    if pts:
        last = pts[-1]
        pid = last.get("id") if isinstance(last, dict) else getattr(last, "id", None)
        if pid and pid.startswith("role::"):
            _, clicked_domain, clicked_role = pid.split("::", 2)
        elif pid and pid.startswith("domain::"):
            clicked_domain = pid.split("::", 1)[1]
except Exception:
    st.plotly_chart(fig, use_container_width=True)

st.markdown("---")

# ── 選擇器（保證可操作，不依賴點擊事件） ───────────────────
col_a, col_b = st.columns(2)
with col_a:
    domain_options = ct.DOMAIN_ORDER
    default_domain_idx = domain_options.index(clicked_domain) if clicked_domain in domain_options else 0
    picked_domain = st.selectbox("領域", domain_options, index=default_domain_idx, key="cm_domain_pick")
with col_b:
    role_options = ct.list_roles_in_domain(picked_domain)
    default_role_idx = role_options.index(clicked_role) if clicked_role in role_options else 0
    picked_role = st.selectbox("子分類職稱", role_options, index=default_role_idx if role_options else 0, key="cm_role_pick")

st.markdown("---")

if not picked_role:
    st.info("這個領域目前還沒有子分類職稱資料。")
    st.stop()

summary = summary_by_role.get(picked_role, {
    "role_normalized": picked_role, "domain": picked_domain,
    "tech_depth": ct.get_tech_depth(picked_role), "count": 0,
    "median_salary": None, "top_skills": [], "top_companies": [], "jobs": [],
})

depth = summary["tech_depth"] or "DA"

st.markdown(
    f"""
    <div class="role-header">
        <span class="role-name">{picked_role}</span>
        <span class="domain-badge">{picked_domain}</span>
        <span class="depth-badge">{depth} · {ct.TECH_DEPTH_LABEL.get(depth, depth)}</span>
    </div>
    """,
    unsafe_allow_html=True,
)

# ── What do people actually do? ───────────────────────────
st.markdown("#### 這個角色實際在做什麼？")
do_items = ct.DOMAIN_WHAT_THEY_DO.get(picked_domain, [])
st.markdown(
    "<div class='do-list'>" + "".join(f"✔ {item}<br>" for item in do_items) + "</div>",
    unsafe_allow_html=True,
)

# ── Common Titles（同領域其他子分類職稱，作為「常見職稱」參考） ─
st.markdown("#### Common Titles（同領域常見職稱）")
peers = [r for r in ct.list_roles_in_domain(picked_domain) if r != picked_role]
st.markdown(
    " ".join(f"<span class='tag-skill'>{p}</span>" for p in [picked_role] + peers[:7]),
    unsafe_allow_html=True,
)

st.markdown("---")

# ── Market Demand / Median Salary / Top Skills / Companies ──
st.markdown("#### 市場數據")
m1, m2 = st.columns(2)
with m1:
    st.markdown(
        f"<div class='stat-box'><div class='stat-num'>{summary['count']:,}</div>"
        f"<div class='stat-label'>Market Demand（職缺數）</div></div>",
        unsafe_allow_html=True,
    )
with m2:
    sal = f"NT$ {summary['median_salary']:,.0f}" if summary["median_salary"] else "資料不足"
    st.markdown(
        f"<div class='stat-box'><div class='stat-num'>{sal}</div>"
        f"<div class='stat-label'>Median Salary（月薪中位數）</div></div>",
        unsafe_allow_html=True,
    )

st.markdown("<br>", unsafe_allow_html=True)
sk1, sk2 = st.columns(2)
with sk1:
    st.markdown("**Top Skills**")
    if summary["top_skills"]:
        st.markdown(" ".join(f"<span class='tag-skill'>{s}</span>" for s in summary["top_skills"]), unsafe_allow_html=True)
    else:
        st.caption("資料不足")
with sk2:
    st.markdown("**Companies**")
    if summary["top_companies"]:
        st.markdown(" ".join(f"<span class='tag-company'>{c}</span>" for c in summary["top_companies"]), unsafe_allow_html=True)
    else:
        st.caption("資料不足")

st.markdown("---")

# ── Resume Fit ────────────────────────────────────────────
st.markdown("#### Resume Fit")
cv_fit_scores = st.session_state.get("cv_fit_scores")
if cv_fit_scores and picked_role in cv_fit_scores:
    st.success(f"你的履歷跟 {picked_role} 的適配分數：{cv_fit_scores[picked_role]:.0f} / 100")
else:
    st.info("還沒有履歷適配分數。")
    if st.button("上傳履歷看 Resume Fit →"):
        st.switch_page("pages/3_Resume.py")

st.markdown("---")

# ── Jobs（放最後） ────────────────────────────────────────
st.markdown(f"#### Jobs（{summary['count']} 筆真實職缺）")
if not summary["jobs"]:
    st.caption("目前這個職稱還沒有職缺資料。")
else:
    for job in summary["jobs"][:15]:
        title = job.get("title_clean") or "（無職稱）"
        company = job.get("company_clean") or ""
        job_no = job.get("job_no") or ""
        url = f"https://www.104.com.tw/job/{job_no}" if job_no else ""
        sal_low, sal_hi = job.get("salary_low"), job.get("salary_high")
        sal_txt = f"NT$ {sal_low:,.0f} - {sal_hi:,.0f}" if sal_low and sal_hi else ""
        line = f"**{title}** — {company}　{sal_txt}"
        if url:
            st.markdown(f"{line}　[查看原始職缺 ↗]({url})")
        else:
            st.markdown(line)
    if st.button("查看全部職缺 →"):
        st.session_state["jobs_filter_role"] = picked_role
        st.switch_page("pages/5_Jobs.py")
