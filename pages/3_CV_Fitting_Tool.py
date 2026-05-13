#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Page 3 — CV Fitting Tool"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from collections import defaultdict
from utils.supabase_client import _get
from utils.cv_parser import (
    extract_skills_from_text,
    compute_fit_scores,
    build_role_skill_demand_from_db,
)

st.set_page_config(page_title="CV Fitting Tool | Career Overfitter", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@300;400;500&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; background:#f9f8f6; }
h1,h2,h3 { font-family: 'Syne', sans-serif; font-weight: 800; }
.fit-card { border:1px solid #e0ddd7; border-radius:10px; padding:1.2rem 1.4rem; margin-bottom:0.8rem; background:#fff; }
.fit-role { font-family:'Syne',sans-serif; font-weight:700; font-size:1.05rem; }
.tag { display:inline-block; border-radius:20px; padding:2px 10px; font-size:0.75rem; margin:2px; }
.tag-match { background:#e8f0fe; border:1px solid #c5d8fd; color:#1a56db; }
.tag-gap   { background:#fef2f2; border:1px solid #fecaca; color:#dc2626; }
.tag-skill { background:#f0fdf4; border:1px solid #bbf7d0; color:#15803d; }
.tag-optional { background:#f7f3ea; border:1px solid #e7dcc7; color:#7a5b22; }
.filter-section-label {
    font-size: 0.72rem;
    font-weight: 700;
    color: #888;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin: 12px 0 6px 0;
}
.group-box {
    border:1px solid #e5e2db;
    border-radius:10px;
    padding:12px 14px;
    background:#fcfbf9;
    margin-bottom:12px;
}
.subtle-note { color:#888; font-size:0.82rem; margin-top:2px; }
</style>
""", unsafe_allow_html=True)

st.markdown("<h1 style='margin-bottom:0'>📄 CV Fitting Tool</h1>", unsafe_allow_html=True)
st.markdown("<p style='color:#888;margin-top:4px;'>貼上履歷 → 自動抽取技能 → 比對市場需求 → 找出技能缺口</p>", unsafe_allow_html=True)
st.markdown("---")


@st.cache_data(ttl=300)
def load_postings():
    return _get("job_posting", {
        "select": (
            "role_normalized,job_parent_category,job_sub_category,"
            "industry_bucket,industry_raw,skill_canonical"
        ),
        "limit": 5000,
    })


@st.cache_data(ttl=600)
def load_taxonomy():
    root = Path(__file__).resolve().parent.parent
    path = root / "skill_taxonomy.csv"
    if not path.exists():
        return pd.DataFrame(columns=["skill_parent_category", "skill_sub_category", "canonical_skill_name"])
    return pd.read_csv(path, encoding="utf-8-sig").fillna("")


rows = load_postings()
taxonomy = load_taxonomy()

skill_to_parent = dict(zip(taxonomy["canonical_skill_name"], taxonomy["skill_parent_category"]))
skill_to_sub = dict(zip(taxonomy["canonical_skill_name"], taxonomy["skill_sub_category"]))

job_parent_all = sorted({r.get("job_parent_category") for r in rows if r.get("job_parent_category")})
industry_parent_all = sorted({r.get("industry_bucket") for r in rows if r.get("industry_bucket")})


def get_role_sub_options(parent):
    return sorted({
        r.get("job_sub_category")
        for r in rows
        if r.get("job_parent_category") == parent and r.get("job_sub_category")
    })


def get_industry_sub_options(parent):
    return sorted({
        r.get("industry_raw")
        for r in rows
        if r.get("industry_bucket") == parent and r.get("industry_raw")
    })


def count_skills(job_rows):
    counter = defaultdict(int)
    for r in job_rows:
        for s in (r.get("skill_canonical") or []):
            counter[s] += 1
    return counter


def skill_freq(job_rows):
    n = len(job_rows)
    if not n:
        return {}
    cnt = count_skills(job_rows)
    return {s: c / n for s, c in cnt.items()}


def group_rows_by_role(job_rows):
    grouped = defaultdict(list)
    for r in job_rows:
        role = r.get("role_normalized")
        if role and role != "Unclassified":
            grouped[role].append(r)
    return grouped


def group_rows_by_subcategory(job_rows):
    grouped = defaultdict(list)
    for r in job_rows:
        sub = r.get("job_sub_category") or "其他"
        grouped[sub].append(r)
    return grouped


def build_subcategory_role_demand(job_rows):
    grouped = group_rows_by_subcategory(job_rows)
    result = {}
    for sub, sub_rows in grouped.items():
        result[sub] = build_role_skill_demand_from_db(sub_rows)
    return result


def build_radar_data(cv_skills, filtered_rows, top_n=6):
    if not filtered_rows:
        return None
    freq_map = skill_freq(filtered_rows)
    if not freq_map:
        return None

    sub_counter = defaultdict(list)
    for skill, freq in freq_map.items():
        sub = skill_to_sub.get(skill, "其他")
        sub_counter[sub].append((skill, freq))

    ranked_subs = []
    for sub, items in sub_counter.items():
        ranked_subs.append((sub, sum(v for _, v in items)))
    ranked_subs = sorted(ranked_subs, key=lambda x: x[1], reverse=True)[:top_n]

    axes = []
    target_vals = []
    cv_vals = []

    for sub, _ in ranked_subs:
        items = sub_counter[sub]
        total_target = sum(v for _, v in items)
        matched_target = sum(v for skill, v in items if skill in cv_skills)
        coverage = matched_target / total_target if total_target else 0
        axes.append(sub)
        target_vals.append(1.0)
        cv_vals.append(round(coverage, 4))

    return axes, target_vals, cv_vals


def radar_chart(axes, target_vals, cv_vals):
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=target_vals + [target_vals[0]],
        theta=axes + [axes[0]],
        fill='toself',
        name='目標需求',
        line=dict(color='#c98b2a', width=2),
        fillcolor='rgba(201,139,42,0.20)'
    ))
    fig.add_trace(go.Scatterpolar(
        r=cv_vals + [cv_vals[0]],
        theta=axes + [axes[0]],
        fill='toself',
        name='CV 技能覆蓋',
        line=dict(color='#1e3a5f', width=2),
        fillcolor='rgba(30,58,95,0.25)'
    ))
    fig.update_layout(
        paper_bgcolor='white',
        plot_bgcolor='white',
        font=dict(family='DM Sans', color='#111'),
        height=460,
        margin=dict(l=40, r=40, t=30, b=20),
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 1], tickformat='.0%'),
            angularaxis=dict(tickfont=dict(size=11))
        ),
        legend=dict(orientation='h', y=1.12)
    )
    return fig


input_mode = st.radio("輸入方式", ["貼上文字", "上傳 .txt / .md 檔案"], horizontal=True)

cv_text = ""
if input_mode == "貼上文字":
    cv_text = st.text_area(
        "履歷內容（中英文皆可）",
        height=250,
        placeholder="貼上你的技能、工作經歷、專案描述..."
    )
else:
    uploaded = st.file_uploader("上傳純文字檔", type=["txt", "md"])
    if uploaded:
        cv_text = uploaded.read().decode("utf-8", errors="ignore")
        st.success(f"✅ 已載入 {len(cv_text)} 字元")
        with st.expander("預覽內容"):
            st.text(cv_text[:1000] + ("..." if len(cv_text) > 1000 else ""))

# ── 新增：選填目標職能 / 產業 ─────────────────────────────
st.markdown('<div class="group-box">', unsafe_allow_html=True)
st.markdown("<div class='filter-section-label'>選填目標條件</div>", unsafe_allow_html=True)
st.markdown(
    "<span class='tag tag-optional'>選填</span> <span class='subtle-note'>若有指定目標職能 / 產業，會先用該市場切片與你的 CV 做雷達圖比較</span>",
    unsafe_allow_html=True,
)

r1, r2 = st.columns(2)
with r1:
    sel_job_parent = st.selectbox("職能大類（選填）", ["全部"] + job_parent_all, key="cv_job_parent")
with r2:
    job_sub_options = ["全部"] if sel_job_parent == "全部" else ["全部"] + get_role_sub_options(sel_job_parent)
    sel_job_sub = st.selectbox("職能中類（選填）", job_sub_options, key="cv_job_sub", disabled=(sel_job_parent == "全部"))

r3, r4 = st.columns(2)
with r3:
    sel_ind_parent = st.selectbox("產業大類（選填）", ["全部"] + industry_parent_all, key="cv_ind_parent")
with r4:
    ind_sub_options = ["全部"] if sel_ind_parent == "全部" else ["全部"] + get_industry_sub_options(sel_ind_parent)
    sel_ind_sub = st.selectbox("產業別（選填）", ind_sub_options, key="cv_ind_sub", disabled=(sel_ind_parent == "全部"))

st.markdown('</div>', unsafe_allow_html=True)

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
    st.markdown(
        f"<p style='color:#888;font-size:0.82rem;'>共 {len(cv_skills)} 個 canonical skill</p>",
        unsafe_allow_html=True,
    )

    # 全市場需求
    with st.spinner("載入市場需求資料..."):
        role_skill_demand_all = build_role_skill_demand_from_db(rows)

    if not role_skill_demand_all:
        st.error("資料庫尚無已清洗職缺，請先執行 cleaner.py")
        st.stop()

    # ── 依使用者選填條件過濾資料 ─────────────────────────
    filtered_rows = [
        r for r in rows
        if (sel_job_parent == "全部" or r.get("job_parent_category") == sel_job_parent)
        and (sel_job_sub == "全部" or r.get("job_sub_category") == sel_job_sub)
        and (sel_ind_parent == "全部" or r.get("industry_bucket") == sel_ind_parent)
        and (sel_ind_sub == "全部" or r.get("industry_raw") == sel_ind_sub)
    ]

    use_segment = any([
        sel_job_parent != "全部",
        sel_job_sub != "全部",
        sel_ind_parent != "全部",
        sel_ind_sub != "全部",
    ])

    # ── 雷達圖：CV vs 選定職能 / 產業切片 ─────────────────
    if use_segment:
        st.markdown("---")
        st.markdown("### 🕸️ 技能匹配雷達圖")

        segment_label = " ｜ ".join([
            f"職能：{sel_job_parent}{' / ' + sel_job_sub if sel_job_sub != '全部' else ''}" if sel_job_parent != "全部" else "職能：全部",
            f"產業：{sel_ind_parent}{' / ' + sel_ind_sub if sel_ind_sub != '全部' else ''}" if sel_ind_parent != "全部" else "產業：全部",
        ])
        st.caption(f"分析切片：{segment_label} ｜ 樣本職缺：{len(filtered_rows)} 筆")

        radar_data = build_radar_data(cv_skills, filtered_rows, top_n=6)
        if radar_data:
            axes, target_vals, cv_vals = radar_data
            overall_match = sum(cv_vals) / len(cv_vals) if cv_vals else 0
            st.metric("目標市場技能覆蓋率", f"{overall_match:.0%}")
            st.plotly_chart(radar_chart(axes, target_vals, cv_vals), use_container_width=True)

            freq_map_segment = skill_freq(filtered_rows)
            missing = [(s, f) for s, f in freq_map_segment.items() if s not in cv_skills]
            missing = sorted(missing, key=lambda x: x[1], reverse=True)[:12]
            if missing:
                st.markdown("**優先補強技能**")
                gap_html = " ".join(f'<span class="tag tag-gap">{s}</span>' for s, _ in missing)
                st.markdown(gap_html, unsafe_allow_html=True)
        else:
            st.info("目前這個職能 / 產業切片沒有足夠技能資料可供雷達圖分析。")

    # ── Fit Score：先出職能中類，再展開職能名稱 ────────────
    st.markdown("---")
    st.markdown("### 🎯 Fit Score 排名")
    st.markdown(
        "<p style='color:#888;font-size:0.82rem;'>先依職能中類彙總，再展開查看各職能名稱的 Fit Score</p>",
        unsafe_allow_html=True,
    )

    fit_source_rows = filtered_rows if (use_segment and filtered_rows) else rows
    role_skill_demand_fit = build_role_skill_demand_from_db(fit_source_rows)

    with st.spinner("計算 Fit Score..."):
        role_results = compute_fit_scores(cv_skills, role_skill_demand_fit, top_n=50)

    if not role_results:
        st.warning("目前沒有可計算的 Fit Score 結果。")
        st.stop()

    # role → sub category mapping
    role_to_sub = {}
    for r in fit_source_rows:
        role = r.get("role_normalized")
        sub = r.get("job_sub_category") or "其他"
        if role and role not in role_to_sub:
            role_to_sub[role] = sub

    sub_groups = defaultdict(list)
    for r in role_results:
        sub = role_to_sub.get(r["role"], "其他")
        sub_groups[sub].append(r)

    sub_summary = []
    for sub, items in sub_groups.items():
        avg_score = sum(x["fit_score"] for x in items) / len(items)
        total_sample = sum(x.get("sample_size", 0) for x in items)
        sub_summary.append((sub, avg_score, total_sample, items))

    sub_summary = sorted(sub_summary, key=lambda x: x[1], reverse=True)

    export_rows = []

    for rank, (sub, avg_score, total_sample, items) in enumerate(sub_summary, 1):
        score_pct = int(avg_score * 100)
        bar_color = "#0f0f0f" if score_pct >= 60 else "#b45309" if score_pct >= 30 else "#aaa"
        items = sorted(items, key=lambda x: x["fit_score"], reverse=True)

        with st.expander(f"#{rank} {sub} ｜ {score_pct}% ｜ {len(items)} 個職能別", expanded=(rank <= 3)):
            st.markdown(f"""
            <div style="background:#f0f0f0;border-radius:6px;height:8px;margin:4px 0 12px 0;">
              <div style="width:{score_pct}%;height:8px;border-radius:6px;background:{bar_color};"></div>
            </div>
            <div style="font-size:0.82rem;color:#777;margin-bottom:10px;">樣本職缺合計：{total_sample} 筆</div>
            """, unsafe_allow_html=True)

            for i, r in enumerate(items, 1):
                role_score_pct = int(r["fit_score"] * 100)
                role_bar_color = "#0f0f0f" if role_score_pct >= 60 else "#b45309" if role_score_pct >= 30 else "#aaa"
                matched_html = " ".join(f'<span class="tag tag-match">{s}</span>' for s in r["matched_skills"])
                gap_html = " ".join(f'<span class="tag tag-gap">{s}</span>' for s in r["gap_skills"][:6])

                st.markdown(f"""
                <div class="fit-card">
                  <div style="display:flex;justify-content:space-between;align-items:center;">
                    <div class="fit-role">{i}. {r['role']}</div>
                    <div style="font-size:1.2rem;font-family:'Syne',sans-serif;font-weight:800;color:{role_bar_color};">{role_score_pct}%</div>
                  </div>
                  <div style="background:#f0f0f0;border-radius:6px;height:8px;margin:6px 0;">
                    <div style="width:{role_score_pct}%;height:8px;border-radius:6px;background:{role_bar_color};"></div>
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

                export_rows.append({
                    "job_sub_category": sub,
                    "role": r["role"],
                    "fit_score": r["fit_score"],
                    "matched_skills": ", ".join(r["matched_skills"]),
                    "gap_skills": ", ".join(r["gap_skills"]),
                    "sample_size": r["sample_size"],
                })

    st.markdown("---")
    df_export = pd.DataFrame(export_rows)
    csv = df_export.to_csv(index=False, encoding="utf-8-sig")
    st.download_button("📥 匯出 Fit Score CSV", data=csv, file_name="fit_scores.csv", mime="text/csv")
