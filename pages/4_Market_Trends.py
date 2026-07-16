#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Page 4 — Market Trends: Compare Career Paths

以前這頁是「Top SQL / Top Python / Top Tableau」的技能排行榜。
但使用者真正想知道的問題是「我要往哪一條路？」— 排行榜沒辦法回答這個問題，
技能 x 職涯路徑的星等比較矩陣可以。
"""

import sys
from collections import Counter
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import streamlit as st
import plotly.graph_objects as go

from utils.supabase_client import get_analytics_rows
from utils import career_taxonomy as ct

st.set_page_config(page_title="Market Trends | Career Overfitter", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@300;400;500&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; background:#f9f8f6; }
h1,h2,h3 { font-family: 'Syne', sans-serif; font-weight: 800; color:#111; }
.star-table { width:100%; border-collapse: collapse; font-size:0.92rem; }
.star-table th { text-align:left; padding:10px 12px; border-bottom:2px solid #111;
    font-family:'Syne',sans-serif; font-size:0.82rem; text-transform:uppercase; letter-spacing:0.04em; }
.star-table td { padding:9px 12px; border-bottom:1px solid #eeece7; }
.star-cell { color:#2563a8; letter-spacing:1px; }
.star-cell.empty { color:#d8d4cc; }
.skill-name { font-weight:600; color:#111; }
</style>
""", unsafe_allow_html=True)

st.markdown("<h1 style='margin-bottom:4px'>📈 Market Trends</h1>", unsafe_allow_html=True)
st.markdown(
    "<p style='color:#5f5a54;margin-top:0'>Compare Career Paths — 不是排行榜，是路線圖。</p>",
    unsafe_allow_html=True,
)
st.markdown("---")

rows = get_analytics_rows()

st.markdown("### 技能 x 職涯路徑")
st.caption("★ 越多代表這個技能在這條路徑的職缺裡出現的比例越高，不是技能難度。")

matrix_data = ct.build_skill_matrix(rows, top_n_skills=14)

if not matrix_data["skills"]:
    st.info("目前資料還不足以計算技能比較矩陣。")
else:
    domain_short = {d: d.replace(" Analytics", "") for d in matrix_data["domains"]}
    header_cells = "".join(f"<th>{domain_short[d]}</th>" for d in matrix_data["domains"])
    body_rows = ""
    for row in matrix_data["matrix"]:
        cells = ""
        for d in matrix_data["domains"]:
            n = row[d]
            stars_html = "★" * n + "☆" * (5 - n)
            cls = "star-cell" if n > 0 else "star-cell empty"
            cells += f"<td class='{cls}'>{stars_html}</td>"
        body_rows += f"<tr><td class='skill-name'>{row['skill']}</td>{cells}</tr>"

    st.markdown(
        f"""
        <table class="star-table">
        <thead><tr><th>Skill</th>{header_cells}</tr></thead>
        <tbody>{body_rows}</tbody>
        </table>
        """,
        unsafe_allow_html=True,
    )

st.markdown("---")

# ── Median salary by role (由 domain 分組) ──────────────
st.markdown("### 各職稱薪資中位數")
role_summaries = ct.build_role_summary(rows)
role_summaries_with_salary = [r for r in role_summaries if r["median_salary"]]
role_summaries_with_salary.sort(key=lambda r: r["median_salary"], reverse=True)

if role_summaries_with_salary:
    domain_colors = {
        "Business Analytics": "#2563a8",
        "Product Analytics": "#5b9bd5",
        "Marketing Analytics": "#6b5b4e",
        "Operations Analytics": "#3d6b5e",
    }
    top_roles = role_summaries_with_salary[:20]
    fig = go.Figure(go.Bar(
        x=[r["median_salary"] for r in top_roles],
        y=[r["role_normalized"] for r in top_roles],
        orientation="h",
        marker_color=[domain_colors.get(r["domain"], "#999") for r in top_roles],
        text=[f"NT$ {r['median_salary']:,.0f}" for r in top_roles],
        textposition="outside",
    ))
    fig.update_layout(
        paper_bgcolor="white", plot_bgcolor="white",
        font=dict(family="DM Sans", color="#111"),
        margin=dict(l=10, r=80, t=10, b=10),
        height=560,
        yaxis=dict(autorange="reversed"),
        xaxis=dict(title="月薪中位數 (NT$)", showgrid=True, gridcolor="#eeece7"),
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("目前薪資資料不足以繪製圖表。")

st.markdown("---")

# ── Industry distribution ────────────────────────────────
st.markdown("### 產業分布與遠端工作比例")
ind_counter = Counter(r.get("industry_bucket") for r in rows if r.get("industry_bucket"))
remote_counter = Counter(bool(r.get("remote_work")) for r in rows if r.get("role_normalized"))

c1, c2 = st.columns(2)
with c1:
    if ind_counter:
        fig = go.Figure(go.Pie(
            labels=list(ind_counter.keys()), values=list(ind_counter.values()), hole=0.45,
        ))
        fig.update_layout(
            paper_bgcolor="white", font=dict(family="DM Sans", color="#111"),
            margin=dict(l=10, r=10, t=10, b=10), height=360,
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.caption("資料不足")
with c2:
    total = sum(remote_counter.values())
    remote_pct = (remote_counter.get(True, 0) / total * 100) if total else 0
    st.markdown(
        f"<div class='stat-box' style='border:1px solid #e0ddd7;border-radius:12px;padding:1.5rem;text-align:center;'>"
        f"<div style='font-size:2.2rem;font-weight:800;color:#1e3a5f;font-family:Syne,sans-serif;'>{remote_pct:.0f}%</div>"
        f"<div style='font-size:0.85rem;color:#8b8175;margin-top:4px;'>職缺支援遠端工作</div>"
        f"</div>",
        unsafe_allow_html=True,
    )
