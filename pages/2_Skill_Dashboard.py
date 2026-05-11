#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Page 2 — Skill Dashboard"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from collections import defaultdict
from pathlib import Path as P

ROOT = P(__file__).resolve().parent.parent

st.set_page_config(page_title="Skill Dashboard | Career Overfitter", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@300;400;500&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
h1,h2,h3 { font-family: 'Syne', sans-serif; font-weight: 800; color:#0f0f0f; }
.sec-title { font-family:'Syne',sans-serif; font-weight:700; font-size:1rem; color:#0f0f0f;
             border-bottom:2px solid #0f0f0f; padding-bottom:5px; margin-bottom:1rem; }
</style>
""", unsafe_allow_html=True)

st.markdown("<h1 style='margin-bottom:4px'>📊 Skill Dashboard</h1>", unsafe_allow_html=True)
st.markdown("<p style='color:#888;margin-top:0'>市場技能需求分析</p>", unsafe_allow_html=True)
st.markdown("---")

# ── 載入資料 ──────────────────────────────────────────────
@st.cache_data(ttl=600)
def load_taxonomy():
    path = ROOT / "skill_taxonomy.csv"
    if not path.exists():
        return pd.DataFrame(columns=["skill_parent_category","skill_sub_category","canonical_skill_name"])
    return pd.read_csv(path, encoding="utf-8-sig").fillna("")

@st.cache_data(ttl=300)
def load_postings():
    from utils.supabase_client import _get
    return _get("job_posting", {
        "select": "role_normalized,job_parent_category,job_sub_category,industry_bucket,skill_canonical",
        "limit": 5000,
    })

taxonomy = load_taxonomy()
skill_to_parent = dict(zip(taxonomy["canonical_skill_name"], taxonomy["skill_parent_category"]))
skill_to_sub    = dict(zip(taxonomy["canonical_skill_name"], taxonomy["skill_sub_category"]))
parent_cats     = sorted(taxonomy["skill_parent_category"].unique())
sub_cats        = sorted(taxonomy["skill_sub_category"].unique())

# 顏色 palette（淺色系 on 深色 bar）
PALETTE = [
    "#60a5fa","#f97316","#34d399","#a78bfa","#fb7185",
    "#fbbf24","#22d3ee","#e879f9","#4ade80","#f472b6",
    "#38bdf8","#fb923c","#86efac","#c084fc","#fca5a5",
]
cat_color = {cat: PALETTE[i % len(PALETTE)] for i, cat in enumerate(parent_cats)}

rows = load_postings()
roles_all      = sorted({r.get("role_normalized") for r in rows if r.get("role_normalized") and r.get("role_normalized") != "Unclassified"})
industries_all = sorted({r.get("industry_bucket") for r in rows if r.get("industry_bucket")})

def count_skills(job_rows):
    counter = defaultdict(int)
    for r in job_rows:
        skills = r.get("skill_canonical") or []
        if isinstance(skills, list):
            for s in skills:
                counter[s] += 1
    return counter

def skill_freq(job_rows):
    """回傳 {skill: frequency(0~1)}，以職缺總數為分母"""
    n = len(job_rows)
    if not n:
        return {}
    cnt = count_skills(job_rows)
    return {s: c/n for s, c in cnt.items()}

# ══ Tabs ══════════════════════════════════════════════════
tab1, tab2, tab3, tab4 = st.tabs([
    "🔥 技能熱度",
    "🏭 產業 × 職能分析",
    "⚖️ 跨產業比較",
    "🔬 跨職能比較",
])

# ── Tab 1：技能熱度（跨組排序 + 顏色 by 大類）────────────
with tab1:
    st.markdown('<div class="sec-title">全市場技能需求</div>', unsafe_allow_html=True)

    ctrl1, ctrl2 = st.columns([2, 1])
    with ctrl1:
        view_mode = st.radio("排序維度", ["跨組統一排序", "依中類分組"], horizontal=True, key="t1_view")
    with ctrl2:
        top_n_1 = st.slider("Top N", 10, 60, 30, 5, key="t1_topn")

    filter_parent_1 = st.multiselect("只看特定大類", parent_cats, default=[], key="t1_filter")

    sc_all = count_skills(rows)

    if filter_parent_1:
        sc_all = {s: c for s, c in sc_all.items() if skill_to_parent.get(s) in filter_parent_1}

    if view_mode == "跨組統一排序":
        # 所有技能統一排序，顏色代表大類
        top_items = sorted(sc_all.items(), key=lambda x: x[1], reverse=True)[:top_n_1]
        skills_sorted  = [x[0] for x in top_items]
        counts_sorted  = [x[1] for x in top_items]
        colors_sorted  = [cat_color.get(skill_to_parent.get(s, ""), "#888") for s in skills_sorted]

        fig = go.Figure(go.Bar(
            x=counts_sorted,
            y=skills_sorted,
            orientation="h",
            marker_color=colors_sorted,
            text=counts_sorted,
            textposition="outside",
            textfont=dict(color="#0f0f0f", size=11),
        ))
        fig.update_layout(
            height=max(400, top_n_1 * 22),
            margin=dict(l=10, r=40, t=10, b=10),
            paper_bgcolor="white",
            plot_bgcolor="white",
            xaxis=dict(title="出現次數", color="#333"),
            yaxis=dict(autorange="reversed", tickfont=dict(size=11, color="#111")),
        )
        # Legend: 大類顏色說明
        used_parents = sorted({skill_to_parent.get(s,"") for s in skills_sorted if skill_to_parent.get(s,"")})
        legend_html = " ".join(
            f'<span style="display:inline-flex;align-items:center;gap:4px;margin:3px 6px 3px 0;">'
            f'<span style="width:12px;height:12px;border-radius:3px;background:{cat_color.get(p,"#888")};display:inline-block;"></span>'
            f'<span style="font-size:0.78rem;color:#333;">{p}</span></span>'
            for p in used_parents
        )
        st.markdown(legend_html, unsafe_allow_html=True)
        st.plotly_chart(fig, use_container_width=True)

    else:  # 依中類分組
        filter_sub_1 = st.selectbox("選擇中類", ["全部"] + sub_cats, key="t1_sub")
        grouped = defaultdict(list)
        for s, c in sc_all.items():
            sub = skill_to_sub.get(s, "其他")
            if filter_sub_1 != "全部" and sub != filter_sub_1:
                continue
            grouped[sub].append((s, c))

        for sub in sorted(grouped.keys()):
            items = sorted(grouped[sub], key=lambda x: x[1], reverse=True)[:top_n_1]
            if not items:
                continue
            st.markdown(f"**{sub}**")
            skills_s = [x[0] for x in items]
            counts_s = [x[1] for x in items]
            colors_s = [cat_color.get(skill_to_parent.get(s,""),"#888") for s in skills_s]
            fig_sub = go.Figure(go.Bar(
                x=counts_s, y=skills_s, orientation="h",
                marker_color=colors_s,
                text=counts_s, textposition="outside",
                textfont=dict(color="#0f0f0f", size=10),
            ))
            fig_sub.update_layout(
                height=max(200, len(items)*22),
                margin=dict(l=10, r=30, t=5, b=5),
                paper_bgcolor="white", plot_bgcolor="white",
                yaxis=dict(autorange="reversed", tickfont=dict(size=10, color="#111")),
                xaxis=dict(color="#333"),
                showlegend=False,
            )
            st.plotly_chart(fig_sub, use_container_width=True)


# ── Tab 2：產業 × 職能分析（frequency threshold + 橫條）──
with tab2:
    st.markdown('<div class="sec-title">選定產業 / 職能，查看技能需求分布</div>', unsafe_allow_html=True)

    f1, f2, f3 = st.columns(3)
    with f1: sel_ind2  = st.selectbox("產業", ["全部"] + industries_all, key="t2_ind")
    with f2: sel_role2 = st.selectbox("職能", ["全部"] + roles_all, key="t2_role")
    with f3: freq_thr  = st.slider("Frequency threshold", 0.0, 0.5, 0.05, 0.01, key="t2_thr",
                                    help="只顯示出現率 ≥ 此值的技能")

    top_n_2 = st.slider("Top N 技能", 10, 50, 20, 5, key="t2_topn")

    filt2 = rows
    if sel_ind2  != "全部": filt2 = [r for r in filt2 if r.get("industry_bucket") == sel_ind2]
    if sel_role2 != "全部": filt2 = [r for r in filt2 if r.get("role_normalized") == sel_role2]

    st.markdown(f"<p style='color:#888;font-size:0.82rem;'>符合職缺：{len(filt2)} 筆</p>", unsafe_allow_html=True)

    freq2 = skill_freq(filt2)
    freq2_filtered = {s: f for s, f in freq2.items() if f >= freq_thr}
    top2 = sorted(freq2_filtered.items(), key=lambda x: x[1], reverse=True)[:top_n_2]

    if top2:
        skills2 = [x[0] for x in top2]
        freqs2  = [round(x[1], 3) for x in top2]
        colors2 = [cat_color.get(skill_to_parent.get(s,""),"#888") for s in skills2]

        fig2 = go.Figure(go.Bar(
            x=freqs2, y=skills2, orientation="h",
            marker_color=colors2,
            text=[f"{f:.0%}" for f in freqs2],
            textposition="outside",
            textfont=dict(color="#0f0f0f", size=11),
        ))
        fig2.update_layout(
            height=max(350, len(top2)*24),
            margin=dict(l=10, r=50, t=10, b=10),
            paper_bgcolor="white", plot_bgcolor="white",
            xaxis=dict(title="Frequency（出現率）", tickformat=".0%", color="#333"),
            yaxis=dict(autorange="reversed", tickfont=dict(size=11, color="#111")),
        )
        # 大類 legend
        used2 = sorted({skill_to_parent.get(s,"") for s in skills2 if skill_to_parent.get(s,"")})
        leg2 = " ".join(
            f'<span style="display:inline-flex;align-items:center;gap:4px;margin:2px 6px 2px 0;">'
            f'<span style="width:10px;height:10px;border-radius:2px;background:{cat_color.get(p,"#888")};display:inline-block;"></span>'
            f'<span style="font-size:0.76rem;color:#333;">{p}</span></span>'
            for p in used2
        )
        st.markdown(leg2, unsafe_allow_html=True)
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("無符合 threshold 的技能，請降低 Frequency threshold")


# ── Tab 3：跨產業比較（dumbbell + unique skills）──────────
with tab3:
    st.markdown('<div class="sec-title">跨產業技能比較</div>', unsafe_allow_html=True)

    d1, d2, d3 = st.columns(3)
    with d1: ind_a = st.selectbox("產業 A", industries_all, key="t3_a")
    with d2:
        ind_b_opts = [i for i in industries_all if i != ind_a]
        ind_b = st.selectbox("產業 B", ind_b_opts, key="t3_b")
    with d3: role_filter3 = st.selectbox("職能（可選）", ["全部"] + roles_all, key="t3_role")

    top_n_3 = st.slider("Top N 共同技能", 10, 40, 20, 5, key="t3_topn")

    rows_a3 = [r for r in rows if r.get("industry_bucket") == ind_a]
    rows_b3 = [r for r in rows if r.get("industry_bucket") == ind_b]
    if role_filter3 != "全部":
        rows_a3 = [r for r in rows_a3 if r.get("role_normalized") == role_filter3]
        rows_b3 = [r for r in rows_b3 if r.get("role_normalized") == role_filter3]

    freq_a3 = skill_freq(rows_a3)
    freq_b3 = skill_freq(rows_b3)

    st.markdown(f"<p style='color:#888;font-size:0.82rem;'>{ind_a}：{len(rows_a3)} 筆 ｜ {ind_b}：{len(rows_b3)} 筆</p>", unsafe_allow_html=True)

    # 共同技能 dumbbell
    common_skills = set(freq_a3) & set(freq_b3)
    common_data = [(s, freq_a3[s], freq_b3[s]) for s in common_skills]
    common_data.sort(key=lambda x: x[1]+x[2], reverse=True)
    top_common = common_data[:top_n_3]

    if top_common:
        s_names = [x[0] for x in top_common]
        f_a     = [x[1] for x in top_common]
        f_b     = [x[2] for x in top_common]

        fig3 = go.Figure()
        # 連線
        for i, s in enumerate(s_names):
            fig3.add_trace(go.Scatter(
                x=[f_a[i], f_b[i]], y=[s, s],
                mode="lines",
                line=dict(color="#cbd5e1", width=2),
                showlegend=False, hoverinfo="skip",
            ))
        # 點 A
        fig3.add_trace(go.Scatter(
            x=f_a, y=s_names, mode="markers",
            marker=dict(color="#1a56db", size=10),
            name=ind_a,
        ))
        # 點 B
        fig3.add_trace(go.Scatter(
            x=f_b, y=s_names, mode="markers",
            marker=dict(color="#b45309", size=10),
            name=ind_b,
        ))
        fig3.update_layout(
            height=max(400, len(top_common)*22),
            margin=dict(l=10, r=20, t=30, b=10),
            paper_bgcolor="white", plot_bgcolor="white",
            xaxis=dict(title="Frequency", tickformat=".0%", color="#333"),
            yaxis=dict(autorange="reversed", tickfont=dict(size=11, color="#111")),
            legend=dict(orientation="h", y=1.04),
        )
        st.plotly_chart(fig3, use_container_width=True)
    else:
        st.info("兩個產業無共同技能")

    # Unique skills
    st.markdown("---")
    only_a = sorted(set(freq_a3) - set(freq_b3), key=lambda s: freq_a3[s], reverse=True)
    only_b = sorted(set(freq_b3) - set(freq_a3), key=lambda s: freq_b3[s], reverse=True)

    u1, u2 = st.columns(2)
    with u1:
        st.markdown(f"**{ind_a} only**")
        if only_a:
            df_oa = pd.DataFrame([{"Skill": s, "Frequency": f"{freq_a3[s]:.1%}", "Category": skill_to_parent.get(s,"")} for s in only_a[:20]])
            st.dataframe(df_oa, use_container_width=True, hide_index=True, height=350)
        else:
            st.info("無獨有技能")
    with u2:
        st.markdown(f"**{ind_b} only**")
        if only_b:
            df_ob = pd.DataFrame([{"Skill": s, "Frequency": f"{freq_b3[s]:.1%}", "Category": skill_to_parent.get(s,"")} for s in only_b[:20]])
            st.dataframe(df_ob, use_container_width=True, hide_index=True, height=350)
        else:
            st.info("無獨有技能")

    # Union skills table
    st.markdown("---")
    st.markdown("**共同技能完整表**")
    if common_data:
        df_common = pd.DataFrame([{
            "Skill": s,
            f"{ind_a} freq": f"{fa:.1%}",
            f"{ind_b} freq": f"{fb:.1%}",
            "Δ": f"{abs(fa-fb):.1%}",
            "Category": skill_to_parent.get(s,""),
        } for s, fa, fb in common_data])
        st.dataframe(df_common, use_container_width=True, hide_index=True, height=350)


# ── Tab 4：跨職能比較 ─────────────────────────────────────
with tab4:
    st.markdown('<div class="sec-title">雙職能技能比較</div>', unsafe_allow_html=True)

    r1c1, r1c2 = st.columns(2)
    with r1c1: role_x = st.selectbox("職能 A", roles_all, key="t4_a")
    with r1c2: role_y = st.selectbox("職能 B", [r for r in roles_all if r != role_x], key="t4_b")

    top_n_4 = st.slider("每側 Top N", 10, 30, 15, 5, key="t4_topn")

    rows_x = [r for r in rows if r.get("role_normalized") == role_x]
    rows_y = [r for r in rows if r.get("role_normalized") == role_y]
    freq_x = skill_freq(rows_x)
    freq_y = skill_freq(rows_y)

    st.markdown(f"<p style='color:#888;font-size:0.82rem;'>{role_x}：{len(rows_x)} 筆 ｜ {role_y}：{len(rows_y)} 筆</p>", unsafe_allow_html=True)

    m1, m2, m3 = st.columns(3)
    m1.metric("共同技能", len(set(freq_x) & set(freq_y)))
    m2.metric(f"{role_x} 獨有", len(set(freq_x) - set(freq_y)))
    m3.metric(f"{role_y} 獨有", len(set(freq_y) - set(freq_x)))

    # Dumbbell for roles
    common_r = set(freq_x) & set(freq_y)
    common_r_data = sorted([(s, freq_x[s], freq_y[s]) for s in common_r], key=lambda x: x[1]+x[2], reverse=True)[:top_n_4]

    if common_r_data:
        rn = [x[0] for x in common_r_data]
        rx = [x[1] for x in common_r_data]
        ry = [x[2] for x in common_r_data]

        fig4 = go.Figure()
        for i, s in enumerate(rn):
            fig4.add_trace(go.Scatter(
                x=[rx[i], ry[i]], y=[s, s], mode="lines",
                line=dict(color="#cbd5e1", width=2),
                showlegend=False, hoverinfo="skip",
            ))
        fig4.add_trace(go.Scatter(x=rx, y=rn, mode="markers",
            marker=dict(color="#1a56db", size=10), name=role_x))
        fig4.add_trace(go.Scatter(x=ry, y=rn, mode="markers",
            marker=dict(color="#b45309", size=10), name=role_y))
        fig4.update_layout(
            height=max(400, len(rn)*22),
            margin=dict(l=10, r=20, t=30, b=10),
            paper_bgcolor="white", plot_bgcolor="white",
            xaxis=dict(title="Frequency", tickformat=".0%", color="#333"),
            yaxis=dict(autorange="reversed", tickfont=dict(size=11, color="#111")),
            legend=dict(orientation="h", y=1.04),
        )
        st.plotly_chart(fig4, use_container_width=True)

    st.markdown("---")
    ox = sorted(set(freq_x)-set(freq_y), key=lambda s: freq_x[s], reverse=True)
    oy = sorted(set(freq_y)-set(freq_x), key=lambda s: freq_y[s], reverse=True)

    ux, uy = st.columns(2)
    with ux:
        st.markdown(f"**{role_x} only**")
        if ox:
            st.dataframe(pd.DataFrame([{"Skill":s,"Freq":f"{freq_x[s]:.1%}","Category":skill_to_parent.get(s,"")} for s in ox[:20]]),
                         use_container_width=True, hide_index=True, height=350)
    with uy:
        st.markdown(f"**{role_y} only**")
        if oy:
            st.dataframe(pd.DataFrame([{"Skill":s,"Freq":f"{freq_y[s]:.1%}","Category":skill_to_parent.get(s,"")} for s in oy[:20]]),
                         use_container_width=True, hide_index=True, height=350)
