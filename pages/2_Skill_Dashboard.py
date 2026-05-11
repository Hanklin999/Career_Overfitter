#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Page 2 — Skill Dashboard
技能分組 / 產業 × 職能分析 / 雙職能比較
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
from collections import defaultdict
from pathlib import Path as P

ROOT = P(__file__).resolve().parent.parent

st.set_page_config(page_title="Skill Dashboard | Career Overfitter", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@300;400;500&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; background: #f7f5f0; }
h1,h2,h3 { font-family: 'Syne', sans-serif; font-weight: 800; color: #0f0f0f; }
.section { background:#fff; border-radius:12px; padding:1.5rem; margin-bottom:1.2rem; border:1px solid #e0ddd7; }
.sec-title { font-family:'Syne',sans-serif; font-weight:700; font-size:1rem; color:#0f0f0f;
             border-bottom:2px solid #0f0f0f; padding-bottom:6px; margin-bottom:1rem; }
.cat-label { font-size:0.78rem; font-weight:700; color:#fff; padding:2px 8px;
             border-radius:4px; display:inline-block; margin-bottom:6px; }
.skill-row { display:flex; align-items:center; gap:8px; margin:3px 0; }
.skill-name { min-width:150px; font-size:0.8rem; color:#1a1a1a; text-align:right; }
.bar-bg { flex:1; background:#e8e8e8; border-radius:4px; height:18px; }
.bar-fill { height:18px; border-radius:4px; display:flex; align-items:center; padding-left:6px; min-width:24px; }
.bar-num { color:#fff; font-size:0.7rem; font-weight:700; }
.count-label { min-width:36px; font-size:0.72rem; color:#888; }
</style>
""", unsafe_allow_html=True)

st.markdown("<h1 style='margin-bottom:4px'>📊 Skill Dashboard</h1>", unsafe_allow_html=True)
st.markdown("<p style='color:#888;margin-top:0'>市場技能需求分析 — 分組 / 產業 / 職能比較</p>", unsafe_allow_html=True)
st.markdown("---")

# ── 載入資料 ──────────────────────────────────────────────
@st.cache_data(ttl=600)
def load_skill_taxonomy():
    path = ROOT / "skill_taxonomy.csv"
    if not path.exists():
        return pd.DataFrame(columns=["skill_parent_category","skill_sub_category","canonical_skill_name"])
    return pd.read_csv(path, encoding="utf-8-sig").fillna("")

@st.cache_data(ttl=300)
def load_job_postings_full():
    from utils.supabase_client import _get
    return _get("job_posting", {
        "select": "role_normalized,job_parent_category,job_sub_category,industry_bucket,skill_canonical",
        "limit": 5000,
    })

taxonomy = load_skill_taxonomy()
skill_to_parent = dict(zip(taxonomy["canonical_skill_name"], taxonomy["skill_parent_category"]))
skill_to_sub = dict(zip(taxonomy["canonical_skill_name"], taxonomy["skill_sub_category"]))
parent_categories = sorted(taxonomy["skill_parent_category"].unique().tolist())

# 顏色對應 skill_parent_category
COLORS = [
    "#0f0f0f","#b45309","#1a56db","#15803d","#7c3aed",
    "#be185d","#0369a1","#92400e","#065f46","#3730a3",
    "#9d174d","#1e40af","#166534","#5b21b6","#9a3412",
]
cat_color = {cat: COLORS[i % len(COLORS)] for i, cat in enumerate(parent_categories)}

rows = load_job_postings_full()
roles_all = sorted({r.get("role_normalized") for r in rows if r.get("role_normalized") and r.get("role_normalized") != "Unclassified"})
industries_all = sorted({r.get("industry_bucket") for r in rows if r.get("industry_bucket")})

# ── Helper ────────────────────────────────────────────────
def count_skills(job_rows):
    """從 job rows 計算 skill 出現次數，回傳 {skill: count}"""
    counter = defaultdict(int)
    for r in job_rows:
        skills = r.get("skill_canonical") or []
        if isinstance(skills, list):
            for s in skills:
                counter[s] += 1
    return counter

def render_skill_bars(skill_counts: dict, top_n: int = 20, color_map: dict = None):
    """依 skill_parent_category 分組渲染橫條圖"""
    if not skill_counts:
        st.info("無技能資料")
        return

    # 依 parent_category 分組
    grouped = defaultdict(list)
    for skill, cnt in skill_counts.items():
        parent = skill_to_parent.get(skill, "其他")
        grouped[parent].append((skill, cnt))

    # 排序：各組內依 count 降序
    for parent in grouped:
        grouped[parent].sort(key=lambda x: x[1], reverse=True)

    max_cnt = max(skill_counts.values()) if skill_counts else 1

    for parent in sorted(grouped.keys()):
        items = grouped[parent][:top_n]
        color = (color_map or cat_color).get(parent, "#555")
        st.markdown(f'<span class="cat-label" style="background:{color};">{parent}</span>', unsafe_allow_html=True)
        for skill, cnt in items:
            pct = max(int(cnt / max_cnt * 100), 3)
            st.markdown(f"""
            <div class="skill-row">
              <div class="skill-name">{skill}</div>
              <div class="bar-bg">
                <div class="bar-fill" style="width:{pct}%;background:{color};">
                  <span class="bar-num">{cnt}</span>
                </div>
              </div>
            </div>
            """, unsafe_allow_html=True)
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════
# Tab 1: 整體技能熱度（分組）
# Tab 2: 產業 × 職能分析
# Tab 3: 雙職能比較
# ══════════════════════════════════════════════════════════
tab1, tab2, tab3 = st.tabs(["🔥 整體技能熱度", "🏭 產業 × 職能分析", "⚖️ 雙職能比較"])

# ── Tab 1：整體技能熱度 ───────────────────────────────────
with tab1:
    st.markdown('<div class="sec-title">全市場技能需求（依類別分組）</div>', unsafe_allow_html=True)

    col_ctrl1, col_ctrl2 = st.columns([2, 1])
    with col_ctrl1:
        filter_parent = st.multiselect(
            "只看特定技能類別",
            parent_categories,
            default=[],
            key="tab1_parent",
        )
    with col_ctrl2:
        top_n_1 = st.slider("每組顯示 Top N", 5, 30, 15, 5, key="tab1_topn")

    filtered_rows = rows
    skill_counts_all = count_skills(filtered_rows)

    if filter_parent:
        skill_counts_all = {
            s: c for s, c in skill_counts_all.items()
            if skill_to_parent.get(s) in filter_parent
        }

    render_skill_bars(skill_counts_all, top_n=top_n_1)


# ── Tab 2：產業 × 職能分析 ───────────────────────────────
with tab2:
    st.markdown('<div class="sec-title">選定產業 / 職能，查看技能分布</div>', unsafe_allow_html=True)

    f1, f2 = st.columns(2)
    with f1:
        sel_industry = st.selectbox("產業", ["全部"] + industries_all, key="tab2_ind")
    with f2:
        sel_role = st.selectbox("職能 (Role)", ["全部"] + roles_all, key="tab2_role")

    top_n_2 = st.slider("每組 Top N", 5, 30, 12, 5, key="tab2_topn")

    filtered = rows
    if sel_industry != "全部":
        filtered = [r for r in filtered if r.get("industry_bucket") == sel_industry]
    if sel_role != "全部":
        filtered = [r for r in filtered if r.get("role_normalized") == sel_role]

    st.markdown(f"<p style='color:#888;font-size:0.82rem;'>符合條件職缺：{len(filtered)} 筆</p>", unsafe_allow_html=True)

    if filtered:
        sc = count_skills(filtered)
        render_skill_bars(sc, top_n=top_n_2)
    else:
        st.info("無符合條件的職缺")

    # 補充：產業下各 role 的技能數量統計表
    if sel_industry != "全部" and sel_role == "全部":
        st.markdown("---")
        st.markdown("**各職能技能需求數量**")
        role_skill_cnt = defaultdict(set)
        for r in filtered:
            role = r.get("role_normalized")
            skills = r.get("skill_canonical") or []
            if role and isinstance(skills, list):
                role_skill_cnt[role].update(skills)
        df_rs = pd.DataFrame([
            {"role": k, "unique_skills": len(v)}
            for k, v in sorted(role_skill_cnt.items(), key=lambda x: len(x[1]), reverse=True)
        ])
        st.dataframe(df_rs, use_container_width=True, height=300)


# ── Tab 3：雙職能比較 ─────────────────────────────────────
with tab3:
    st.markdown('<div class="sec-title">選兩個職能，比較技能需求差異</div>', unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        role_a = st.selectbox("職能 A", roles_all, key="compare_a")
    with c2:
        role_b_options = [r for r in roles_all if r != role_a]
        role_b = st.selectbox("職能 B", role_b_options, key="compare_b")

    top_n_3 = st.slider("每側 Top N 技能", 5, 25, 15, 5, key="tab3_topn")

    rows_a = [r for r in rows if r.get("role_normalized") == role_a]
    rows_b = [r for r in rows if r.get("role_normalized") == role_b]
    sc_a = count_skills(rows_a)
    sc_b = count_skills(rows_b)

    st.markdown(f"<p style='color:#888;font-size:0.82rem;'>職能A樣本：{len(rows_a)} 筆 ｜ 職能B樣本：{len(rows_b)} 筆</p>", unsafe_allow_html=True)

    # 共同 / 獨有技能
    skills_a_set = set(sc_a.keys())
    skills_b_set = set(sc_b.keys())
    common = skills_a_set & skills_b_set
    only_a = skills_a_set - skills_b_set
    only_b = skills_b_set - skills_a_set

    m1, m2, m3 = st.columns(3)
    m1.metric("共同技能", len(common))
    m2.metric(f"{role_a} 獨有", len(only_a))
    m3.metric(f"{role_b} 獨有", len(only_b))

    st.markdown("---")
    col_a, col_b = st.columns(2)

    def render_side(skill_counts, label, color, top_n):
        st.markdown(f'<span class="cat-label" style="background:{color};font-size:0.9rem;">{label}</span>', unsafe_allow_html=True)
        max_cnt = max(skill_counts.values()) if skill_counts else 1
        top_skills = sorted(skill_counts.items(), key=lambda x: x[1], reverse=True)[:top_n]
        for skill, cnt in top_skills:
            pct = max(int(cnt / max_cnt * 100), 3)
            parent = skill_to_parent.get(skill, "其他")
            skill_color = cat_color.get(parent, color)
            only_marker = " ★" if skill not in (skills_b_set if color == "#1a56db" else skills_a_set) else ""
            st.markdown(f"""
            <div class="skill-row">
              <div class="skill-name" style="color:{'#b45309' if only_marker else '#1a1a1a'};">{skill}{only_marker}</div>
              <div class="bar-bg">
                <div class="bar-fill" style="width:{pct}%;background:{skill_color};">
                  <span class="bar-num">{cnt}</span>
                </div>
              </div>
            </div>
            """, unsafe_allow_html=True)

    with col_a:
        render_side(sc_a, role_a, "#1a56db", top_n_3)
    with col_b:
        render_side(sc_b, role_b, "#b45309", top_n_3)

    st.markdown("---")
    st.markdown("**共同技能（兩個職能都要求）**")
    common_data = [(s, sc_a.get(s,0), sc_b.get(s,0)) for s in common]
    common_data.sort(key=lambda x: x[1]+x[2], reverse=True)
    if common_data:
        df_common = pd.DataFrame(common_data, columns=["skill", f"{role_a}_count", f"{role_b}_count"])
        df_common["skill_category"] = df_common["skill"].map(skill_to_parent)
        st.dataframe(df_common, use_container_width=True, height=300)
    else:
        st.info("兩個職能沒有共同技能")
