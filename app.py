#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Career_Overfitter — Streamlit 主入口
"Google Maps for Analytics Careers" — 幫你找到藏在各種職稱底下的分析工作。

執行方式:
    streamlit run app.py

Flow:
    Explore Careers → Career Map → Choose Path → Understand Role →
    Upload Resume → Where Do I Fit? → View Matching Jobs → Improve Resume
"""

import streamlit as st

st.set_page_config(
    page_title="Career Overfitter",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="expanded",
)

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

.flow-strip {
    display: flex; flex-wrap: wrap; gap: 6px; align-items: center;
    margin: 0.6rem 0 1.4rem 0;
}
.flow-step {
    font-size: 0.78rem; font-weight: 600; color: #1e3a5f;
    background: #e8edf5; border-radius: 999px; padding: 4px 12px;
}
.flow-arrow { color: #b8b2a8; font-size: 0.9rem; }

.card-shell {
    border: 1px solid #e0ddd7;
    border-radius: 14px;
    background: #ffffff;
    padding: 1.2rem 1.15rem;
    min-height: 230px;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);
    transition: all 0.18s ease;
    margin-bottom: 0.75rem;
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

st.markdown(
    """
    <div class="hero-wrap">
        <div class="hero-title">🗺️ Career Overfitter</div>
        <div class="hero-sub">
            Google Maps for Analytics Careers — 很多人想走數據分析，但「數據分析」這件事
            藏在很多不同的職稱與部門底下。這個工具用 104 的真實職缺資料，幫你先看懂
            這張地圖，再找到自己的位置。
        </div>
        <div class="hero-note">請從下方功能入口開始，或使用左側選單切換頁面。</div>
    </div>
    <div class="flow-strip">
        <span class="flow-step">Explore Careers</span><span class="flow-arrow">→</span>
        <span class="flow-step">Career Map</span><span class="flow-arrow">→</span>
        <span class="flow-step">Choose Path</span><span class="flow-arrow">→</span>
        <span class="flow-step">Understand Role</span><span class="flow-arrow">→</span>
        <span class="flow-step">Upload Resume</span><span class="flow-arrow">→</span>
        <span class="flow-step">Where Do I Fit?</span><span class="flow-arrow">→</span>
        <span class="flow-step">View Matching Jobs</span><span class="flow-arrow">→</span>
        <span class="flow-step">Improve Resume</span>
    </div>
    <div class="section-divider"></div>
    """,
    unsafe_allow_html=True,
)

col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.markdown(
        """
        <div class="card-shell">
            <div class="card-kicker">Step 1 · Landscape</div>
            <div class="card-title">🗺️ Explore Careers</div>
            <div class="card-desc">
                X 軸是業務應用領域，Y 軸是工程深度。先看市場地圖，
                知道「分析工作」實際分布在哪裡，泡泡大小代表職缺數量。
            </div>
            <div class="card-tag">先看全貌</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("進入 Explore Careers", key="go_explore", use_container_width=True):
        st.switch_page("pages/1_Explore_Careers.py")

with col2:
    st.markdown(
        """
        <div class="card-shell">
            <div class="card-kicker">Step 2 · Choose Path</div>
            <div class="card-title">🧭 Career Map</div>
            <div class="card-desc">
                展開領域看子分類職稱（例如 Product Analytics 底下的
                Growth Analyst、Marketplace Analyst），再看單一角色的
                完整輪廓：做什麼、常見職稱、薪資、技能、公司、職缺。
            </div>
            <div class="card-tag">選一條路，看懂它</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("進入 Career Map", key="go_map", use_container_width=True):
        st.switch_page("pages/2_Career_Map.py")

with col3:
    st.markdown(
        """
        <div class="card-shell">
            <div class="card-kicker">Step 3 · Where Do I Fit?</div>
            <div class="card-title">📄 Resume</div>
            <div class="card-desc">
                貼上履歷，自動抽取技能，算出跟每條 Career Path 的
                Fit Score，再問 Career Advisor：這條路為什麼適合我、
                我還缺什麼。
            </div>
            <div class="card-tag">上傳履歷，看你的位置</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("進入 Resume", key="go_resume", use_container_width=True):
        st.switch_page("pages/3_Resume.py")

with col4:
    st.markdown(
        """
        <div class="card-shell">
            <div class="card-kicker">Compare</div>
            <div class="card-title">📈 Market Trends</div>
            <div class="card-desc">
                不是「Top SQL / Top Python」排行榜，而是 Compare Career
                Paths — 同一個技能在不同路徑的重要程度、各職稱薪資中位數、
                產業分布。
            </div>
            <div class="card-tag">比較不同路徑</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("進入 Market Trends", key="go_trends", use_container_width=True):
        st.switch_page("pages/4_Market_Trends.py")

with col5:
    st.markdown(
        """
        <div class="card-shell">
            <div class="card-kicker">Step 4 · Apply</div>
            <div class="card-title">🎯 Jobs</div>
            <div class="card-desc">
                依 Career Path（不是職稱關鍵字）篩選真實職缺，
                或直接描述你想做的工作，AI 會先告訴你這像哪些 Career
                Path，再列出對應職缺。
            </div>
            <div class="card-tag">找到匹配職缺</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("進入 Jobs", key="go_jobs", use_container_width=True):
        st.switch_page("pages/5_Jobs.py")

st.markdown(
    """
    <div class="footer-note">
        建議使用流程：Explore Careers → Career Map → Resume → Jobs（Market Trends 隨時可查）
    </div>
    """,
    unsafe_allow_html=True,
)
