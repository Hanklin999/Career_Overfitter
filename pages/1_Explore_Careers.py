#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Page 1 — Explore Analytics Careers

「Google Maps for Analytics Careers」的入口頁。很多人想走數據分析，
但不知道「數據分析」這件事藏在很多不同職稱、不同部門底下 — 這一頁先給
一張市場地圖：X 軸是「業務應用領域」，Y 軸是「工程深度」，泡泡大小是
目前資料庫裡這個象限有多少職缺。點一個象限，往下看細分職稱。
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import streamlit as st
import plotly.graph_objects as go

from utils.supabase_client import get_analytics_rows
from utils import career_taxonomy as ct

st.set_page_config(page_title="Explore Analytics Careers | Career Overfitter", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@300;400;500&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; background:#f9f8f6; }
h1,h2,h3 { font-family: 'Syne', sans-serif; font-weight: 800; color:#111; }
.hero-sub { font-size:1rem; color:#5f5a54; line-height:1.7; margin-bottom:0.4rem; }
.domain-card {
    border: 1px solid #e0ddd7; border-radius: 14px; background: #ffffff;
    padding: 1.1rem 1.15rem; box-shadow: 0 1px 2px rgba(0,0,0,0.03);
    margin-bottom: 0.75rem; transition: all 0.15s ease;
}
.domain-card:hover { border-color:#cfc8be; box-shadow: 0 6px 18px rgba(0,0,0,0.06); }
.domain-title { font-family:'Syne',sans-serif; font-weight:800; font-size:1.05rem; color:#111; }
.domain-tagline { font-size:0.85rem; color:#8b8175; margin:2px 0 8px 0; }
.domain-count { font-size:1.6rem; font-weight:800; color:#1e3a5f; }
.domain-count-label { font-size:0.76rem; color:#8b8175; }
</style>
""", unsafe_allow_html=True)

st.markdown("<h1 style='margin-bottom:4px'>🗺️ Explore Analytics Careers</h1>", unsafe_allow_html=True)
st.markdown(
    """
    <div class="hero-sub">
    很多人想走數據分析，但「數據分析」這件事其實藏在很多不同的職稱與部門裡 —
    有人叫 Business Analyst，有人叫 Product Analyst，有人在做一模一樣的事卻叫 Data Scientist。
    這張地圖用兩個軸幫你先看懂市場：<b>橫軸是業務應用領域</b>（你分析的是什麼問題），
    <b>縱軸是工程深度</b>（你的工作離工程／建模有多近）。泡泡越大，代表資料庫裡這個象限
    目前的職缺越多。
    </div>
    """,
    unsafe_allow_html=True,
)
st.markdown("---")

rows = get_analytics_rows()
landscape = ct.build_landscape(rows)

domain_order = ct.DOMAIN_ORDER
depth_order = ct.TECH_DEPTH_ORDER

# ── XY 市場分布圖 ─────────────────────────────────────────
counts = [d["count"] for d in landscape]
max_count = max(counts) if counts else 1

fig = go.Figure()
for point in landscape:
    x = domain_order.index(point["domain"])
    y = depth_order.index(point["tech_depth"])
    size = 18 + (point["count"] / max_count) * 62 if max_count else 18
    fig.add_trace(go.Scatter(
        x=[x], y=[y],
        mode="markers+text",
        marker=dict(
            size=size,
            color="#2563a8" if point["count"] > 0 else "#e5e2db",
            line=dict(width=1, color="#1e3a5f"),
            opacity=0.85 if point["count"] > 0 else 0.4,
        ),
        text=[str(point["count"])],
        textposition="middle center",
        textfont=dict(color="white" if point["count"] > 0 else "#999", size=13, family="DM Sans"),
        hovertemplate=(
            f"<b>{point['domain']}</b><br>"
            f"{ct.TECH_DEPTH_LABEL[point['tech_depth']]} ({point['tech_depth']})<br>"
            f"{point['count']} 筆職缺<extra></extra>"
        ),
        showlegend=False,
        name="",
    ))

fig.update_layout(
    paper_bgcolor="white", plot_bgcolor="#fbfaf8",
    font=dict(family="DM Sans", color="#111"),
    margin=dict(l=10, r=10, t=10, b=10),
    height=440,
    xaxis=dict(
        tickmode="array", tickvals=list(range(len(domain_order))),
        ticktext=[d.replace(" Analytics", "") for d in domain_order],
        title="業務應用領域 →", range=[-0.6, len(domain_order) - 0.4],
        showgrid=True, gridcolor="#eeece7", zeroline=False,
    ),
    yaxis=dict(
        tickmode="array", tickvals=list(range(len(depth_order))),
        ticktext=[f"{d} ({ct.TECH_DEPTH_LABEL[d]})" for d in depth_order],
        title="← 工程深度 →", range=[-0.6, len(depth_order) - 0.4],
        showgrid=True, gridcolor="#eeece7", zeroline=False,
    ),
)

st.plotly_chart(fig, use_container_width=True, theme=None)

st.markdown("---")

# ── Domain drill-down ────────────────────────────────────
st.markdown("### 選一個領域，看細分職稱")

domain_totals = {}
for d in domain_order:
    domain_totals[d] = sum(p["count"] for p in landscape if p["domain"] == d)

cols = st.columns(4)
for i, domain in enumerate(domain_order):
    with cols[i]:
        st.markdown(
            f"""
            <div class="domain-card">
                <div class="domain-title">{domain}</div>
                <div class="domain-tagline">{ct.DOMAIN_TAGLINE[domain]}</div>
                <div class="domain-count">{domain_totals[domain]:,}</div>
                <div class="domain-count-label">筆職缺</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button(f"展開 {domain}", key=f"expand_{domain}", use_container_width=True):
            st.session_state["career_map_domain"] = domain
            st.switch_page("pages/2_Career_Map.py")

selected_domain = st.selectbox(
    "或直接選擇領域查看子分類概況",
    options=domain_order,
    key="explore_domain_select",
)

role_summaries = ct.build_role_summary(rows, domain=selected_domain)

st.markdown(f"#### {selected_domain} 底下的子分類職稱")
if not role_summaries:
    st.info("目前這個領域還沒有足夠的職缺資料 — 可能是爬蟲範圍尚未涵蓋，或資料還在累積中。")
else:
    for rs in role_summaries:
        salary_txt = f"NT$ {rs['median_salary']:,.0f}" if rs["median_salary"] else "資料不足"
        st.markdown(
            f"- **{rs['role_normalized']}**"
            f"（{ct.TECH_DEPTH_LABEL[rs['tech_depth']]} · {rs['tech_depth']}） "
            f"— {rs['count']} 筆職缺，薪資中位數 {salary_txt}"
        )

    if st.button("查看完整 Career Map →", type="primary"):
        st.session_state["career_map_domain"] = selected_domain
        st.switch_page("pages/2_Career_Map.py")
