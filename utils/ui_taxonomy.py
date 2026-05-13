#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
utils/ui_taxonomy.py
共用層級 / filter / label / color helper

術語對照：
  industry_bucket       → 產業大類
  industry_raw          → 產業別
  job_parent_category   → 職能大類
  job_sub_category      → 職能中類
  role_normalized       → 職能別
"""

from collections import defaultdict

# ── Skill Parent Category 配色（全頁統一） ─────────────
SKILL_PARENT_PALETTE = [
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


def build_skill_parent_colors(parent_categories: list[str]) -> dict[str, str]:
    cats = sorted(c for c in parent_categories if c)
    return {cat: SKILL_PARENT_PALETTE[i % len(SKILL_PARENT_PALETTE)] for i, cat in enumerate(cats)}


# ── Streamlit session_state helper ───────────────────────
def ensure_valid_state(st, key: str, valid_options: list, default: str = "全部") -> None:
    if key not in st.session_state or st.session_state[key] not in valid_options:
        st.session_state[key] = default


# ── Options builders ─────────────────────────────────────
def get_industry_parents(rows: list, role_parent: str = "全部", role_sub: str = "全部") -> list[str]:
    return sorted({
        r.get("industry_bucket")
        for r in rows
        if r.get("industry_bucket")
        and (role_parent == "全部" or r.get("job_parent_category") == role_parent)
        and (role_sub == "全部" or r.get("job_sub_category") == role_sub)
    })


def get_industry_subs(rows: list, industry_parent: str,
                      role_parent: str = "全部", role_sub: str = "全部") -> list[str]:
    """産業別 → industry_raw"""
    return sorted({
        r.get("industry_raw")
        for r in rows
        if r.get("industry_raw")
        and r.get("industry_bucket") == industry_parent
        and (role_parent == "全部" or r.get("job_parent_category") == role_parent)
        and (role_sub == "全部" or r.get("job_sub_category") == role_sub)
    })


def get_role_parents(rows: list, industry_parent: str = "全部", industry_sub: str = "全部") -> list[str]:
    return sorted({
        r.get("job_parent_category")
        for r in rows
        if r.get("job_parent_category")
        and (industry_parent == "全部" or r.get("industry_bucket") == industry_parent)
        and (industry_sub == "全部" or r.get("industry_raw") == industry_sub)
    })


def get_role_subs(rows: list, role_parent: str,
                  industry_parent: str = "全部", industry_sub: str = "全部") -> list[str]:
    return sorted({
        r.get("job_sub_category")
        for r in rows
        if r.get("job_sub_category")
        and r.get("job_parent_category") == role_parent
        and (industry_parent == "全部" or r.get("industry_bucket") == industry_parent)
        and (industry_sub == "全部" or r.get("industry_raw") == industry_sub)
    })


def get_roles(rows: list, role_parent: str = "全部", role_sub: str = "全部",
              industry_parent: str = "全部", industry_sub: str = "全部") -> list[str]:
    return sorted({
        r.get("role_normalized")
        for r in rows
        if r.get("role_normalized") and r.get("role_normalized") != "Unclassified"
        and (role_parent == "全部" or r.get("job_parent_category") == role_parent)
        and (role_sub == "全部" or r.get("job_sub_category") == role_sub)
        and (industry_parent == "全部" or r.get("industry_bucket") == industry_parent)
        and (industry_sub == "全部" or r.get("industry_raw") == industry_sub)
    })


# ── Row filtering ─────────────────────────────────────────
def filter_rows(rows: list,
                industry_parent: str = "全部",
                industry_sub: str = "全部",
                role_parent: str = "全部",
                role_sub: str = "全部",
                roles: list | None = None) -> list:
    roles = roles or []
    return [
        r for r in rows
        if (industry_parent == "全部" or r.get("industry_bucket") == industry_parent)
        and (industry_sub == "全部" or r.get("industry_raw") == industry_sub)
        and (role_parent == "全部" or r.get("job_parent_category") == role_parent)
        and (role_sub == "全部" or r.get("job_sub_category") == role_sub)
        and (not roles or r.get("role_normalized") in roles)
    ]


# ── Label helpers ─────────────────────────────────────────
def format_industry_label(parent: str, sub: str = "全部") -> str:
    if parent == "全部":
        return "全部產業"
    return f"{parent} / {sub}" if sub != "全部" else parent


def format_role_label(parent: str, sub: str = "全部") -> str:
    if parent == "全部":
        return "全部職能"
    return f"{parent} / {sub}" if sub != "全部" else parent


# ── Shared filter-section label HTML ─────────────────────
FILTER_STYLE = """
<style>
.filter-section-label {
    font-size: 0.72rem;
    font-weight: 700;
    color: #888;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin: 14px 0 6px 0;
    padding: 6px 0 4px 0;
    border-top: 1px solid #e5e2db;
}
.filter-section-label.first { border-top: none; margin-top: 0; }
</style>
"""


def filter_label(text: str, first: bool = False) -> str:
    cls = "filter-section-label first" if first else "filter-section-label"
    return f"<div class='{cls}'>{text}</div>"
