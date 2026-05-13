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

from utils.ui_taxonomy import (
    build_skill_parent_colors, ensure_valid_state,
    get_industry_parents, get_industry_subs,
    get_role_parents, get_role_subs,
    filter_rows as ut_filter_rows,
    format_industry_label, format_role_label,
    filter_label, FILTER_STYLE,
)

st.set_page_config(page_title="Skill Dashboard | Career Overfitter", layout="wide")

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@300;400;500&display=swap');
html, body, [class*="css"] {{ font-family: 'DM Sans', sans-serif; background:#f9f8f6; }}
h1,h2,h3 {{ font-family: 'Syne', sans-serif; font-weight: 800; color:#111; }}
.sec-title {{
    font-family:'Syne',sans-serif; font-weight:700; font-size:0.95rem;
    color:#111; border-bottom:2px solid #111; padding-bottom:5px; margin-bottom:1rem;
}}
{FILTER_STYLE}
</style>
""", unsafe_allow_html=True)

st.markdown("<h1 style='margin-bottom:4px'>📊 Skill Dashboard</h1>", unsafe_allow_html=True)
st.markdown("<p style='color:#888;margin-top:0'>市場技能需求分析</p>", unsafe_allow_html=True)
st.markdown("---")


@st.cache_data(ttl=600)
def load_taxonomy():
    path = ROOT / "skill_taxonomy.csv"
    if not path.exists():
        return pd.DataFrame(columns=["skill_parent_category", "skill_sub_category", "canonical_skill_name"])
    return pd.read_csv(path, encoding="utf-8-sig").fillna("")


@st.cache_data(ttl=300)
def load_postings():
    from utils.supabase_client import _get
    return _get("job_posting", {
        "select": (
            "role_normalized,job_parent_category,job_sub_category,"
            "industry_bucket,industry_raw,skill_canonical"
        ),
        "limit": 5000,
    })


taxonomy = load_taxonomy()
rows = load_postings()

skill_to_parent = dict(zip(taxonomy["canonical_skill_name"], taxonomy["skill_parent_category"]))
skill_to_sub    = dict(zip(taxonomy["canonical_skill_name"], taxonomy["skill_sub_category"]))
parent_cats     = sorted(x for x in taxonomy["skill_parent_category"].unique() if x)
SKILL_PARENT_COLORS = build_skill_parent_colors(parent_cats)

LAYOUT_BASE = dict(
    paper_bgcolor="white", plot_bgcolor="white",
    font=dict(family="DM Sans", color="#111"),
    margin=dict(l=10, r=50, t=20, b=10),
)

role_parent_all    = sorted({r.get("job_parent_category") for r in rows if r.get("job_parent_category")})
industry_parent_all = sorted({r.get("industry_bucket") for r in rows if r.get("industry_bucket")})


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


def legend_html(skill_list):
    used = sorted({skill_to_parent.get(s, "") for s in skill_list if skill_to_parent.get(s, "")})
    return " ".join(
        f'<span style="display:inline-flex;align-items:center;gap:4px;margin:2px 8px 2px 0;">'
        f'<span style="width:10px;height:10px;border-radius:2px;'
        f'background:{SKILL_PARENT_COLORS.get(p,"#888")};display:inline-block;"></span>'
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
        height=height or max(380, len(skills) * 22),
        xaxis=dict(title=x_title, color="#555", showgrid=True, gridcolor="#f0ede8"),
        yaxis=dict(autorange="reversed", tickfont=dict(size=11, color="#111"), showgrid=False),
    )
    return fig


def build_skill_comparison_df(frx, fry, rx, ry, skills):
    return pd.DataFrame([{
        "Sub Skill": skill_to_sub.get(s, "其他"),
        "Skill": s,
        f"{rx} freq": f"{frx.get(s, 0):.1%}",
        f"{ry} freq": f"{fry.get(s, 0):.1%}",
        "Δ": f"{abs(frx.get(s, 0) - fry.get(s, 0)):.1%}",
        "Parent Category": skill_to_parent.get(s, ""),
    } for s in skills])


def build_subskill_summary_df(frx, fry, skills, rx, ry):
    agg_x = defaultdict(list)
    agg_y = defaultdict(list)
    for s in skills:
        sub = skill_to_sub.get(s, "其他")
        agg_x[sub].append(frx.get(s, 0))
        agg_y[sub].append(fry.get(s, 0))
    out = []
    for sub in sorted(set(agg_x) | set(agg_y)):
        vx = sum(agg_x[sub]) / len(agg_x[sub]) if agg_x[sub] else 0
        vy = sum(agg_y[sub]) / len(agg_y[sub]) if agg_y[sub] else 0
        out.append({
            "Sub Skill": sub,
            f"{rx} avg freq": f"{vx:.1%}",
            f"{ry} avg freq": f"{vy:.1%}",
            "Δ": f"{abs(vx - vy):.1%}",
            "Skill Count": len(agg_x.get(sub, []) or agg_y.get(sub, [])),
        })
    return pd.DataFrame(out).sort_values("Skill Count", ascending=False)


# ── Industry / Role selector widget (reusable) ───────────
def industry_selectors(key_prefix, rows_src, first=True):
    st.markdown(filter_label("🏭 選擇產業", first=first), unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        ind_par = st.selectbox("產業大類", ["全部"] + get_industry_parents(rows_src),
                               key=f"{key_prefix}_ind_par")
    with c2:
        ind_sub_opts = ["全部"] + (get_industry_subs(rows_src, ind_par) if ind_par != "全部" else [])
        ensure_valid_state(st, f"{key_prefix}_ind_sub", ind_sub_opts)
        ind_sub = st.selectbox("產業別", ind_sub_opts,
                               key=f"{key_prefix}_ind_sub", disabled=(ind_par == "全部"))
    return ind_par, ind_sub


def role_selectors(key_prefix, rows_src, industry_parent="全部", industry_sub="全部", first=False):
    st.markdown(filter_label("🎯 選擇職能", first=first), unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        role_par_opts = ["全部"] + get_role_parents(rows_src, industry_parent=industry_parent, industry_sub=industry_sub)
        ensure_valid_state(st, f"{key_prefix}_role_par", role_par_opts)
        role_par = st.selectbox("職能大類", role_par_opts, key=f"{key_prefix}_role_par")
    with c2:
        role_sub_opts = ["全部"] + (get_role_subs(rows_src, role_par, industry_parent=industry_parent, industry_sub=industry_sub)
                                    if role_par != "全部" else [])
        ensure_valid_state(st, f"{key_prefix}_role_sub", role_sub_opts)
        role_sub = st.selectbox("職能中類", role_sub_opts, key=f"{key_prefix}_role_sub",
                                disabled=(role_par == "全部"))
    return role_par, role_sub


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
    with ctrl[0]:
        fp1 = st.multiselect("只看特定技能大類", parent_cats, default=[], key="t1_fp")
    with ctrl[1]:
        top_n_1 = st.slider("Top N", 10, 60, 30, 5, key="t1_topn")

    sc_all = count_skills(rows)
    if fp1:
        sc_all = {s: c for s, c in sc_all.items() if skill_to_parent.get(s) in fp1}
    top_items = sorted(sc_all.items(), key=lambda x: x[1], reverse=True)[:top_n_1]
    sk = [x[0] for x in top_items]
    vl = [x[1] for x in top_items]
    cl = [SKILL_PARENT_COLORS.get(skill_to_parent.get(s, ""), "#888") for s in sk]
    st.markdown(legend_html(sk), unsafe_allow_html=True)
    st.plotly_chart(bar_chart(sk, vl, cl, x_title="出現次數"), use_container_width=True)

# ── Tab 2 ─────────────────────────────────────────────────
with tab2:
    st.markdown('<div class="sec-title">選定產業 / 職能，查看技能需求分布</div>', unsafe_allow_html=True)
    ind_par2, ind_sub2 = industry_selectors("t2", rows, first=True)
    role_par2, role_sub2 = role_selectors("t2", rows, industry_parent=ind_par2, industry_sub=ind_sub2)

    thr = st.slider("Frequency threshold", 0.0, 0.5, 0.05, 0.01, key="t2_thr")
    tn2 = st.slider("Top N 技能", 10, 50, 20, 5, key="t2_topn")

    f2r = ut_filter_rows(rows, industry_parent=ind_par2, industry_sub=ind_sub2,
                         role_parent=role_par2, role_sub=role_sub2)
    st.caption(
        f"產業：{format_industry_label(ind_par2, ind_sub2)} ｜"
        f" 職能：{format_role_label(role_par2, role_sub2)} ｜ 符合職缺：{len(f2r)} 筆"
    )

    freq2 = {s: f for s, f in skill_freq(f2r).items() if f >= thr}
    top2  = sorted(freq2.items(), key=lambda x: x[1], reverse=True)[:tn2]
    if top2:
        sk2 = [x[0] for x in top2]
        vl2 = [round(x[1], 3) for x in top2]
        cl2 = [SKILL_PARENT_COLORS.get(skill_to_parent.get(s, ""), "#888") for s in sk2]
        st.markdown(legend_html(sk2), unsafe_allow_html=True)
        st.plotly_chart(
            bar_chart(sk2, vl2, cl2, x_title="Frequency（出現率）", text_vals=[f"{v:.0%}" for v in vl2]),
            use_container_width=True,
        )
    else:
        st.info("無符合條件的技能，請放寬篩選或降低 Frequency threshold")

# ── Tab 3 ─────────────────────────────────────────────────
with tab3:
    st.markdown('<div class="sec-title">跨產業技能比較</div>', unsafe_allow_html=True)
    role_par3, role_sub3 = role_selectors("t3", rows, first=True)

    st.markdown(filter_label("🏭 選擇比較產業"), unsafe_allow_html=True)
    avail_ind3 = ["全部"] + get_industry_parents(rows, role_parent=role_par3, role_sub=role_sub3)
    ensure_valid_state(st, "t3_ind_par_a", avail_ind3)
    ensure_valid_state(st, "t3_ind_par_b", avail_ind3)

    d1, d2, d3, d4 = st.columns(4)
    with d1:
        ind_par_a = st.selectbox("產業 A（大類）", avail_ind3, key="t3_ind_par_a")
    ind_sub_a_opts = ["全部"] + (get_industry_subs(rows, ind_par_a, role_parent=role_par3, role_sub=role_sub3)
                                 if ind_par_a != "全部" else [])
    ensure_valid_state(st, "t3_ind_sub_a", ind_sub_a_opts)
    with d2:
        ind_sub_a = st.selectbox("產業 A（產業別）", ind_sub_a_opts,
                                 key="t3_ind_sub_a", disabled=(ind_par_a == "全部"))
    with d3:
        ind_par_b = st.selectbox("產業 B（大類）", avail_ind3, key="t3_ind_par_b")
    ind_sub_b_opts = ["全部"] + (get_industry_subs(rows, ind_par_b, role_parent=role_par3, role_sub=role_sub3)
                                 if ind_par_b != "全部" else [])
    ensure_valid_state(st, "t3_ind_sub_b", ind_sub_b_opts)
    with d4:
        ind_sub_b = st.selectbox("產業 B（產業別）", ind_sub_b_opts,
                                 key="t3_ind_sub_b", disabled=(ind_par_b == "全部"))

    tn3 = st.slider("Top N 共同技能", 10, 40, 20, 5, key="t3_topn")
    ra3 = ut_filter_rows(rows, industry_parent=ind_par_a, industry_sub=ind_sub_a,
                         role_parent=role_par3, role_sub=role_sub3)
    rb3 = ut_filter_rows(rows, industry_parent=ind_par_b, industry_sub=ind_sub_b,
                         role_parent=role_par3, role_sub=role_sub3)
    fa3 = skill_freq(ra3)
    fb3 = skill_freq(rb3)
    label_a = format_industry_label(ind_par_a, ind_sub_a)
    label_b = format_industry_label(ind_par_b, ind_sub_b)
    st.caption(f"{label_a}：{len(ra3)} 筆 ｜ {label_b}：{len(rb3)} 筆")

    common = set(fa3) & set(fb3)
    c_data = sorted([(s, fa3[s], fb3[s]) for s in common], key=lambda x: x[1] + x[2], reverse=True)[:tn3]

    if c_data:
        sn = [x[0] for x in c_data]; fx = [x[1] for x in c_data]; fy = [x[2] for x in c_data]
        fig3 = go.Figure()
        for i in range(len(sn)):
            fig3.add_trace(go.Scatter(x=[fx[i], fy[i]], y=[sn[i], sn[i]], mode="lines",
                                      line=dict(color="#d1d5db", width=2), showlegend=False, hoverinfo="skip"))
        fig3.add_trace(go.Scatter(x=fx, y=sn, mode="markers", marker=dict(color="#1e3a5f", size=11), name=label_a))
        fig3.add_trace(go.Scatter(x=fy, y=sn, mode="markers", marker=dict(color="#6b5b4e", size=11), name=label_b))
        fig3.update_layout(
            **LAYOUT_BASE, height=max(400, len(sn) * 22),
            xaxis=dict(title="Frequency", tickformat=".0%", color="#555", showgrid=True, gridcolor="#f0ede8"),
            yaxis=dict(autorange="reversed", tickfont=dict(size=11, color="#111"), showgrid=False),
            legend=dict(orientation="h", y=1.06, font=dict(size=12)),
        )
        st.plotly_chart(fig3, use_container_width=True)
    else:
        st.info("兩個產業無共同技能")

    st.markdown("---")
    oa = sorted(set(fa3) - set(fb3), key=lambda s: fa3[s], reverse=True)
    ob = sorted(set(fb3) - set(fa3), key=lambda s: fb3[s], reverse=True)
    u1, u2 = st.columns(2)
    with u1:
        st.markdown(f"**{label_a} only**")
        if oa:
            st.dataframe(pd.DataFrame([{"Skill": s, "Freq": f"{fa3[s]:.1%}", "Category": skill_to_parent.get(s, "")} for s in oa[:20]]),
                         use_container_width=True, hide_index=True, height=350)
        else:
            st.info("無獨有技能")
    with u2:
        st.markdown(f"**{label_b} only**")
        if ob:
            st.dataframe(pd.DataFrame([{"Skill": s, "Freq": f"{fb3[s]:.1%}", "Category": skill_to_parent.get(s, "")} for s in ob[:20]]),
                         use_container_width=True, hide_index=True, height=350)
        else:
            st.info("無獨有技能")

    if c_data:
        st.markdown("---")
        st.markdown("**共同技能完整表**")
        st.dataframe(pd.DataFrame([{
            "Skill": s, f"{label_a} freq": f"{fa:.1%}", f"{label_b} freq": f"{fb:.1%}",
            "Δ": f"{abs(fa - fb):.1%}", "Category": skill_to_parent.get(s, ""),
        } for s, fa, fb in sorted([(s, fa3[s], fb3[s]) for s in common], key=lambda x: x[1]+x[2], reverse=True)]),
            use_container_width=True, hide_index=True, height=350)

# ── Tab 4 ─────────────────────────────────────────────────
with tab4:
    st.markdown('<div class="sec-title">雙職能技能比較</div>', unsafe_allow_html=True)
    r1c, r2c, r3c, r4c = st.columns(4)
    with r1c:
        role_par_a = st.selectbox("職能 A 大類", ["全部"] + role_parent_all, key="t4_rpa")
    with r2c:
        rsa_opts = ["全部"] + (get_role_subs(rows, role_par_a) if role_par_a != "全部" else [])
        ensure_valid_state(st, "t4_rsa", rsa_opts)
        role_sub_a = st.selectbox("職能 A 中類", rsa_opts, key="t4_rsa", disabled=(role_par_a == "全部"))
    with r3c:
        role_par_b = st.selectbox("職能 B 大類", ["全部"] + role_parent_all, key="t4_rpb")
    with r4c:
        rsb_opts = ["全部"] + (get_role_subs(rows, role_par_b) if role_par_b != "全部" else [])
        ensure_valid_state(st, "t4_rsb", rsb_opts)
        role_sub_b = st.selectbox("職能 B 中類", rsb_opts, key="t4_rsb", disabled=(role_par_b == "全部"))
    tn4 = st.slider("每側 Top N", 10, 30, 15, 5, key="t4_topn")

    rrx = ut_filter_rows(rows, role_parent=role_par_a, role_sub=role_sub_a)
    rry = ut_filter_rows(rows, role_parent=role_par_b, role_sub=role_sub_b)
    frx = skill_freq(rrx); fry = skill_freq(rry)
    rx = format_role_label(role_par_a, role_sub_a)
    ry = format_role_label(role_par_b, role_sub_b)
    st.caption(f"{rx}：{len(rrx)} 筆 ｜ {ry}：{len(rry)} 筆")

    m1, m2, m3 = st.columns(3)
    m1.metric("共同技能", len(set(frx) & set(fry)))
    m2.metric(f"{rx} 獨有", len(set(frx) - set(fry)))
    m3.metric(f"{ry} 獨有", len(set(fry) - set(frx)))

    cr = set(frx) & set(fry)
    cr_data = sorted([(s, frx[s], fry[s]) for s in cr], key=lambda x: x[1] + x[2], reverse=True)[:tn4]
    if cr_data:
        rn = [x[0] for x in cr_data]; vx = [x[1] for x in cr_data]; vy = [x[2] for x in cr_data]
        fig4 = go.Figure()
        for i in range(len(rn)):
            fig4.add_trace(go.Scatter(x=[vx[i], vy[i]], y=[rn[i], rn[i]], mode="lines",
                                      line=dict(color="#d1d5db", width=2), showlegend=False, hoverinfo="skip"))
        fig4.add_trace(go.Scatter(x=vx, y=rn, mode="markers", marker=dict(color="#1e3a5f", size=11), name=rx))
        fig4.add_trace(go.Scatter(x=vy, y=rn, mode="markers", marker=dict(color="#6b5b4e", size=11), name=ry))
        fig4.update_layout(
            **LAYOUT_BASE, height=max(400, len(rn) * 22),
            xaxis=dict(title="Frequency", tickformat=".0%", color="#555", showgrid=True, gridcolor="#f0ede8"),
            yaxis=dict(autorange="reversed", tickfont=dict(size=11, color="#111"), showgrid=False),
            legend=dict(orientation="h", y=1.06, font=dict(size=12)),
        )
        st.plotly_chart(fig4, use_container_width=True)

        st.markdown("---")
        st.markdown("**Skill 表**（左欄顯示所屬 Sub Skill）")
        st.dataframe(build_skill_comparison_df(frx, fry, rx, ry, rn),
                     use_container_width=True, hide_index=True, height=360)
        st.markdown("**Sub Skill 彙總表**")
        st.dataframe(build_subskill_summary_df(frx, fry, rn, rx, ry),
                     use_container_width=True, hide_index=True, height=320)

    st.markdown("---")
    ox = sorted(set(frx) - set(fry), key=lambda s: frx[s], reverse=True)
    oy = sorted(set(fry) - set(frx), key=lambda s: fry[s], reverse=True)
    ux, uy = st.columns(2)
    with ux:
        st.markdown(f"**{rx} only**")
        if ox:
            st.dataframe(pd.DataFrame([{
                "Sub Skill": skill_to_sub.get(s, "其他"), "Skill": s,
                "Freq": f"{frx[s]:.1%}", "Category": skill_to_parent.get(s, "")} for s in ox[:20]]),
                use_container_width=True, hide_index=True, height=350)
        else:
            st.info("無獨有技能")
    with uy:
        st.markdown(f"**{ry} only**")
        if oy:
            st.dataframe(pd.DataFrame([{
                "Sub Skill": skill_to_sub.get(s, "其他"), "Skill": s,
                "Freq": f"{fry[s]:.1%}", "Category": skill_to_parent.get(s, "")} for s in oy[:20]]),
                use_container_width=True, hide_index=True, height=350)
        else:
            st.info("無獨有技能")
