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
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; background:#f9f8f6; }
h1,h2,h3 { font-family: 'Syne', sans-serif; font-weight: 800; color:#111; }
.sec-title {
    font-family:'Syne',sans-serif; font-weight:700; font-size:0.95rem;
    color:#111; border-bottom:2px solid #111; padding-bottom:5px; margin-bottom:1rem;
}
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

taxonomy     = load_taxonomy()
skill_to_parent = dict(zip(taxonomy["canonical_skill_name"], taxonomy["skill_parent_category"]))
skill_to_sub    = dict(zip(taxonomy["canonical_skill_name"], taxonomy["skill_sub_category"]))
parent_cats     = sorted(taxonomy["skill_parent_category"].unique())
sub_cats        = sorted(taxonomy["skill_sub_category"].unique())

# ── 配色：單一藍灰色系，深淺表示不同大類 ─────────────────
# 10 個可辨別但不刺眼的藍灰漸層色
PALETTE = [
    "#1e3a5f",  # 深海藍
    "#2563a8",  # 中藍
    "#3b82c4",  # 淺藍
    "#5b9bd5",  # 天藍
    "#7cb4e0",  # 霧藍
    "#2d4a3e",  # 深綠灰
    "#3d6b5e",  # 中綠灰
    "#5c8c7e",  # 淺綠灰
    "#6b5b4e",  # 深棕灰
    "#8c7b6e",  # 中棕灰
]
cat_color = {cat: PALETTE[i % len(PALETTE)] for i, cat in enumerate(parent_cats)}

# Plotly layout 共用設定（白底、黑字）
LAYOUT_BASE = dict(
    paper_bgcolor="white",
    plot_bgcolor="white",
    font=dict(family="DM Sans", color="#111"),
    margin=dict(l=10, r=50, t=20, b=10),
)

rows = load_postings()
roles_all      = sorted({r.get("role_normalized") for r in rows if r.get("role_normalized") and r.get("role_normalized") != "Unclassified"})
industries_all = sorted({r.get("industry_bucket") for r in rows if r.get("industry_bucket")})

role_parent_all = sorted({
    r.get("job_parent_category")
    for r in rows
    if r.get("job_parent_category")
})

industry_parent_all = sorted({
    r.get("industry_bucket")
    for r in rows
    if r.get("industry_bucket")
})

def get_role_subcategories(parent):
    return sorted({
        r.get("job_sub_category")
        for r in rows
        if r.get("job_parent_category") == parent and r.get("job_sub_category")
    })

def get_industry_subcategories(parent):
    return sorted({
        r.get("industry_raw")
        for r in rows
        if r.get("industry_bucket") == parent and r.get("industry_raw")
    })

def filter_by_role_parent_sub(data_rows, parent, sub):
    return [
        r for r in data_rows
        if (parent == "全部" or r.get("job_parent_category") == parent)
        and (sub == "全部" or r.get("job_sub_category") == sub)
    ]

def filter_by_industry_parent_sub(data_rows, parent, sub):
    return [
        r for r in data_rows
        if (parent == "全部" or r.get("industry_bucket") == parent)
        and (sub == "全部" or r.get("industry_raw") == sub)
    ]

def count_skills(job_rows):
    counter = defaultdict(int)
    for r in job_rows:
        for s in (r.get("skill_canonical") or []):
            counter[s] += 1
    return counter

def skill_freq(job_rows):
    n = len(job_rows)
    if not n: return {}
    cnt = count_skills(job_rows)
    return {s: c/n for s, c in cnt.items()}

def legend_html(skill_list):
    """產生大類顏色 legend"""
    used = sorted({skill_to_parent.get(s,"") for s in skill_list if skill_to_parent.get(s,"")})
    return " ".join(
        f'<span style="display:inline-flex;align-items:center;gap:4px;margin:2px 8px 2px 0;">'
        f'<span style="width:10px;height:10px;border-radius:2px;'
        f'background:{cat_color.get(p,"#888")};display:inline-block;"></span>'
        f'<span style="font-size:0.76rem;color:#444;">{p}</span></span>'
        for p in used
    )

def bar_chart(skills, values, colors, x_title="", height=None, text_vals=None):
    fig = go.Figure(go.Bar(
        x=values, y=skills, orientation="h",
        marker_color=colors,
        text=text_vals if text_vals else values,
        textposition="outside",
        textfont=dict(color="#111", size=11),
        marker_line_width=0,
    ))
    fig.update_layout(
        **LAYOUT_BASE,
        height=height or max(380, len(skills)*22),
        xaxis=dict(title=x_title, color="#555", showgrid=True, gridcolor="#f0ede8"),
        yaxis=dict(autorange="reversed", tickfont=dict(size=11, color="#111"),
                   showgrid=False),
    )
    return fig

# ══ Tabs ══════════════════════════════════════════════════
tab1, tab2, tab3, tab4 = st.tabs([
    "🔥 技能熱度",
    "🏭 產業 × 職能分析",
    "⚖️ 跨產業比較",
    "🔬 跨職能比較",
])

# ── Tab 1 ─────────────────────────────────────────────────
with tab1:
    st.markdown('<div class="sec-title">全市場技能需求</div>', unsafe_allow_html=True)

    ctrl = st.columns([2, 1])
    with ctrl[0]: view_mode = st.radio("排序維度", ["跨組統一排序", "依中類分組"], horizontal=True, key="t1_view")
    with ctrl[1]: top_n_1  = st.slider("Top N", 10, 60, 30, 5, key="t1_topn")

    fp1 = st.multiselect("只看特定大類", parent_cats, default=[], key="t1_fp")
    sc_all = count_skills(rows)
    if fp1:
        sc_all = {s: c for s, c in sc_all.items() if skill_to_parent.get(s) in fp1}

    if view_mode == "跨組統一排序":
        top_items = sorted(sc_all.items(), key=lambda x: x[1], reverse=True)[:top_n_1]
        sk = [x[0] for x in top_items]
        vl = [x[1] for x in top_items]
        cl = [cat_color.get(skill_to_parent.get(s,""), "#888") for s in sk]
        st.markdown(legend_html(sk), unsafe_allow_html=True)
        st.plotly_chart(bar_chart(sk, vl, cl, x_title="出現次數"), use_container_width=True)

    else:
        fs1 = st.selectbox("選擇中類", ["全部"] + sub_cats, key="t1_sub")
        grouped = defaultdict(list)
        for s, c in sc_all.items():
            sub = skill_to_sub.get(s, "其他")
            if fs1 != "全部" and sub != fs1: continue
            grouped[sub].append((s, c))

        for sub in sorted(grouped.keys()):
            items = sorted(grouped[sub], key=lambda x: x[1], reverse=True)[:top_n_1]
            if not items: continue
            st.markdown(f"**{sub}**")
            sk = [x[0] for x in items]; vl = [x[1] for x in items]
            cl = [cat_color.get(skill_to_parent.get(s,""),"#888") for s in sk]
            st.plotly_chart(bar_chart(sk, vl, cl, x_title="出現次數", height=max(200, len(sk)*20)), use_container_width=True)

# ── Tab 2 ─────────────────────────────────────────────────
with tab2:
    st.markdown(
        '<div class="sec-title">選定產業 / 職能，查看技能需求分布</div>',
        unsafe_allow_html=True
    )

    f1, f2, f3, f4 = st.columns(4)

    with f1:
        si2 = st.selectbox("產業", ["全部"] + industries_all, key="t2_ind")

    with f2:
        role_parent_2 = st.selectbox(
            "職能大類",
            ["全部"] + role_parent_all,
            key="t2_role_parent"
        )

    with f3:
        role_sub_options_2 = (
            ["全部"]
            if role_parent_2 == "全部"
            else ["全部"] + get_role_subcategories(role_parent_2)
        )
        role_sub_2 = st.selectbox(
            "職能中類",
            role_sub_options_2,
            key="t2_role_sub",
            disabled=(role_parent_2 == "全部")
        )

    with f4:
        thr = st.slider("Frequency threshold", 0.0, 0.5, 0.05, 0.01, key="t2_thr")

    tn2 = st.slider("Top N 技能", 10, 50, 20, 5, key="t2_topn")

    f2r = [
        r for r in rows
        if (si2 == "全部" or r.get("industry_bucket") == si2)
        and (role_parent_2 == "全部" or r.get("job_parent_category") == role_parent_2)
        and (role_sub_2 == "全部" or r.get("job_sub_category") == role_sub_2)
    ]

    st.caption(f"符合職缺：{len(f2r)} 筆")

    freq2 = {s: f for s, f in skill_freq(f2r).items() if f >= thr}
    top2 = sorted(freq2.items(), key=lambda x: x[1], reverse=True)[:tn2]

    if top2:
        sk2 = [x[0] for x in top2]
        vl2 = [round(x[1], 3) for x in top2]
        cl2 = [cat_color.get(skill_to_parent.get(s, ""), "#888") for s in sk2]

        st.markdown(legend_html(sk2), unsafe_allow_html=True)
        st.plotly_chart(
            bar_chart(
                sk2,
                vl2,
                cl2,
                x_title="Frequency（出現率）",
                text_vals=[f"{v:.0%}" for v in vl2]
            ),
            use_container_width=True,
        )
    else:
        st.info("無符合 threshold 的技能，請降低 Frequency threshold")

# ── Tab 3 ─────────────────────────────────────────────────
with tab3:
    st.markdown('<div class="sec-title">跨產業技能比較</div>', unsafe_allow_html=True)

    r1, r2 = st.columns(2)
    with r1:
        role_parent_3 = st.selectbox("職能大類", ["全部"] + role_parent_all, key="t3_role_parent")
    with r2:
        role_sub_options_3 = ["全部"] if role_parent_3 == "全部" else ["全部"] + get_role_subcategories(role_parent_3)
        role_sub_3 = st.selectbox("職能中類", role_sub_options_3, key="t3_role_sub", disabled=(role_parent_3 == "全部"))

    d1, d2, d3, d4 = st.columns(4)
    with d1:
        ind_parent_a = st.selectbox("產業 A（大類）", ["全部"] + industry_parent_all, key="t3_ind_parent_a")
    with d2:
        ind_sub_options_a = ["全部"]
        ia = st.selectbox("產業 A（子類）", ind_sub_options_a, key="t3_a")
    with d3:
        ind_parent_b = st.selectbox("產業 B（大類）", ["全部"] + industry_parent_all, key="t3_ind_parent_b")
    with d4:
        ind_sub_options_b = ["全部"]
        ib = st.selectbox("產業 B（子類）", ind_sub_options_b, key="t3_b")
    tn3 = st.slider("Top N 共同技能", 10, 40, 20, 5, key="t3_topn")

    def filter_rows(ind, role_parent, role_sub):
        return [r for r in rows
                if (ind == "全部" or r.get("industry_bucket") == ind)
                and (role_parent == "全部" or r.get("job_parent_category") == role_parent)
                and (role_sub == "全部" or r.get("job_sub_category") == role_sub)]

    ra3 = filter_rows(ia, role_parent_3, role_sub_3); rb3 = filter_rows(ib, role_parent_3, role_sub_3)
    fa3 = skill_freq(ra3);      fb3 = skill_freq(rb3)
    st.caption(f"{ia}：{len(ra3)} 筆 ｜ {ib}：{len(rb3)} 筆")

    # Dumbbell
    common = set(fa3) & set(fb3)
    c_data = sorted([(s, fa3[s], fb3[s]) for s in common], key=lambda x: x[1]+x[2], reverse=True)[:tn3]

    if c_data:
        sn = [x[0] for x in c_data]; fx = [x[1] for x in c_data]; fy = [x[2] for x in c_data]
        fig3 = go.Figure()
        for i in range(len(sn)):
            fig3.add_trace(go.Scatter(
                x=[fx[i], fy[i]], y=[sn[i], sn[i]], mode="lines",
                line=dict(color="#d1d5db", width=2), showlegend=False, hoverinfo="skip",
            ))
        fig3.add_trace(go.Scatter(x=fx, y=sn, mode="markers",
            marker=dict(color="#1e3a5f", size=11), name=ia))
        fig3.add_trace(go.Scatter(x=fy, y=sn, mode="markers",
            marker=dict(color="#6b5b4e", size=11), name=ib))
        fig3.update_layout(
            **LAYOUT_BASE,
            height=max(400, len(sn)*22),
            xaxis=dict(title="Frequency", tickformat=".0%", color="#555",
                       showgrid=True, gridcolor="#f0ede8"),
            yaxis=dict(autorange="reversed", tickfont=dict(size=11, color="#111"), showgrid=False),
            legend=dict(orientation="h", y=1.06, font=dict(size=12)),
        )
        st.plotly_chart(fig3, use_container_width=True)
    else:
        st.info("兩個產業無共同技能")

    # Unique skills
    st.markdown("---")
    oa = sorted(set(fa3)-set(fb3), key=lambda s: fa3[s], reverse=True)
    ob = sorted(set(fb3)-set(fa3), key=lambda s: fb3[s], reverse=True)
    u1, u2 = st.columns(2)
    with u1:
        st.markdown(f"**{ia} only**")
        if oa:
            st.dataframe(pd.DataFrame([{"Skill":s,"Freq":f"{fa3[s]:.1%}","Category":skill_to_parent.get(s,"")} for s in oa[:20]]),
                use_container_width=True, hide_index=True, height=350)
        else: st.info("無獨有技能")
    with u2:
        st.markdown(f"**{ib} only**")
        if ob:
            st.dataframe(pd.DataFrame([{"Skill":s,"Freq":f"{fb3[s]:.1%}","Category":skill_to_parent.get(s,"")} for s in ob[:20]]),
                use_container_width=True, hide_index=True, height=350)
        else: st.info("無獨有技能")

    if c_data:
        st.markdown("---")
        st.markdown("**共同技能完整表**")
        st.dataframe(pd.DataFrame([{
            "Skill":s, f"{ia} freq":f"{fa:.1%}", f"{ib} freq":f"{fb:.1%}",
            "Δ":f"{abs(fa-fb):.1%}", "Category":skill_to_parent.get(s,""),
        } for s, fa, fb in sorted([(s,fa3[s],fb3[s]) for s in common], key=lambda x: x[1]+x[2], reverse=True)]),
        use_container_width=True, hide_index=True, height=350)

# ── Tab 4 ─────────────────────────────────────────────────
with tab4:
    st.markdown('<div class="sec-title">雙職能技能比較</div>', unsafe_allow_html=True)

    r1, r2, r3, r4 = st.columns(4)
    with r1:
        role_parent_a = st.selectbox("職能 A 大類", ["全部"] + role_parent_all, key="t4_role_parent_a")
    with r2:
        role_sub_options_a = ["全部"] if role_parent_a == "全部" else ["全部"] + get_role_subcategories(role_parent_a)
        role_sub_a = st.selectbox("職能 A 中類", role_sub_options_a, key="t4_role_sub_a", disabled=(role_parent_a == "全部"))
    with r3:
        role_parent_b = st.selectbox("職能 B 大類", ["全部"] + role_parent_all, key="t4_role_parent_b")
    with r4:
        role_sub_options_b = ["全部"] if role_parent_b == "全部" else ["全部"] + get_role_subcategories(role_parent_b)
        role_sub_b = st.selectbox("職能 B 中類", role_sub_options_b, key="t4_role_sub_b", disabled=(role_parent_b == "全部"))
    tn4 = st.slider("每側 Top N", 10, 30, 15, 5, key="t4_topn")

    rrx = filter_by_role_parent_sub(rows, role_parent_a, role_sub_a)
    rry = filter_by_role_parent_sub(rows, role_parent_b, role_sub_b)
    frx = skill_freq(rrx); fry = skill_freq(rry)
    rx = f"{role_parent_a} / {role_sub_a}"
    ry = f"{role_parent_b} / {role_sub_b}"
    st.caption(f"{rx}：{len(rrx)} 筆 ｜ {ry}：{len(rry)} 筆")

    m1, m2, m3 = st.columns(3)
    m1.metric("共同技能", len(set(frx)&set(fry)))
    m2.metric(f"{rx} 獨有", len(set(frx)-set(fry)))
    m3.metric(f"{ry} 獨有", len(set(fry)-set(frx)))

    cr = set(frx)&set(fry)
    cr_data = sorted([(s,frx[s],fry[s]) for s in cr], key=lambda x: x[1]+x[2], reverse=True)[:tn4]

    if cr_data:
        rn=[x[0] for x in cr_data]; vx=[x[1] for x in cr_data]; vy=[x[2] for x in cr_data]
        fig4 = go.Figure()
        for i in range(len(rn)):
            fig4.add_trace(go.Scatter(x=[vx[i],vy[i]], y=[rn[i],rn[i]], mode="lines",
                line=dict(color="#d1d5db",width=2), showlegend=False, hoverinfo="skip"))
        fig4.add_trace(go.Scatter(x=vx, y=rn, mode="markers",
            marker=dict(color="#1e3a5f",size=11), name=rx))
        fig4.add_trace(go.Scatter(x=vy, y=rn, mode="markers",
            marker=dict(color="#6b5b4e",size=11), name=ry))
        fig4.update_layout(
            **LAYOUT_BASE,
            height=max(400, len(rn)*22),
            xaxis=dict(title="Frequency", tickformat=".0%", color="#555",
                       showgrid=True, gridcolor="#f0ede8"),
            yaxis=dict(autorange="reversed", tickfont=dict(size=11, color="#111"), showgrid=False),
            legend=dict(orientation="h", y=1.06, font=dict(size=12)),
        )
        st.plotly_chart(fig4, use_container_width=True)

    st.markdown("---")
    ox = sorted(set(frx)-set(fry), key=lambda s: frx[s], reverse=True)
    oy = sorted(set(fry)-set(frx), key=lambda s: fry[s], reverse=True)
    ux, uy = st.columns(2)
    with ux:
        st.markdown(f"**{rx} only**")
        if ox:
            st.dataframe(pd.DataFrame([{"Skill":s,"Freq":f"{frx[s]:.1%}","Category":skill_to_parent.get(s,"")} for s in ox[:20]]),
                use_container_width=True, hide_index=True, height=350)
    with uy:
        st.markdown(f"**{ry} only**")
        if oy:
            st.dataframe(pd.DataFrame([{"Skill":s,"Freq":f"{fry[s]:.1%}","Category":skill_to_parent.get(s,"")} for s in oy[:20]]),
                use_container_width=True, hide_index=True, height=350)
