#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CV 解析與 FitScore 計算模組
- 從履歷文字抽取 canonical skills（對照 skill_alias.csv）
- 對每個 role 計算 coverage score
"""

import re
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

SKILL_ALIAS_PATH = ROOT / "skill_alias.csv"
SKILL_TAXONOMY_PATH = ROOT / "skill_taxonomy.csv"
ROLE_ALIAS_PATH = ROOT / "role_alias.csv"
JOB_TAXONOMY_PATH = ROOT / "Job_taxonomy_byRole.csv"


# ── 載入 taxonomy（cached at module level） ───────────────

def _load_skill_alias() -> Dict[str, str]:
    """alias_text → canonical_skill_name"""
    if not SKILL_ALIAS_PATH.exists():
        return {}
    df = pd.read_csv(SKILL_ALIAS_PATH, encoding="utf-8-sig").fillna("")
    mapping = {}
    for _, row in df.iterrows():
        canonical = str(row.get("canonical_skill_name", "")).strip()
        alias = str(row.get("alias", "")).strip()
        if canonical and alias:
            mapping[alias.lower()] = canonical
    return mapping


def _build_skill_regex(alias_map: Dict[str, str]):
    """建立 alias → canonical 的 regex pattern list，長的優先匹配。"""
    patterns = []
    for alias in sorted(alias_map.keys(), key=len, reverse=True):
        escaped = re.escape(alias)
        patterns.append((re.compile(escaped, re.IGNORECASE), alias_map[alias]))
    return patterns


def _load_role_skill_map() -> Dict[str, List[str]]:
    """role_normalized → [canonical_skill_name, ...]"""
    if not JOB_TAXONOMY_PATH.exists():
        return {}
    df = pd.read_csv(JOB_TAXONOMY_PATH, encoding="utf-8-sig").fillna("")
    role_skills: Dict[str, set] = {}
    for _, row in df.iterrows():
        role = str(row.get("job_skill_name", "")).strip()  # adjust col name if needed
        skill = str(row.get("canonical_skill_name", "")).strip()
        if not role or not skill:
            continue
        role_skills.setdefault(role, set()).add(skill)
    return {k: list(v) for k, v in role_skills.items()}


# Module-level cache
_SKILL_ALIAS: Dict[str, str] = {}
_SKILL_PATTERNS = []
_ROLE_SKILL_MAP: Dict[str, List[str]] = {}
_INITIALIZED = False


def _ensure_init():
    global _SKILL_ALIAS, _SKILL_PATTERNS, _ROLE_SKILL_MAP, _INITIALIZED
    if _INITIALIZED:
        return
    _SKILL_ALIAS = _load_skill_alias()
    _SKILL_PATTERNS = _build_skill_regex(_SKILL_ALIAS)
    _ROLE_SKILL_MAP = _load_role_skill_map()
    _INITIALIZED = True


# ── 公開 API ──────────────────────────────────────────────

def extract_skills_from_text(text: str) -> List[str]:
    """
    從任意文字（履歷、JD）抽取 canonical skill 名稱。
    回傳去重後的列表。
    """
    _ensure_init()
    found = set()
    for pattern, canonical in _SKILL_PATTERNS:
        if pattern.search(text):
            found.add(canonical)
    return sorted(found)


def compute_fit_scores(
    cv_skills: List[str],
    role_skill_demand: Dict[str, Dict[str, int]],
    top_n: int = 10,
) -> List[Dict]:
    """
    計算 CV 對每個 role 的 fit score。

    Args:
        cv_skills: 從履歷抽到的 canonical skills
        role_skill_demand: {role: {skill: count}} 來自 DB 聚合
        top_n: 回傳前 N 個 role

    Returns:
        List of {role, fit_score, matched_skills, gap_skills, sample_size}
    """
    cv_set = set(cv_skills)
    results = []

    for role, skill_counts in role_skill_demand.items():
        if not skill_counts:
            continue
        total_jobs = max(skill_counts.values()) if skill_counts else 1
        role_skills = set(skill_counts.keys())

        matched = cv_set & role_skills
        gap = role_skills - cv_set

        # weighted coverage: skills with higher demand weighted more
        weighted_match = sum(skill_counts.get(s, 0) for s in matched)
        weighted_total = sum(skill_counts.values())
        fit_score = round(weighted_match / weighted_total, 3) if weighted_total else 0.0

        results.append({
            "role": role,
            "fit_score": fit_score,
            "matched_skills": sorted(matched),
            "gap_skills": sorted(gap, key=lambda s: skill_counts.get(s, 0), reverse=True)[:10],
            "sample_size": total_jobs,
        })

    results.sort(key=lambda x: x["fit_score"], reverse=True)
    return results[:top_n]


def build_role_skill_demand_from_db(rows: List[Dict]) -> Dict[str, Dict[str, int]]:
    """
    從 job_posting rows 聚合出 {role: {skill: count}}。
    傳入欄位需含 role_normalized, skill_canonical。
    """
    demand: Dict[str, Dict[str, int]] = {}
    for row in rows:
        role = row.get("role_normalized")
        skills = row.get("skill_canonical") or []
        if not role or role == "Unclassified" or not isinstance(skills, list):
            continue
        if role not in demand:
            demand[role] = {}
        for skill in skills:
            demand[role][skill] = demand[role].get(skill, 0) + 1
    return demand
