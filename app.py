#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Career_Overfitter — Streamlit 主入口
執行方式:
    streamlit run app.py
"""

import streamlit as st

st.set_page_config(
    page_title="Career Overfitter",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 全域 CSS ──────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@300;400;500&display=swap');

html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
    background: #f9f8f6;
}

h1, h2, h3 {
    font-family: 'Syne', sans-serif;
    font-weight: 800;
    color: #111;
}

.block-container {
    padding-top: 2rem;
    padding-bottom: 2rem;
}

.hero-wrap {
    padding: 0.5rem 0 1.25rem 0;
}

.hero-title {
    font-size: 2.5rem;
    line-height: 1.08;
    margin-bottom: 0.45rem;
    color: #111;
}

.hero-sub {
    font-size: 1rem;
    color: #5f5a54;
    margin-bottom: 0.35rem;
    line-height: 1.7;
}

.hero-note {
    font-size: 0.9rem;
    color: #8a847b;
}

.section-divider {
    margin: 1rem 0 1.5rem 0;
    border-top: 1px solid #e5e2db;
}

.card-shell {
    border: 1px solid #e0ddd7;
    border-radius: 14px;
    background: #ffffff;
    padding: 1.2rem 1.15rem;
    min-height: 220px;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);
    transition: all 0.18s ease;
}

.card-shell:hover {
    border-color: #cfc8be;
    transform: translateY(-2px);
    box-shadow: 0 8px 22px rgba(0, 0, 0, 0.06);
    background: #fcfbf9;
}

.card-kicker {
    font-size: 0.74rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #8b8175;
    margin-bottom: 0.7rem;
}

.card-title {
    font-family: 'Syne', sans-serif;
    font-size: 1.2rem;
    font-weight: 800;
    color: #111;
    margin-bottom: 0.6rem;
}

.card-desc {
    font-size: 0.92rem;
    color: #5f5a54;
    line-height: 1.75;
    min-height: 90px;
}

.card-tag {
    display: inline-block;
    margin-top: 0.95rem;
    padding: 4px 10px;
    border-radius: 999px;
    font-size: 0.76rem;
    font-weight: 600;
    background: #e8edf5;
    color: #1e3a5f;
}

.footer-note {
    margin-top: 1.2rem;
    font-size: 0.82rem;
    color: #8a847b;
}
</style>
""", unsafe_allow_html=True)

# ── 首頁內容 ──────────────────────────────────────────────
st.markdown(
    """
    <div class="hero-wrap">
        <div class="hero-title">🎯 Career Overfitter</div>
        <div class="hero-sub">
            從 104 人力銀行職缺資料，幫你找到最 fit 的職涯方向。<br>
            你可以先瀏覽市場職缺，再看技能結構，最後用履歷做 CV Fit 分析。
        </div>
        <div class="hero-note">請從下方功能入口開始，或使用左側選單切換頁面。</div>
    </div>
    <div class="section-divider"></div>
    """,
    unsafe_allow_html=True,
)

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown(
        """
        <div class="card-shell">
            <div class="card-kicker">Explore</div>
            <div class="card-title">職缺瀏覽</div>
            <div class="card-desc">
                依產業大類、產業別、職能大類、職能中類與職能別快速篩選，
                查看真實職缺內容、職類標籤、技能需求與 104 原始連結。
            </div>
            <div class="card-tag">第一步：先看市場</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.page_link("pages/1_job_search.py", label="進入職缺瀏覽", icon="🔍")

with col2:
    st.markdown(
        """
        <div class="card-shell">
            <div class="card-kicker">Analyze</div>
            <div class="card-title">技能 Dashboard</div>
            <div class="card-desc">
                查看全市場技能熱度、產業與職能的技能分布，
                比較跨產業與跨職能之間的共同技能與差異。
            </div>
            <div class="card-tag">第二步：理解技能結構</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.page_link("pages/2_skill_dashboard.py", label="進入技能 Dashboard", icon="📊")

with col3:
    st.markdown(
        """
        <div class="card-shell">
            <div class="card-kicker">Match</div>
            <div class="card-title">CV Fit 分析</div>
            <div class="card-desc">
                貼上履歷，自動抽取技能，對照市場需求，
                看你的技能最適合哪些職能，以及還缺哪些關鍵能力。
            </div>
            <div class="card-tag">第三步：做履歷適配分析</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.page_link("pages/3_cv_fitting_tool.py", label="進入 CV Fit 分析", icon="📄")

st.markdown(
    """
    <div class="footer-note">
        建議使用流程：職缺瀏覽 → 技能 Dashboard → CV Fit 分析
    </div>
    """,
    unsafe_allow_html=True,
)
