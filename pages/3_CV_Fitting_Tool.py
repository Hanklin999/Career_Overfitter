#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Page 3 — CV Fitting Tool
上傳履歷 → 抽取技能 → 計算 Fit Score → 找缺口
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
from utils.supabase_client import get_job_postings
from utils.cv_parser import (
    extract_skills_from_text,
    compute_fit_scores,
    build_role_skill_demand_from_db,
)

st.set_page_config(page_title="CV Fitting Tool | Career Overfitter", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@300;400;500&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
h1,h2,h3 { font-family: 'Syne', sans-serif; font-weight: 800; }
.fit-card { border:1px solid #e0ddd7; border-radius:10px; padding:1.2rem 1.4rem; margin-bottom:0.8rem; background:#fff; }
.fit-role { font-family:'Syne',sans-serif; font-weight:700; font-size:1.05rem; }
.tag { display:inline-block; border-radius:20px; padding:2px 10px; font-size:0.75rem; margin:2px; }
.tag-match { background:#e8f0fe; border:1px solid #c5d8fd; color:#1a56db; }
.tag-gap   { background:#fef2f2; border:1px solid #fecaca; color:#dc2626; }
.tag-skill { background:#f0fdf4; border:1px solid #bbf7d0; color:#15803d; }
</style>
""", unsafe_allow_html=True)

st.markdown("<h1 style='margin-bottom:0'>📄 CV Fitting Tool</h1>", unsafe_allow_html=True)
st.markdown("<p style='color:#888;margin-top:4px;'>貼上履歷 → 自動抽取技能 → 比對市場需求 → 找出技能缺口</p>", unsafe_allow_html=True)
st.markdown("---")

input_mode = st.radio("輸入方式", ["貼上文字", "上傳 .txt / .md 檔案"], horizontal=True)

cv_text = ""
if input_mode == "貼上文字":
    cv_text = st.text_area("履歷內容（中英文皆可）", height=250, placeholder="貼上你的技能、工作經歷、專案描述...")
else:
    uploaded = st.file_uploader("上傳純文字檔", type=["txt", "md"])
    if uploaded:
        cv_text = uploaded.read().decode("utf-8", errors="ignore")
        st.success(f"✅ 已載入 {len(cv_text)} 字元")
        with st.expander("預覽內容"):
            st.text(cv_text[:1000] + ("..." if len(cv_text) > 1000 else ""))

if not cv_text.strip():
    st.info("請輸入履歷內容後點擊「開始分析」")
    st.stop()

if st.button("🚀 開始分析", type="primary"):
    with st.spinner("抽取技能中..."):
        cv_skills = extract_skills_from_text(cv_text)

    if not cv_skills:
        st.warning("⚠️ 未能辨識出已知技能，請確認 skill_alias.csv 存在於專案根目錄。")
        st.stop()

    st.markdown("### 🛠️ 從履歷辨識到的技能")
    skill_html = " ".join(f'<span class="tag tag-skill">{s}</span>' for s in cv_skills)
    st.markdown(skill_html, unsafe_allow_html=True)
    st.markdown(f"<p style='color:#888;font-size:0.82rem;'>共 {len(cv_skills)} 個 canonical skill</p>", unsafe_allow_html=True)

    with st.spinner("載入市場需求資料..."):
        rows = get_job_postings(limit=5000)
        role_skill_demand = build_role_skill_demand_from_db(rows)

    if not role_skill_demand:
        st.error("資料庫尚無已清洗職缺，請先執行 cleaner.py")
        st.stop()

    with st.spinner("計算 Fit Score..."):
        results = compute_fit_scores(cv_skills, role_skill_demand, top_n=15)

    st.markdown("---")
    st.markdown("### 🎯 Fit Score 排名")
    st.markdown("<p style='color:#888;font-size:0.82rem;'>依加權技能覆蓋率排序，★ 代表你的獨有優勢技能</p>", unsafe_allow_html=True)

    for i, r in enumerate(results, 1):
        score_pct = int(r["fit_score"] * 100)
        bar_color = "#0f0f0f" if score_pct >= 60 else "#b45309" if score_pct >= 30 else "#aaa"
        matched_html = " ".join(f'<span class="tag tag-match">{s}</span>' for s in r["matched_skills"])
        gap_html = " ".join(f'<span class="tag tag-gap">{s}</span>' for s in r["gap_skills"][:6])

        st.markdown(f"""
        <div class="fit-card">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <div class="fit-role">#{i} {r['role']}</div>
            <div style="font-size:1.4rem;font-family:'Syne',sans-serif;font-weight:800;color:{bar_color};">{score_pct}%</div>
          </div>
          <div style="background:#f0f0f0;border-radius:6px;height:8px;margin:6px 0;">
            <div style="width:{score_pct}%;height:8px;border-radius:6px;background:{bar_color};"></div>
          </div>
          <div style="margin-top:8px;">
            <span style="font-size:0.8rem;color:#555;font-weight:500;">✅ 匹配技能：</span><br>
            {matched_html if matched_html else '<span style="color:#aaa;font-size:0.8rem;">無</span>'}
          </div>
          <div style="margin-top:6px;">
            <span style="font-size:0.8rem;color:#555;font-weight:500;">❌ 缺口技能（高需求優先）：</span><br>
            {gap_html if gap_html else '<span style="color:#aaa;font-size:0.8rem;">無缺口</span>'}
          </div>
          <div style="margin-top:6px;font-size:0.75rem;color:#aaa;">樣本職缺：{r['sample_size']} 筆</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")
    df_export = pd.DataFrame([{
        "role": r["role"],
        "fit_score": r["fit_score"],
        "matched_skills": ", ".join(r["matched_skills"]),
        "gap_skills": ", ".join(r["gap_skills"]),
        "sample_size": r["sample_size"],
    } for r in results])
    csv = df_export.to_csv(index=False, encoding="utf-8-sig")
    st.download_button("📥 匯出 Fit Score CSV", data=csv, file_name="fit_scores.csv", mime="text/csv")
