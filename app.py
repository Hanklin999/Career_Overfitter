#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Career_Overfitter — Streamlit 主入口
執行方式: streamlit run app.py
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
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;700;800&family=DM+Sans:wght@300;400;500&display=swap');

html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
}
h1, h2, h3 {
    font-family: 'Syne', sans-serif;
    font-weight: 800;
}

/* Sidebar */
section[data-testid="stSidebar"] {
    background: #0f0f0f;
    border-right: 1px solid #2a2a2a;
}
section[data-testid="stSidebar"] * {
    color: #e8e8e8 !important;
}
section[data-testid="stSidebar"] .stRadio label {
    font-family: 'Syne', sans-serif;
    font-size: 0.9rem;
    letter-spacing: 0.04em;
}

/* Metric cards */
div[data-testid="metric-container"] {
    background: #f7f5f0;
    border: 1px solid #e0ddd7;
    border-radius: 8px;
    padding: 1rem;
}

/* Buttons */
.stButton > button {
    font-family: 'Syne', sans-serif;
    font-weight: 700;
    letter-spacing: 0.05em;
    border-radius: 4px;
    border: 2px solid #0f0f0f;
    background: #0f0f0f;
    color: #f7f5f0;
    transition: all 0.15s;
}
.stButton > button:hover {
    background: #f7f5f0;
    color: #0f0f0f;
}

/* Tag pills */
.tag-pill {
    display: inline-block;
    background: #f0ede8;
    border: 1px solid #d4cfc8;
    border-radius: 20px;
    padding: 2px 10px;
    font-size: 0.78rem;
    margin: 2px;
    font-family: 'DM Sans', sans-serif;
    color: #3a3a3a;
}
.tag-pill.skill {
    background: #e8f0fe;
    border-color: #c5d8fd;
    color: #1a56db;
}
.tag-pill.role {
    background: #fef3e8;
    border-color: #fdd5a0;
    color: #b45309;
}

/* Score bar */
.score-bar-wrap { background: #e8e8e8; border-radius: 4px; height: 8px; margin: 4px 0; }
.score-bar-fill { height: 8px; border-radius: 4px; background: #0f0f0f; }

/* Job card */
.job-card {
    border: 1px solid #e0ddd7;
    border-radius: 10px;
    padding: 1.2rem 1.4rem;
    margin-bottom: 0.8rem;
    background: #fff;
    transition: box-shadow 0.15s;
}
.job-card:hover { box-shadow: 0 4px 16px rgba(0,0,0,0.08); }
.job-card-title { font-family: 'Syne', sans-serif; font-weight: 700; font-size: 1.05rem; color: #0f0f0f; }
.job-card-meta { font-size: 0.82rem; color: #666; margin: 4px 0 8px 0; }
</style>
""", unsafe_allow_html=True)

# ── 首頁內容 ──────────────────────────────────────────────
st.markdown("""
<div style="padding: 3rem 0 2rem 0;">
  <div style="font-family:'Syne',sans-serif; font-size:3rem; font-weight:800; line-height:1.1; color:#0f0f0f;">
    Career<br><span style="color:#b45309;">Overfitter</span>
  </div>
  <p style="font-size:1.1rem; color:#555; margin-top:1rem; max-width:520px;">
    從 104 人力銀行職缺資料，幫你找到最 fit 的職涯方向。
  </p>
</div>
""", unsafe_allow_html=True)

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("""
    <div class="job-card" style="border-left: 4px solid #0f0f0f;">
      <div class="job-card-title">🔍 職缺瀏覽</div>
      <div class="job-card-meta" style="margin-top:8px;">
        搜尋、篩選、瀏覽已爬取的職缺，查看 role / skill 分布。
      </div>
    </div>
    """, unsafe_allow_html=True)

with col2:
    st.markdown("""
    <div class="job-card" style="border-left: 4px solid #b45309;">
      <div class="job-card-title">📄 CV Fit 分析</div>
      <div class="job-card-meta" style="margin-top:8px;">
        上傳履歷，自動抽取技能，計算與各 role 的 fit score。
      </div>
    </div>
    """, unsafe_allow_html=True)

with col3:
    st.markdown("""
    <div class="job-card" style="border-left: 4px solid #1a56db;">
      <div class="job-card-title">📊 技能 Dashboard</div>
      <div class="job-card-meta" style="margin-top:8px;">
        市場技能需求熱度、薪資分布、產業趨勢一覽。
      </div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("---")
st.markdown(
    "<p style='font-size:0.8rem; color:#aaa;'>← 從左側選單選擇功能</p>",
    unsafe_allow_html=True,
)
