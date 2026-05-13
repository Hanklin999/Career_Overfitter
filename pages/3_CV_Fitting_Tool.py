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
from pathlib import Path as P

ROOT = P(__file__).resolve().parent.parent

from utils.supabase_client import _get
from utils.cv_parser import extract_skills_from_text, compute_fit_scores, build_role_skill_demand_from_db
from utils.ui_taxonomy import (
    build_skill_parent_colors,
    get_industry_parents, get_industry_subs,
    get_role_parents, get_role_subs,
    filter_rows as ut_filter_rows,
    format_industry_label, format_role_label,
    filter_label, FILTER_STYLE,
)

st.set_page_config(page_title="CV Fitting Tool | Career Overfitter", layout="wide")

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@300;400;500&display=swap');
html, body, [class*="css"] {{ font-family: 'DM Sans', sans-serif; }}
h1,h2,h3 {{ font-family: 'Syne', sans-serif; font-weight: 800; }}
.fit-card {{
    border: 1px solid #e0ddd7; border-radius: 10px;
    padding: 1.2rem 1.4rem; margin-bottom: 0.8rem; background: #fff;
}}
.fit-role {{ font-family:'Syne',sans-serif; font-weight:700; font-size:1.05rem; }}
.tag {{ display:inline-block; border-radius:20px; padding:2px 10px; font-size:0.75rem; margin:2px; }}
.tag-match {{ background:#e8f0fe; border:1px solid #c5d8fd; color:#1a56db; }}
.tag-gap   {{ background:#fef2f2; border:1px solid #fecaca; color:#dc2626; }}
.tag-skill {{ background:#f0fdf4; border:1px solid #bbf7d0; color:#15803d; }}
.tag-opt   {{ background:#f0ebe2; color:#5c3d11; border:1px solid #dcd5c7; border-radius:4px; padding:1px 8px; font-size:0.74rem; }}
.subcat-header {{
    font-family:'Syne',sans-serif; font-weight:700; font-size:0.92rem;
    color:#111; padding:8px 12px; background:#f3f0ea;
    border-radius:6px; margin-bottom:6px; cursor:pointer;
}}
{FILTER_STYLE}
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
    path = ROOT / "skill_taxonomy.csv"
    if not path.exists():
        return pd.DataFrame(columns=["skill_parent_category", "skill_sub_category", "canonical_skill_name"])
    return pd.read_csv(path, encoding="utf-8-sig").fillna("")


all_rows = load_postings()
taxonomy = load_taxonomy()
skill_to_parent = dict(zip(taxonomy["canonical_skill_name"], taxonomy["skill_parent_category"]))
skill_to_sub    = dict(zip(taxonomy["canonical_skill_name"], taxonomy["skill_sub_category"]))
parent_cats     = sorted(x for x in taxonomy["skill_parent_category"].unique() if x)
SKILL_COLORS    = build_skill_parent_colors(parent_cats)


# ── CV input ─────────────────────────────────────────────
input_mode = st.radio("輸入方式", ["貼上文字", "上傳 .txt / .md 檔案"], horizontal=True)

cv_text = ""
if input_mode == "貼上文字":
    cv_text = st.text_area("履歷內容（中英文皆可）", height=220,
                           placeholder="貼上你的技能、工作經歷、專案描述...")
else:
    uploaded = st.file_uploader("上傳純文字檔", type=["txt", "md"])
    if uploaded:
        cv_text = uploaded.read().decode("utf-8", errors="ignore")
        st.success(f"✅ 已載入 {len(cv_text)} 字元")
        with st.expander("預覽內容"):
            st.text(cv_text[:1000] + ("..." if len(cv_text) > 1000 else ""))


# ── Optional target filters ───────────────────────────────
st.markdown("---")
with st.expander("🎯 目標條件（選填 — 設定後啟用指定市場雷達圖分析）", expanded=True):
    st.caption("不選代表分析全市場；選擇後 Fit Score 與雷達圖會對應該切片市場需求")

    st.markdown(filter_label("🎯 選擇職能", first=True), unsafe_allow_html=True)
    rc1, rc2 = st.columns(2)
    with rc1:
        t_role_par = st.selectbox("職能大類（選填）",
                                  ["全部"] + get_role_parents(all_rows), key="cv_rp")
    with rc2:
        t_role_sub_opts = ["全部"] + (get_role_subs(all_rows, t_role_par) if t_role_par != "全部" else [])
        t_role_sub = st.selectbox("職能中類（選填）", t_role_sub_opts, key="cv_rs",
                                  disabled=(t_role_par == "全部"))

    st.markdown(filter_label("🏭 選擇產業"), unsafe_allow_html=True)
    ic1, ic2 = st.columns(2)
    with ic1:
        t_ind_par = st.selectbox("產業大類（選填）",
                                 ["全部"] + get_industry_parents(all_rows), key="cv_ip")
    with ic2:
        t_ind_sub_opts = ["全部"] + (get_industry_subs(all_rows, t_ind_par) if t_ind_par != "全部" else [])
        t_ind_sub = st.selectbox("產業別（選填）", t_ind_sub_opts, key="cv_is",
                                 disabled=(t_ind_par == "全部"))

has_target = (t_role_par != "全部" or t_ind_par != "全部")
if has_target:
    target_rows = ut_filter_rows(all_rows,
                                 industry_parent=t_ind_par, industry_sub=t_ind_sub,
                                 role_parent=t_role_par, role_sub=t_role_sub)
    target_label = " / ".join(p for p in [
        format_role_label(t_role_par, t_role_sub),
        format_industry_label(t_ind_par, t_ind_sub),
    ] if p != "全部產業" and p != "全部職能")
    st.info(f"目標市場切片：**{target_label}**｜{len(target_rows)} 筆職缺")
else:
    target_rows = all_rows
    target_label = "全市場"

st.markdown("---")

if not cv_text.strip():
    st.info("請輸入履歷內容後點擊「開始分析」")
    st.stop()

if not st.button("🚀 開始分析", type="primary"):
    st.stop()


# ── Extract skills ────────────────────────────────────────
with st.spinner("抽取技能中..."):
    cv_skills = extract_skills_from_text(cv_text)

if not cv_skills:
    st.warning("⚠️ 未能辨識出已知技能，請確認 skill_alias.csv 存在於專案根目錄。")
    st.stop()

st.markdown("### 🛠️ 從履歷辨識到的技能")
skill_html = " ".join(
    f'<span class="tag tag-skill" style="background:{SKILL_COLORS.get(skill_to_parent.get(s,""),"#e8edf5")}22;'
    f'border-color:{SKILL_COLORS.get(skill_to_parent.get(s,""),"#888")}55;">{s}</span>'
    for s in cv_skills
)
st.markdown(skill_html, unsafe_allow_html=True)
st.markdown(f"<p style='color:#888;font-size:0.82rem;'>共 {len(cv_skills)} 個 canonical skill</p>",
            unsafe_allow_html=True)


# ── Radar chart (only when target set) ───────────────────
if has_target and len(target_rows) > 0:
    st.markdown("---")
    st.markdown("### 📡 技能匹配雷達圖")
    st.caption(f"目標切片：{target_label}")

    sub_freq: dict[str, float] = defaultdict(float)
    sub_cnt: dict[str, int]    = defaultdict(int)
    n_target = len(target_rows)

    for r in target_rows:
        for sk in (r.get("skill_canonical") or []):
            sub = skill_to_sub.get(sk, "其他")
            sub_freq[sub] += 1 / n_target
            sub_cnt[sub] += 1

    top_subs = sorted(sub_freq, key=sub_freq.get, reverse=True)[:8]
    if top_subs:
        cv_sub_scores: dict[str, float] = defaultdict(float)
        for sk in cv_skills:
            sub = skill_to_sub.get(sk, "其他")
            if sub in top_subs:
                cv_sub_scores[sub] += sub_freq[sub] / len(cv_skills)

        max_val = max(sub_freq[s] for s in top_subs) or 1
        demand  = [sub_freq[s] / max_val for s in top_subs]
        cv_norm = [min(cv_sub_scores.get(s, 0) / max_val * 2, 1) for s in top_subs]

        θ = top_subs + [top_subs[0]]
        fig_r = go.Figure()
        fig_r.add_trace(go.Scatterpolar(r=demand + [demand[0]], theta=θ,
                                         fill="toself", name="目標需求",
                                         line=dict(color="#1e3a5f"), fillcolor="rgba(30,58,95,0.15)"))
        fig_r.add_trace(go.Scatterpolar(r=cv_norm + [cv_norm[0]], theta=θ,
                                         fill="toself", name="CV 覆蓋",
                                         line=dict(color="#e54d2e", dash="dot"), fillcolor="rgba(229,77,46,0.12)"))
        fig_r.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[0, 1], tickformat=".0%")),
            showlegend=True, height=400, margin=dict(l=40, r=40, t=30, b=30),
            font=dict(family="DM Sans"),
        )
        st.plotly_chart(fig_r, use_container_width=True)

        overall_match = sum(min(cv_sub_scores.get(s, 0), sub_freq[s]) for s in top_subs) / sum(sub_freq[s] for s in top_subs)
        st.metric("整體技能覆蓋率（目標切片）", f"{overall_match:.0%}")

        gap_skills_radar = sorted(
            [sk for sk in (set([s for r in target_rows for s in (r.get("skill_canonical") or [])]) - set(cv_skills))],
            key=lambda s: sub_freq.get(skill_to_sub.get(s, ""), 0), reverse=True
        )[:12]
        if gap_skills_radar:
            st.markdown("**⚠️ 優先補強技能（目標切片高需求）**")
            st.markdown(" ".join(
                f'<span class="tag tag-gap">{s}</span>' for s in gap_skills_radar
            ), unsafe_allow_html=True)


# ── Load market demand & compute Fit Scores ───────────────
st.markdown("---")
with st.spinner("載入市場需求資料..."):
    raw_rows = _get("job_posting", {
        "select": "role_normalized,job_sub_category,skill_canonical",
        "limit": 5000,
    })

    target_raw = _get("job_posting", {
        "select": "role_normalized,job_sub_category,skill_canonical,"
                  "job_parent_category,industry_bucket,industry_raw",
        "limit": 5000,
    }) if has_target else raw_rows

if has_target:
    target_raw_filtered = ut_filter_rows(target_raw,
                                          industry_parent=t_ind_par, industry_sub=t_ind_sub,
                                          role_parent=t_role_par, role_sub=t_role_sub)
    fit_source = target_raw_filtered if target_raw_filtered else target_raw
else:
    fit_source = raw_rows

role_skill_demand = build_role_skill_demand_from_db(fit_source)

if not role_skill_demand:
    st.error("資料庫尚無已清洗職缺，請先執行 cleaner.py")
    st.stop()

with st.spinner("計算 Fit Score..."):
    results = compute_fit_scores(cv_skills, role_skill_demand, top_n=30)


# ── Fit Score — grouped by job_sub_category ───────────────
st.markdown("### 🎯 Fit Score 排名")
st.markdown(
    "<p style='color:#888;font-size:0.82rem;'>"
    "先選取職能中類，展開後查看各職能別分數。</p>",
    unsafe_allow_html=True,
)

role_to_sub: dict[str, str] = {}
for r in fit_source:
    role = r.get("role_normalized")
    sub  = r.get("job_sub_category") or "其他"
    if role and role != "Unclassified":
        role_to_sub[role] = sub

sub_groups: dict[str, list] = defaultdict(list)
for res in results:
    sub = role_to_sub.get(res["role"], "其他")
    sub_groups[sub].append(res)

sub_avg: list[tuple[str, float]] = [
    (sub, sum(r["fit_score"] for r in items) / len(items))
    for sub, items in sub_groups.items()
]
sub_avg.sort(key=lambda x: x[1], reverse=True)

for sub, avg_score in sub_avg:
    avg_pct   = int(avg_score * 100)
    bar_color = "#0f0f0f" if avg_pct >= 60 else "#b45309" if avg_pct >= 30 else "#aaa"
    sub_items = sorted(sub_groups[sub], key=lambda r: r["fit_score"], reverse=True)

    with st.expander(
        f"📂 {sub} — 平均 {avg_pct}%　({len(sub_items)} 個職能別)",
        expanded=(avg_pct >= 60)
    ):
        mini_bar = (
            f"<div style='background:#f0f0f0;border-radius:4px;height:6px;margin:4px 0 12px 0;'>"
            f"<div style='width:{avg_pct}%;height:6px;border-radius:4px;background:{bar_color};'></div>"
            f"</div>"
        )
        st.markdown(mini_bar, unsafe_allow_html=True)

        for i, r in enumerate(sub_items, 1):
            score_pct = int(r["fit_score"] * 100)
            rc        = "#0f0f0f" if score_pct >= 60 else "#b45309" if score_pct >= 30 else "#aaa"
            matched_html = " ".join(f'<span class="tag tag-match">{s}</span>' for s in r["matched_skills"])
            gap_html     = " ".join(f'<span class="tag tag-gap">{s}</span>'   for s in r["gap_skills"][:6])

            st.markdown(f"""
            <div class="fit-card">
              <div style="display:flex;justify-content:space-between;align-items:center;">
                <div class="fit-role">#{i} {r['role']}</div>
                <div style="font-size:1.3rem;font-family:'Syne',sans-serif;font-weight:800;color:{rc};">{score_pct}%</div>
              </div>
              <div style="background:#f0f0f0;border-radius:6px;height:7px;margin:5px 0;">
                <div style="width:{score_pct}%;height:7px;border-radius:6px;background:{rc};"></div>
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


# ── Export ─────────────────────────────────────────────────
st.markdown("---")
df_export = pd.DataFrame([{
    "job_sub_category": role_to_sub.get(r["role"], "其他"),
    "role": r["role"],
    "fit_score": r["fit_score"],
    "matched_skills": ", ".join(r["matched_skills"]),
    "gap_skills": ", ".join(r["gap_skills"]),
    "sample_size": r["sample_size"],
} for r in results])
csv = df_export.to_csv(index=False, encoding="utf-8-sig")
st.download_button("📥 匯出 Fit Score CSV", data=csv, file_name="fit_scores.csv", mime="text/csv")
