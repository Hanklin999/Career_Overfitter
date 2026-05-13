#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Page 3 — CV Fitting Tool (optimized + weighted skill evidence)"""

import sys
import json
from pathlib import Path
from collections import defaultdict

sys.path.append(str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

ROOT = Path(__file__).resolve().parent.parent

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
html, body, [class*="css"] {{ font-family: 'DM Sans', sans-serif; background:#f9f8f6; }}
h1,h2,h3 {{ font-family: 'Syne', sans-serif; font-weight: 800; }}
.fit-card {{ border:1px solid #e0ddd7; border-radius:10px; padding:1.1rem 1.25rem; margin-bottom:0.8rem; background:#fff; }}
.fit-role {{ font-family:'Syne',sans-serif; font-weight:700; font-size:1.02rem; }}
.tag {{ display:inline-block; border-radius:20px; padding:2px 10px; font-size:0.75rem; margin:2px; }}
.tag-match {{ background:#e8f0fe; border:1px solid #c5d8fd; color:#1a56db; }}
.tag-gap   {{ background:#fef2f2; border:1px solid #fecaca; color:#dc2626; }}
.tag-skill {{ background:#f0fdf4; border:1px solid #bbf7d0; color:#15803d; }}
.metric-card {{ border:1px solid #e5e2db; border-radius:10px; padding:14px 16px; background:#fff; }}
.section-card {{ border:1px solid #e5e2db; border-radius:12px; background:#fff; padding:16px 18px; }}
.muted {{ color:#777; font-size:0.82rem; }}
.codebox {{ background:#fafaf8; border:1px solid #ece8df; border-radius:8px; padding:10px 12px; font-size:0.84rem; }}
{FILTER_STYLE}
</style>
""", unsafe_allow_html=True)

st.markdown("<h1 style='margin-bottom:0'>📄 CV Fitting Tool</h1>", unsafe_allow_html=True)
st.markdown("<p style='color:#888;margin-top:4px;'>貼上履歷 → 抽取技能 → 對照目標市場 → 產生 Fit Score、技能診斷與履歷改寫建議</p>", unsafe_allow_html=True)
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


def safe_list(x):
    return x if isinstance(x, list) else []


# ── skill evidence weighting ─────────────────────────────
# 最小可部署版：不改 cv_parser.py，只在 CV Fitting 頁對已抽出的 canonical skills 做 evidence 權重。
# 目的：避免 R / AI / CV / DS / PM / QA / UI / UX 等短英文技能誤判後直接吃滿分。
SHORT_SKILL_ALLOWLIST = {
    # core analytics / data
    "SQL", "API", "ETL", "ELT", "DBT",
    "AWS", "GCP", "CRM", "ERP",

    # metrics / finance / marketing
    "KPI", "OKR", "DAU", "MAU", "GMV", "LTV", "CLV",
    "ROAS", "CTR", "CPC", "CPM", "CPL",
    "NPV", "IRR", "DCF", "LBO", "M&A",
    "AML", "KYC", "RPA", "PMO", "TPM",

    # engineering / AI
    "SWE", "SRE", "LLM", "RAG", "NLP",
    "C++", "C#", "F#",

    # enterprise/tools
    "SAP",
}

RISKY_SHORT_SKILLS = {
    "R", "AI", "BI", "BA", "CV", "DS", "DA", "DE",
    "ML", "PM", "QA", "UI", "UX", "GA", "PL", "SA",
    "CS", "HR", "IT", "PO", "AE", "SE", "AM",
}


def is_short_english_skill(skill: str) -> bool:
    """Return True when canonical skill is a short English token that may be noisy."""
    if not skill:
        return False

    s = str(skill).strip()
    if any("\u4e00" <= ch <= "\u9fff" for ch in s):
        return False

    if s.upper() in {"C++", "C#", "F#"}:
        return True

    letters = "".join(ch for ch in s if ch.isalpha())
    return len(letters) <= 3 and letters.isascii()


def get_skill_evidence_weight(skill: str) -> float:
    """
    CV skill evidence weight.
    - allowlist: 1.0
    - R: 0.50 by default; raise to 1.0 only if cv_parser is very precise for R.
    - risky <=2 letters: 0.25
    - risky 3 letters: 0.50
    - other short English <=2 letters: 0.25
    - other short English 3 letters: 0.50
    - otherwise: 1.0
    """
    if not skill:
        return 0.0

    s = str(skill).strip()
    upper = s.upper()

    if upper in SHORT_SKILL_ALLOWLIST:
        return 1.0

    if upper == "R":
        return 0.50

    letters = "".join(ch for ch in s if ch.isalpha())

    if upper in RISKY_SHORT_SKILLS:
        return 0.25 if len(letters) <= 2 else 0.50

    if is_short_english_skill(s):
        if len(letters) <= 2:
            return 0.25
        if len(letters) == 3:
            return 0.50

    return 1.0


def build_weighted_cv_skills(cv_skills):
    """
    Convert raw extracted canonical skills into weighted evidence artifacts.
    Returns:
    - weighted_skill_map: {skill: evidence_weight}
    - weighted_skill_rows: UI / export rows
    - deduped skills list
    """
    deduped = []
    seen = set()

    for sk in cv_skills:
        if not sk:
            continue
        sk = str(sk).strip()
        if sk and sk not in seen:
            deduped.append(sk)
            seen.add(sk)

    weighted_skill_map = {}
    rows = []

    for sk in deduped:
        w = get_skill_evidence_weight(sk)
        weighted_skill_map[sk] = w

        if w >= 1.0:
            label = "full"
            note = "完整權重"
        elif w >= 0.5:
            label = "downweighted_x0.5"
            note = "短英文技能，證據降權 ×0.5"
        else:
            label = "downweighted_x0.25"
            note = "高風險短英文技能，證據降權 ×0.25"

        rows.append({
            "skill": sk,
            "evidence_weight": w,
            "weight_label": label,
            "note": note,
        })

    return weighted_skill_map, rows, deduped


def render_skill_tag(skill, skill_to_parent, skill_colors, cv_skill_weights=None, css_class="tag-skill"):
    """Render a skill tag. Downweighted skills are marked as ×0.5 / ×0.25."""
    weight = 1.0 if cv_skill_weights is None else cv_skill_weights.get(skill, 1.0)
    color = skill_colors.get(skill_to_parent.get(skill, ""), "#e8edf5")
    label = skill if weight >= 1.0 else f"{skill} ×{weight:g}"
    border_style = "border-style:dashed;" if weight < 1.0 else ""
    title = "" if weight >= 1.0 else f"title='短英文技能已降權計算：×{weight:g}'"
    return (
        f"<span class='tag {css_class}' {title} "
        f"style='background:{color}22;border-color:{color}55;{border_style}'>{label}</span>"
    )


def build_target_profiles(rows, skill_to_sub):
    skill_weight = defaultdict(float)
    sub_skill_total = defaultdict(float)
    role_count = len(rows) or 1
    all_target_skills = set()

    for r in rows:
        for sk in safe_list(r.get("skill_canonical")):
            skill_weight[sk] += 1 / role_count
            sub = skill_to_sub.get(sk, "其他")
            sub_skill_total[sub] += 1 / role_count
            all_target_skills.add(sk)

    return dict(skill_weight), dict(sub_skill_total), all_target_skills


def compute_true_subskill_coverage(cv_skills, skill_weight, sub_skill_total, skill_to_sub, top_k=8, cv_skill_weights=None):
    """
    True sub-skill coverage with weighted CV evidence.
    Before: matched skill = 1.0 evidence.
    Now: matched skill = cv_skill_weights[skill] evidence.
    """
    cv_skill_weights = cv_skill_weights or {sk: 1.0 for sk in cv_skills}

    top_subs = sorted(sub_skill_total, key=sub_skill_total.get, reverse=True)[:top_k]
    sub_matched = defaultdict(float)
    evidence_score = defaultdict(float)
    evidence_count = defaultdict(int)

    for sk in cv_skills:
        if sk in skill_weight:
            w = cv_skill_weights.get(sk, 1.0)
            sub = skill_to_sub.get(sk, "其他")
            sub_matched[sub] += skill_weight[sk] * w
            evidence_score[sub] += w
            evidence_count[sub] += 1

    demand_axis = []
    coverage_axis = []
    confidence_axis = []

    for sub in top_subs:
        total = sub_skill_total.get(sub, 0)
        matched = sub_matched.get(sub, 0)
        demand_axis.append(1.0)
        coverage_axis.append(min(matched / total, 1.0) if total else 0.0)
        confidence_axis.append(min(evidence_score.get(sub, 0) / 3, 1.0))

    overall_coverage = (
        sum(sub_matched.get(sub, 0) for sub in sub_skill_total) /
        sum(sub_skill_total.values())
    ) if sub_skill_total else 0.0

    return {
        "top_subs": top_subs,
        "demand_axis": demand_axis,
        "coverage_axis": coverage_axis,
        "confidence_axis": confidence_axis,
        "overall_coverage": overall_coverage,
        "evidence_count": dict(evidence_count),
        "evidence_score": dict(evidence_score),
        "sub_matched_weight": dict(sub_matched),
    }


def build_category_scores(overall_coverage, cv_skills, target_skills, matched_skills, has_target, cv_skill_weights=None):
    cv_skill_weights = cv_skill_weights or {sk: 1.0 for sk in cv_skills}

    skills_match = overall_coverage
    weighted_matched = sum(cv_skill_weights.get(sk, 1.0) for sk in matched_skills)
    keywords_coverage = weighted_matched / len(target_skills) if target_skills else 0.0

    total_cv_evidence = sum(cv_skill_weights.get(sk, 1.0) for sk in cv_skills) or 1.0
    evidence_strength = min(weighted_matched / total_cv_evidence, 1.0)

    industry_alignment = 0.8 if has_target else 0.6
    experience_relevance = min((skills_match * 0.6 + keywords_coverage * 0.4), 1.0)

    return {
        "skills_match": round(skills_match, 4),
        "experience_relevance": round(experience_relevance, 4),
        "industry_alignment": round(industry_alignment, 4),
        "keywords_coverage": round(keywords_coverage, 4),
        "evidence_strength": round(evidence_strength, 4),
    }


def apply_weighted_fit_adjustment(raw_results, cv_skill_weights):
    """
    Low-intrusion weighted fit adjustment.
    Keeps compute_fit_scores() output shape and sample_size, then discounts roles whose matched skills are mostly weak evidence.
    """
    adjusted = []
    for r in raw_results:
        rr = dict(r)
        matched = rr.get("matched_skills", []) or []

        if matched:
            weighted_sum = sum(cv_skill_weights.get(sk, 1.0) for sk in matched)
            evidence_factor = weighted_sum / len(matched)
        else:
            evidence_factor = 0.0

        rr["raw_fit_score"] = rr.get("fit_score", 0.0)
        rr["weighted_evidence_factor"] = evidence_factor
        rr["fit_score"] = min(rr.get("fit_score", 0.0) * evidence_factor, 1.0)
        adjusted.append(rr)

    return sorted(adjusted, key=lambda x: x.get("fit_score", 0), reverse=True)


def build_structured_diagnosis(
    cv_text,
    cv_skills,
    matched_skills,
    gap_skills,
    top_roles,
    category_scores,
    target_label,
    cv_skill_weights=None,
    cv_skill_rows=None,
):
    cv_skill_weights = cv_skill_weights or {sk: 1.0 for sk in cv_skills}
    cv_skill_rows = cv_skill_rows or []

    best_role = top_roles[0]["role"] if top_roles else "未判定"
    overall_score = round(
        category_scores["skills_match"] * 0.4 +
        category_scores["experience_relevance"] * 0.2 +
        category_scores["industry_alignment"] * 0.15 +
        category_scores["keywords_coverage"] * 0.15 +
        category_scores["evidence_strength"] * 0.10,
        4
    )

    downweighted_skills = [r for r in cv_skill_rows if r.get("evidence_weight", 1.0) < 1.0]

    strengths = []
    if matched_skills:
        strengths.append(f"履歷已命中 {len(matched_skills)} 個目標市場技能，包含：{', '.join(matched_skills[:6])}")
    if top_roles:
        strengths.append(f"目前最適合的職能為 {best_role}，代表技能組合與市場需求已有明顯重疊")
    if len(cv_text) > 300:
        strengths.append("履歷內容篇幅足夠，具備進一步做 LLM 診斷與改寫的文本基礎")

    gaps = []
    if gap_skills:
        gaps.append(f"高優先缺口技能包含：{', '.join(gap_skills[:6])}")
    if category_scores["evidence_strength"] < 0.45:
        gaps.append("履歷中的技能證據偏弱，可能只提到工具名稱，缺少具體成果或使用情境")
    if category_scores["keywords_coverage"] < 0.35:
        gaps.append("關鍵字覆蓋不足，對目標市場的重要技能仍有明顯缺漏")
    if downweighted_skills:
        gaps.append("部分短英文技能已降權計算，建議在履歷中補上完整技能名稱或使用情境，避免 ATS / parser 誤判")

    suggestions = [
        "補強前 3 個高需求缺口技能，優先用專案或量化成果呈現，而不只列工具名稱。",
        "把既有經歷 bullet 改寫成『做了什麼 + 影響了什麼指標 + 用了哪些技能』的格式。",
        f"若目標是 {target_label}，建議針對最適 role 的核心技能建立一個對應 side project。",
    ]

    if downweighted_skills:
        suggestions.append("對 R / AI / ML / PM / QA / UI / UX 等短技能，履歷中優先寫完整名稱，例如 Machine Learning、Product Management、Quality Assurance。")

    role_explanation = {
        "best_fit_role": best_role,
        "why_fit": [
            "你的履歷技能與目標市場需求已有一定重疊。",
            "目前分數最高的角色代表技能輪廓和市場常見需求最接近。",
            "短英文技能已用 evidence weight 降權，因此分數更偏向保守估計。",
        ],
        "key_skill_evidence": [
            {"skill": sk, "evidence_weight": cv_skill_weights.get(sk, 1.0)}
            for sk in matched_skills[:8]
        ],
        "biggest_gap": gap_skills[:6],
    }

    rewrite_suggestions = []
    sample_lines = [ln.strip() for ln in cv_text.splitlines() if ln.strip()][:3]
    for line in sample_lines[:3]:
        rewritten = line
        if not any(ch.isdigit() for ch in line):
            rewritten = line + "，並以可量化成果呈現專案影響，例如提升效率、優化流程或改善決策品質。"
        reason = "補上 impact 與 evidence，讓經歷更像目標職能會採信的履歷 bullet。"
        rewrite_suggestions.append({
            "original": line,
            "rewritten": rewritten,
            "reason": reason,
        })

    return {
        "overall_score": overall_score,
        "category_scores": category_scores,
        "skill_evidence_summary": {
            "detected_skill_count": len(cv_skills),
            "downweighted_skill_count": len(downweighted_skills),
            "effective_skill_evidence": round(sum(cv_skill_weights.get(sk, 1.0) for sk in cv_skills), 4),
            "downweighted_skills": downweighted_skills,
        },
        "strengths": strengths,
        "gaps": gaps,
        "suggestions": suggestions,
        "role_explanation": role_explanation,
        "rewrite_suggestions": rewrite_suggestions,
    }


def build_llm_ready_diagnosis_payload(
    target_label,
    cv_skills,
    cv_skill_weights,
    matched_skills,
    gap_skills,
    results,
    category_scores,
    coverage_pack,
):
    """Stable JSON payload for future LLM diagnosis / rewrite calls."""
    return {
        "target_context": {
            "target_label": target_label,
            "analysis_scope": "selected_market_slice" if target_label != "全市場" else "overall_market",
        },
        "score_summary": {
            "overall_score": round(
                category_scores["skills_match"] * 0.4 +
                category_scores["experience_relevance"] * 0.2 +
                category_scores["industry_alignment"] * 0.15 +
                category_scores["keywords_coverage"] * 0.15 +
                category_scores["evidence_strength"] * 0.10,
                4,
            ),
            "category_scores": category_scores,
            "coverage": coverage_pack.get("overall_coverage", 0),
        },
        "skill_evidence": {
            "detected_skills": [
                {
                    "skill": sk,
                    "evidence_weight": cv_skill_weights.get(sk, 1.0),
                    "is_downweighted": cv_skill_weights.get(sk, 1.0) < 1.0,
                }
                for sk in cv_skills
            ],
            "matched_target_skills": matched_skills[:30],
            "priority_gap_skills": gap_skills[:30],
        },
        "role_fit": [
            {
                "role": r.get("role"),
                "fit_score": r.get("fit_score"),
                "raw_fit_score": r.get("raw_fit_score"),
                "weighted_evidence_factor": r.get("weighted_evidence_factor"),
                "matched_skills": r.get("matched_skills", [])[:12],
                "gap_skills": r.get("gap_skills", [])[:12],
                "sample_size": r.get("sample_size", 0),
            }
            for r in results[:10]
        ],
        "subskill_coverage": [
            {
                "sub_skill": sub,
                "coverage": cov,
                "evidence_score": ev,
                "matched_skill_count": coverage_pack["evidence_count"].get(sub, 0),
                "weighted_evidence": coverage_pack.get("evidence_score", {}).get(sub, 0),
            }
            for sub, cov, ev in zip(
                coverage_pack.get("top_subs", []),
                coverage_pack.get("coverage_axis", []),
                coverage_pack.get("confidence_axis", []),
            )
        ],
        "llm_instruction": {
            "task": "Generate resume diagnosis and rewrite suggestions.",
            "output_language": "zh-TW",
            "must_include": [
                "best_fit_role",
                "why_fit",
                "key_skill_evidence",
                "biggest_gap",
                "rewrite_suggestions",
                "next_learning_actions",
            ],
            "style": "concise, practical, non-exaggerated",
        },
    }


all_rows = load_postings()
taxonomy = load_taxonomy()
skill_to_parent = dict(zip(taxonomy["canonical_skill_name"], taxonomy["skill_parent_category"]))
skill_to_sub = dict(zip(taxonomy["canonical_skill_name"], taxonomy["skill_sub_category"]))
parent_cats = sorted(x for x in taxonomy["skill_parent_category"].unique() if x)
SKILL_COLORS = build_skill_parent_colors(parent_cats)

# ── input ────────────────────────────────────────────────
input_mode = st.radio("輸入方式", ["貼上文字", "上傳 .txt / .md 檔案"], horizontal=True)
cv_text = ""
if input_mode == "貼上文字":
    cv_text = st.text_area("履歷內容（中英文皆可）", height=220, placeholder="貼上你的技能、工作經歷、專案描述...")
else:
    uploaded = st.file_uploader("上傳純文字檔", type=["txt", "md"])
    if uploaded:
        cv_text = uploaded.read().decode("utf-8", errors="ignore")
        st.success(f"✅ 已載入 {len(cv_text)} 字元")
        with st.expander("預覽內容"):
            st.text(cv_text[:1200] + ("..." if len(cv_text) > 1200 else ""))

st.markdown("---")
with st.expander("🎯 目標條件（選填）", expanded=True):
    st.caption("不選代表分析全市場；選擇後會優先對應指定產業 / 職能切片")
    st.markdown(filter_label("🎯 選擇職能", first=True), unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        t_role_par = st.selectbox("職能大類（選填）", ["全部"] + get_role_parents(all_rows), key="cv_rp")
    with c2:
        role_sub_opts = ["全部"] + (get_role_subs(all_rows, t_role_par) if t_role_par != "全部" else [])
        t_role_sub = st.selectbox("職能中類（選填）", role_sub_opts, key="cv_rs", disabled=(t_role_par == "全部"))

    st.markdown(filter_label("🏭 選擇產業"), unsafe_allow_html=True)
    c3, c4 = st.columns(2)
    with c3:
        t_ind_par = st.selectbox("產業大類（選填）", ["全部"] + get_industry_parents(all_rows), key="cv_ip")
    with c4:
        ind_sub_opts = ["全部"] + (get_industry_subs(all_rows, t_ind_par) if t_ind_par != "全部" else [])
        t_ind_sub = st.selectbox("產業別（選填）", ind_sub_opts, key="cv_is", disabled=(t_ind_par == "全部"))

has_target = (t_role_par != "全部" or t_ind_par != "全部")
if has_target:
    target_rows = ut_filter_rows(all_rows,
                                 industry_parent=t_ind_par, industry_sub=t_ind_sub,
                                 role_parent=t_role_par, role_sub=t_role_sub)
    target_label = " / ".join(p for p in [
        format_role_label(t_role_par, t_role_sub),
        format_industry_label(t_ind_par, t_ind_sub),
    ] if p not in {"全部職能", "全部產業"}) or "指定切片"
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

# ── extract skills ───────────────────────────────────────
with st.spinner("抽取技能中..."):
    raw_cv_skills = extract_skills_from_text(cv_text)

if not raw_cv_skills:
    st.warning("⚠️ 未能辨識出已知技能，請確認 skill_alias.csv 存在於專案根目錄。")
    st.stop()

cv_skill_weights, cv_skill_rows, cv_skills = build_weighted_cv_skills(raw_cv_skills)

st.markdown("### 🛠️ 從履歷辨識到的技能")
skill_html = " ".join(
    render_skill_tag(s, skill_to_parent, SKILL_COLORS, cv_skill_weights=cv_skill_weights)
    for s in cv_skills
)
st.markdown(skill_html, unsafe_allow_html=True)

downweighted_count = sum(1 for r in cv_skill_rows if r["evidence_weight"] < 1.0)
effective_evidence = sum(cv_skill_weights.get(s, 1.0) for s in cv_skills)
st.markdown(
    f"<p class='muted'>共 {len(cv_skills)} 個 canonical skill；有效 evidence 權重 {effective_evidence:.2f}；其中 {downweighted_count} 個短英文技能已降權計算。</p>",
    unsafe_allow_html=True,
)

with st.expander("查看技能權重明細"):
    st.dataframe(
        pd.DataFrame(cv_skill_rows).rename(columns={
            "skill": "Skill",
            "evidence_weight": "Evidence Weight",
            "weight_label": "Weight Type",
            "note": "Note",
        }),
        use_container_width=True,
        hide_index=True,
    )

# ── target profile ───────────────────────────────────────
skill_weight, sub_skill_total, all_target_skills = build_target_profiles(target_rows, skill_to_sub)
coverage_pack = compute_true_subskill_coverage(
    cv_skills,
    skill_weight,
    sub_skill_total,
    skill_to_sub,
    top_k=8,
    cv_skill_weights=cv_skill_weights,
)
matched_target_skills = sorted(
    [s for s in cv_skills if s in all_target_skills],
    key=lambda s: skill_weight.get(s, 0) * cv_skill_weights.get(s, 1.0),
    reverse=True,
)
gap_skills = sorted(
    list(all_target_skills - set(cv_skills)),
    key=lambda s: skill_weight.get(s, 0),
    reverse=True,
)
category_scores = build_category_scores(
    coverage_pack["overall_coverage"],
    cv_skills,
    all_target_skills,
    matched_target_skills,
    has_target,
    cv_skill_weights=cv_skill_weights,
)

# ── radar + overall ──────────────────────────────────────
st.markdown("---")
st.markdown("### 📡 技能匹配診斷")
st.caption(f"目標切片：{target_label}")

m1, m2, m3 = st.columns(3)
with m1:
    st.metric("整體 Coverage", f"{coverage_pack['overall_coverage']:.0%}")
with m2:
    conf = (sum(coverage_pack['confidence_axis']) / len(coverage_pack['confidence_axis'])) if coverage_pack['confidence_axis'] else 0
    st.metric("Evidence Score", f"{conf:.0%}")
with m3:
    st.metric("目標技能命中數", f"{len(matched_target_skills)} / {len(all_target_skills)}")

if coverage_pack["top_subs"]:
    theta = coverage_pack["top_subs"] + [coverage_pack["top_subs"][0]]
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=coverage_pack["demand_axis"] + [coverage_pack["demand_axis"][0]],
        theta=theta, fill="toself", name="目標需求",
        line=dict(color="#1e3a5f"), fillcolor="rgba(30,58,95,0.10)"
    ))
    fig.add_trace(go.Scatterpolar(
        r=coverage_pack["coverage_axis"] + [coverage_pack["coverage_axis"][0]],
        theta=theta, fill="toself", name="CV 真實覆蓋率",
        line=dict(color="#e54d2e"), fillcolor="rgba(229,77,46,0.16)"
    ))
    fig.add_trace(go.Scatterpolar(
        r=coverage_pack["confidence_axis"] + [coverage_pack["confidence_axis"][0]],
        theta=theta, fill="toself", name="Evidence / Confidence",
        line=dict(color="#7a39bb", dash="dot"), fillcolor="rgba(122,57,187,0.08)"
    ))
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 1], tickformat=".0%")),
        showlegend=True, height=430, margin=dict(l=30, r=30, t=20, b=20),
        font=dict(family="DM Sans"),
    )
    st.plotly_chart(fig, use_container_width=True)

sub_df = pd.DataFrame([{
    "Sub Skill": sub,
    "真實覆蓋率": f"{cov:.0%}",
    "Evidence Score": f"{confv:.0%}",
    "命中技能數": coverage_pack["evidence_count"].get(sub, 0),
    "Weighted Evidence": round(coverage_pack.get("evidence_score", {}).get(sub, 0), 2),
} for sub, cov, confv in zip(coverage_pack["top_subs"], coverage_pack["coverage_axis"], coverage_pack["confidence_axis"])])
st.dataframe(sub_df, use_container_width=True, hide_index=True)

if gap_skills:
    st.markdown("**⚠️ 優先補強技能**")
    st.markdown(" ".join(f'<span class="tag tag-gap">{s}</span>' for s in gap_skills[:12]), unsafe_allow_html=True)

# ── fit score ────────────────────────────────────────────
st.markdown("---")
with st.spinner("計算 Fit Score..."):
    fit_source = target_rows if target_rows else all_rows
    role_skill_demand = build_role_skill_demand_from_db(fit_source)
    raw_results = compute_fit_scores(cv_skills, role_skill_demand, top_n=30) if role_skill_demand else []
    results = apply_weighted_fit_adjustment(raw_results, cv_skill_weights)

role_to_sub = {}
for r in fit_source:
    role = r.get("role_normalized")
    sub = r.get("job_sub_category") or "其他"
    if role and role != "Unclassified":
        role_to_sub[role] = sub

st.markdown("### 🎯 Fit Score 排名")
st.markdown("<p class='muted'>先看職能中類，再展開查看職能別細節。短英文技能會用 evidence weight 保守調整分數。</p>", unsafe_allow_html=True)
sub_groups = defaultdict(list)
for res in results:
    sub_groups[role_to_sub.get(res["role"], "其他")].append(res)
sub_avg = sorted([(sub, sum(r["fit_score"] for r in items) / len(items)) for sub, items in sub_groups.items()], key=lambda x: x[1], reverse=True)

for sub, avg_score in sub_avg:
    avg_pct = int(avg_score * 100)
    bar_color = "#0f0f0f" if avg_pct >= 60 else "#b45309" if avg_pct >= 30 else "#aaa"
    with st.expander(f"📂 {sub} — 平均 {avg_pct}%　({len(sub_groups[sub])} 個職能別)", expanded=(avg_pct >= 60)):
        st.markdown(
            f"<div style='background:#f0f0f0;border-radius:4px;height:6px;margin:4px 0 12px 0;'><div style='width:{avg_pct}%;height:6px;border-radius:4px;background:{bar_color};'></div></div>",
            unsafe_allow_html=True,
        )
        for i, r in enumerate(sorted(sub_groups[sub], key=lambda x: x["fit_score"], reverse=True), 1):
            score_pct = int(r["fit_score"] * 100)
            raw_score_pct = int(r.get("raw_fit_score", r["fit_score"]) * 100)
            evidence_factor_pct = int(r.get("weighted_evidence_factor", 1.0) * 100)
            rc = "#0f0f0f" if score_pct >= 60 else "#b45309" if score_pct >= 30 else "#aaa"
            matched_html = " ".join(
                render_skill_tag(s, skill_to_parent, SKILL_COLORS, cv_skill_weights=cv_skill_weights, css_class="tag-match")
                for s in r.get("matched_skills", [])
            )
            gap_html = " ".join(f'<span class="tag tag-gap">{s}</span>' for s in r.get("gap_skills", [])[:6])
            st.markdown(f"""
            <div class="fit-card">
              <div style="display:flex;justify-content:space-between;align-items:center;">
                <div class="fit-role">#{i} {r['role']}</div>
                <div style="font-size:1.25rem;font-family:'Syne',sans-serif;font-weight:800;color:{rc};">{score_pct}%</div>
              </div>
              <div style="background:#f0f0f0;border-radius:6px;height:7px;margin:5px 0;">
                <div style="width:{score_pct}%;height:7px;border-radius:6px;background:{rc};"></div>
              </div>
              <div class="muted" style="margin-top:4px;">Raw Fit：{raw_score_pct}%｜Evidence Factor：{evidence_factor_pct}%</div>
              <div style="margin-top:8px;"><span class="muted">✅ 匹配技能</span><br>{matched_html if matched_html else '<span class="muted">無</span>'}</div>
              <div style="margin-top:6px;"><span class="muted">❌ 缺口技能</span><br>{gap_html if gap_html else '<span class="muted">無缺口</span>'}</div>
              <div class="muted" style="margin-top:6px;">樣本職缺：{r.get('sample_size', 0)} 筆</div>
            </div>
            """, unsafe_allow_html=True)

# ── structured diagnosis ────────────────────────────────
structured = build_structured_diagnosis(
    cv_text=cv_text,
    cv_skills=cv_skills,
    matched_skills=matched_target_skills,
    gap_skills=gap_skills,
    top_roles=results[:5],
    category_scores=category_scores,
    target_label=target_label,
    cv_skill_weights=cv_skill_weights,
    cv_skill_rows=cv_skill_rows,
)

llm_payload = build_llm_ready_diagnosis_payload(
    target_label=target_label,
    cv_skills=cv_skills,
    cv_skill_weights=cv_skill_weights,
    matched_skills=matched_target_skills,
    gap_skills=gap_skills,
    results=results,
    category_scores=category_scores,
    coverage_pack=coverage_pack,
)

st.markdown("---")
st.markdown("### 🧠 結構化診斷")
mc1, mc2, mc3, mc4, mc5 = st.columns(5)
metrics = structured["category_scores"]
mc1.metric("Skills Match", f"{metrics['skills_match']:.0%}")
mc2.metric("Experience", f"{metrics['experience_relevance']:.0%}")
mc3.metric("Industry", f"{metrics['industry_alignment']:.0%}")
mc4.metric("Keywords", f"{metrics['keywords_coverage']:.0%}")
mc5.metric("Evidence", f"{metrics['evidence_strength']:.0%}")
st.metric("Overall Score", f"{structured['overall_score']:.0%}")

csa, csb = st.columns(2)
with csa:
    st.markdown("**Strengths**")
    for item in structured["strengths"]:
        st.markdown(f"- {item}")
    st.markdown("**Suggestions**")
    for item in structured["suggestions"]:
        st.markdown(f"- {item}")
with csb:
    st.markdown("**Gaps**")
    for item in structured["gaps"]:
        st.markdown(f"- {item}")
    st.markdown("**Role Explanation**")
    st.markdown(f"- Best fit role：**{structured['role_explanation']['best_fit_role']}**")
    key_evidence = structured["role_explanation"]["key_skill_evidence"]
    key_evidence_txt = ", ".join(f"{x['skill']}×{x['evidence_weight']:g}" for x in key_evidence) if key_evidence else "無"
    st.markdown(f"- 關鍵證據：{key_evidence_txt}")
    st.markdown(f"- 最大缺口：{', '.join(structured['role_explanation']['biggest_gap']) if structured['role_explanation']['biggest_gap'] else '無'}")

with st.expander("查看結構化診斷 JSON"):
    st.code(json.dumps(structured, ensure_ascii=False, indent=2), language="json")

with st.expander("查看 LLM-ready diagnosis payload"):
    st.code(json.dumps(llm_payload, ensure_ascii=False, indent=2), language="json")

st.markdown("---")
st.markdown("### ✍️ 履歷改寫建議")
for i, item in enumerate(structured["rewrite_suggestions"], 1):
    st.markdown(f"**{i}. 原始 bullet**")
    st.markdown(f"<div class='codebox'>{item['original']}</div>", unsafe_allow_html=True)
    st.markdown("**改寫建議**")
    st.markdown(f"<div class='codebox'>{item['rewritten']}</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='muted'>原因：{item['reason']}</div>", unsafe_allow_html=True)

st.markdown("---")
df_export = pd.DataFrame([{
    "job_sub_category": role_to_sub.get(r["role"], "其他"),
    "role": r["role"],
    "fit_score": r["fit_score"],
    "raw_fit_score": r.get("raw_fit_score", r["fit_score"]),
    "weighted_evidence_factor": r.get("weighted_evidence_factor", 1.0),
    "matched_skills": ", ".join(r.get("matched_skills", [])),
    "gap_skills": ", ".join(r.get("gap_skills", [])),
    "sample_size": r.get("sample_size", 0),
    "overall_score": structured["overall_score"],
} for r in results])
csv = df_export.to_csv(index=False, encoding="utf-8-sig")
st.download_button("📥 匯出 Fit Score CSV", data=csv, file_name="fit_scores.csv", mime="text/csv")

skill_evidence_export = pd.DataFrame(cv_skill_rows)
skill_csv = skill_evidence_export.to_csv(index=False, encoding="utf-8-sig")
st.download_button("📥 匯出 CV Skill Evidence CSV", data=skill_csv, file_name="cv_skill_evidence.csv", mime="text/csv")
