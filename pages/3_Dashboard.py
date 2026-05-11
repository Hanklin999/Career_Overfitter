#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Page 3 — 技能需求 Dashboard
技能熱度 / 薪資分布 / 產業趨勢
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
from collections import defaultdict
from utils.supabase_client import (
    get_skill_demand,
    get_salary_by_role,
    get_job_postings,
)

st.set_page_config(page_title="技能 Dashboard | Career Overfitter", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@300;400;500&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
h1,h2,h3 { font-family: 'Syne', sans-serif; font-weight: 800; }
.section-title { font-family:'Syne',sans-serif; font-weight:700; font-size:1.1rem; margin:1.5rem 0 0.5rem 0; color:#0f0f0f; border-bottom:2px solid #0f0f0f; padding-bottom:4px; }
.bar-label { font-size:0.8rem; color:#333; }
.bar-bg { background:#f0f0f0; border-radius:4px; height:22px; margin:3px 0; position:relative; }
.bar-fill { height:22px; border-radius:4px; background:#0f0f0f; display:flex; align-items:center; padding-left:8px; }
.bar-text { color:#fff; font-size:0.75rem; font-weight:600; white-space:nowrap; }
</style>
""", unsafe_allow_html=True)

st.markdown("<h1 style='margin-bottom:0'>📊 技能需求 Dashboard</h1>", unsafe_allow_html=True)
st.markdown("<p style='color:#888;margin-top:4px;'>從 job_posting 即時聚合市場資料</p>", unsafe_allow_html=True)
st.markdown("---")

# ── Section 1: 技能熱度 ───────────────────────────────────
st.markdown('<div class="section-title">🔥 Top 技能需求（出現次數）</div>', unsafe_allow_html=True)

with st.spinner("載入技能資料..."):
    top_n = st.slider("顯示 Top N 技能", 10, 50, 25, 5)
    skill_data = get_skill_demand(top_n=top_n)

if skill_data:
    max_count = skill_data[0]["count"] if skill_data else 1
    for row in skill_data:
        pct = row["count"] / max_count
        bar_w = max(int(pct * 100), 4)
        st.markdown(f"""
        <div style="display:flex;align-items:center;gap:8px;margin:3px 0;">
          <div style="min-width:160px;font-size:0.82rem;color:#333;text-align:right;">{row['skill']}</div>
          <div style="flex:1;background:#f0f0f0;border-radius:4px;height:20px;">
            <div style="width:{bar_w}%;background:#0f0f0f;height:20px;border-radius:4px;
                        display:flex;align-items:center;padding-left:8px;min-width:30px;">
              <span style="color:#fff;font-size:0.72rem;font-weight:600;">{row['count']}</span>
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)
else:
    st.info("目前無技能資料，請先執行 cleaner.py")

st.markdown("---")

# ── Section 2: 薪資 by Role ───────────────────────────────
st.markdown('<div class="section-title">💰 各 Role 薪資中位數（月薪，千元）</div>', unsafe_allow_html=True)

with st.spinner("載入薪資資料..."):
    salary_rows = get_salary_by_role()

if salary_rows:
    role_salary: dict = defaultdict(list)
    for row in salary_rows:
        role = row.get("role_normalized")
        unit = row.get("salary_unit", "月薪")
        low = row.get("salary_low")
        high = row.get("salary_high")
        if not role or role == "Unclassified":
            continue
        mid = None
        if low and high:
            mid = (low + high) / 2
        elif low:
            mid = low
        if mid:
            # 年薪換算月薪
            if unit == "年薪":
                mid = mid / 12
            if 15000 < mid < 500000:  # 合理月薪範圍
                role_salary[role].append(mid)

    salary_summary = []
    for role, vals in role_salary.items():
        if len(vals) >= 3:
            import statistics
            salary_summary.append({
                "role": role,
                "median": statistics.median(vals),
                "count": len(vals),
            })
    salary_summary.sort(key=lambda x: x["median"], reverse=True)

    if salary_summary:
        max_salary = salary_summary[0]["median"]
        for row in salary_summary[:20]:
            pct = row["median"] / max_salary
            bar_w = max(int(pct * 100), 4)
            median_k = int(row["median"] / 1000)
            st.markdown(f"""
            <div style="display:flex;align-items:center;gap:8px;margin:3px 0;">
              <div style="min-width:160px;font-size:0.82rem;color:#333;text-align:right;">{row['role']}</div>
              <div style="flex:1;background:#f0f0f0;border-radius:4px;height:20px;">
                <div style="width:{bar_w}%;background:#b45309;height:20px;border-radius:4px;
                            display:flex;align-items:center;padding-left:8px;min-width:30px;">
                  <span style="color:#fff;font-size:0.72rem;font-weight:600;">{median_k}K</span>
                </div>
              </div>
              <div style="font-size:0.75rem;color:#aaa;min-width:50px;">n={row['count']}</div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("薪資樣本不足（每個 role 至少需要 3 筆）")
else:
    st.info("目前無薪資資料")

st.markdown("---")

# ── Section 3: 產業 × Remote 分布 ────────────────────────
st.markdown('<div class="section-title">🏭 產業分布 & Remote 比例</div>', unsafe_allow_html=True)

with st.spinner("載入產業資料..."):
    industry_rows = get_job_postings(limit=3000)

if industry_rows:
    industry_count: dict = defaultdict(int)
    industry_remote: dict = defaultdict(int)
    for row in industry_rows:
        ind = row.get("industry_bucket") or "Unknown"
        industry_count[ind] += 1
        if row.get("remote_work"):
            industry_remote[ind] += 1

    ind_summary = [
        {
            "industry": ind,
            "count": cnt,
            "remote_pct": round(industry_remote[ind] / cnt * 100, 1),
        }
        for ind, cnt in sorted(industry_count.items(), key=lambda x: x[1], reverse=True)
    ]

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**職缺數量**")
        max_ind = ind_summary[0]["count"] if ind_summary else 1
        for row in ind_summary:
            pct = row["count"] / max_ind
            bar_w = max(int(pct * 100), 4)
            st.markdown(f"""
            <div style="display:flex;align-items:center;gap:8px;margin:3px 0;">
              <div style="min-width:100px;font-size:0.82rem;color:#333;text-align:right;">{row['industry']}</div>
              <div style="flex:1;background:#f0f0f0;border-radius:4px;height:20px;">
                <div style="width:{bar_w}%;background:#1a56db;height:20px;border-radius:4px;
                            display:flex;align-items:center;padding-left:8px;min-width:30px;">
                  <span style="color:#fff;font-size:0.72rem;font-weight:600;">{row['count']}</span>
                </div>
              </div>
            </div>
            """, unsafe_allow_html=True)

    with col2:
        st.markdown("**Remote 比例 (%)**")
        for row in ind_summary:
            bar_w = max(int(row["remote_pct"]), 2)
            st.markdown(f"""
            <div style="display:flex;align-items:center;gap:8px;margin:3px 0;">
              <div style="min-width:100px;font-size:0.82rem;color:#333;text-align:right;">{row['industry']}</div>
              <div style="flex:1;background:#f0f0f0;border-radius:4px;height:20px;">
                <div style="width:{bar_w}%;background:#15803d;height:20px;border-radius:4px;
                            display:flex;align-items:center;padding-left:8px;min-width:30px;">
                  <span style="color:#fff;font-size:0.72rem;font-weight:600;">{row['remote_pct']}%</span>
                </div>
              </div>
            </div>
            """, unsafe_allow_html=True)
else:
    st.info("目前無產業資料")

st.markdown("---")

# ── Section 4: 快速統計表 ────────────────────────────────
st.markdown('<div class="section-title">📋 完整數據表（可排序）</div>', unsafe_allow_html=True)
tab1, tab2 = st.tabs(["技能需求表", "薪資表"])

with tab1:
    if skill_data:
        df_skill = pd.DataFrame(skill_data)
        st.dataframe(df_skill, use_container_width=True, height=400)
    else:
        st.info("無資料")

with tab2:
    if "salary_summary" in dir() and salary_summary:
        df_sal = pd.DataFrame(salary_summary)
        df_sal["median_K"] = (df_sal["median"] / 1000).round(1)
        st.dataframe(df_sal[["role", "median_K", "count"]], use_container_width=True, height=400)
    else:
        st.info("無資料")
