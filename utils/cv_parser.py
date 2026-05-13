#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CV / JD skill parser with boundary-safe alias matching and context guards.

Drop-in replacement for utils/cv_parser.py.
Expected files:
- project_root/skill_alias.csv

Main public functions kept compatible:
- extract_skills_from_text(text, alias_path=None)
- build_role_skill_demand_from_db(rows)
- compute_fit_scores(cv_skills, role_skill_demand, top_n=20)
"""

from __future__ import annotations

import re
from pathlib import Path
from functools import lru_cache
from collections import Counter, defaultdict
from typing import Any

import pandas as pd


# ─────────────────────────────────────────────────────────────
# Matching constants
# ─────────────────────────────────────────────────────────────

SPECIAL_ALIAS_PATTERNS = {
    # allow C++17 / C++11 but avoid abc++def style accidental hits
    "c++": r"(?<![A-Za-z0-9_+#])c\+\+(?![A-Za-z_+#])",
    "c#": r"(?<![A-Za-z0-9_+#])c\#(?![A-Za-z_+#])",
    "f#": r"(?<![A-Za-z0-9_+#])f\#(?![A-Za-z_+#])",
    "p&l": r"(?<![A-Za-z0-9_&])p\s*&\s*l(?![A-Za-z0-9_&])",
    "s&op": r"(?<![A-Za-z0-9_&])s\s*&\s*op(?![A-Za-z0-9_&])",
    "m&a": r"(?<![A-Za-z0-9_&])m\s*&\s*a(?![A-Za-z0-9_&])",
    "a/b testing": r"(?<![A-Za-z0-9_/])a\s*/\s*b\s+testing(?![A-Za-z0-9_/])",
    "a/b test": r"(?<![A-Za-z0-9_/])a\s*/\s*b\s+test(?![A-Za-z0-9_/])",
    "pl/sql": r"(?<![A-Za-z0-9_/])pl\s*/\s*sql(?![A-Za-z0-9_/])",
    "t-sql": r"(?<![A-Za-z0-9_-])t\s*-\s*sql(?![A-Za-z0-9_-])",
    "node.js": r"(?<![A-Za-z0-9_.])node\.js(?![A-Za-z0-9_.])",
    "d3.js": r"(?<![A-Za-z0-9_.])d3\.js(?![A-Za-z0-9_.])",
    "monday.com": r"(?<![A-Za-z0-9_.])monday\.com(?![A-Za-z0-9_.])",
    "s/4hana": r"(?<![A-Za-z0-9_/])s\s*/\s*4hana(?![A-Za-z0-9_/])",
}

TOKEN_BOUNDARY = r"A-Za-z0-9_+#"
CONTEXT_WINDOW_CHARS = 120


# ─────────────────────────────────────────────────────────────
# General helpers
# ─────────────────────────────────────────────────────────────

def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def normalize_text_for_match(text: str) -> str:
    """Normalize text while preserving symbols used by technical skills."""
    if not text:
        return ""
    text = str(text).lower()
    # common full-width variants
    text = (
        text.replace("＋", "+")
        .replace("＃", "#")
        .replace("＆", "&")
        .replace("／", "/")
        .replace("－", "-")
        .replace("–", "-")
        .replace("—", "-")
        .replace("\u00a0", " ")
    )
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def split_context(value: Any) -> list[str]:
    if value is None:
        return []
    s = str(value).strip()
    if not s or s.lower() == "nan":
        return []
    return [x.strip().lower() for x in s.split("|") if x.strip()]


def has_chinese(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in str(text))


def is_truthy(value: Any) -> bool:
    return str(value).strip().upper() in {"TRUE", "1", "YES", "Y"}


def local_window(text: str, start: int, end: int, window: int = CONTEXT_WINDOW_CHARS) -> str:
    left = max(0, start - window)
    right = min(len(text), end + window)
    return text[left:right]


def contains_any(text: str, phrases: list[str]) -> bool:
    if not phrases:
        return False
    t = text.lower()
    return any(p and p in t for p in phrases)


# ─────────────────────────────────────────────────────────────
# Alias loading
# ─────────────────────────────────────────────────────────────

@lru_cache(maxsize=4)
def load_skill_aliases(alias_path_str: str) -> pd.DataFrame:
    alias_path = Path(alias_path_str)
    if not alias_path.exists():
        return pd.DataFrame(columns=[
            "canonical_skill_name", "alias", "alias_type", "is_regex",
            "requires_context", "priority", "positive_context", "negative_context",
            "ambiguity_score", "match_mode",
        ])

    df = pd.read_csv(alias_path, encoding="utf-8-sig").fillna("")

    required_cols = {"canonical_skill_name", "alias"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"skill_alias.csv missing required columns: {missing}")

    # Backward-compatible defaults if the CSV has not yet been upgraded.
    defaults = {
        "alias_type": "exact",
        "is_regex": "FALSE",
        "requires_context": "FALSE",
        "priority": 50,
        "positive_context": "",
        "negative_context": "",
        "ambiguity_score": 1,
        "match_mode": "phrase_boundary",
    }
    for col, default in defaults.items():
        if col not in df.columns:
            df[col] = default

    for col in ["canonical_skill_name", "alias", "alias_type", "is_regex", "requires_context", "positive_context", "negative_context", "match_mode"]:
        df[col] = df[col].astype(str).str.strip()

    df["priority"] = pd.to_numeric(df["priority"], errors="coerce").fillna(50)
    df["alias_len"] = df["alias"].astype(str).str.len()

    # Full phrases and high-priority aliases first; this helps stable ordering.
    df = df.sort_values(["priority", "alias_len"], ascending=[False, False]).reset_index(drop=True)
    return df


# ─────────────────────────────────────────────────────────────
# Pattern builder + context guard
# ─────────────────────────────────────────────────────────────

def build_alias_pattern(alias: str, is_regex: bool = False, match_mode: str = "") -> str | None:
    if not alias:
        return None

    a = str(alias).strip().lower()
    if not a:
        return None

    # CSV-provided regex, e.g. \bml\b
    if is_regex or "\\b" in a or "(?<" in a or "(?=" in a or "(?!" in a:
        return a

    if a in SPECIAL_ALIAS_PATTERNS:
        return SPECIAL_ALIAS_PATTERNS[a]

    # Chinese aliases do not have word boundaries.
    if has_chinese(a):
        return re.escape(a).replace(r"\ ", r"\s*")

    # Short ASCII aliases must use strict token boundaries.
    compact = re.sub(r"[^a-z0-9+#]", "", a)
    if len(compact) <= 3 and re.fullmatch(r"[a-z0-9+#]+", compact):
        return rf"(?<![{TOKEN_BOUNDARY}]){re.escape(a)}(?![{TOKEN_BOUNDARY}])"

    # General phrase boundary. Spaces can vary.
    escaped = re.escape(a).replace(r"\ ", r"\s+")
    return rf"(?<![{TOKEN_BOUNDARY}]){escaped}(?![{TOKEN_BOUNDARY}])"


def row_passes_context_guard(row: pd.Series, norm_text: str, match_start: int, match_end: int) -> bool:
    requires_context = is_truthy(row.get("requires_context", "FALSE"))
    positive = split_context(row.get("positive_context", ""))
    negative = split_context(row.get("negative_context", ""))

    if not requires_context and not negative:
        return True

    snippet = local_window(norm_text, match_start, match_end)

    # Negative context only checks near the match, not whole CV.
    # This avoids rejecting a valid NGS mention just because another section says "meetings".
    if negative and contains_any(snippet, negative):
        return False

    if requires_context:
        # If context is required but no positive context is provided, keep it conservative.
        if not positive:
            return False
        return contains_any(snippet, positive)

    return True


def safe_alias_matches(row: pd.Series, norm_text: str) -> list[re.Match]:
    alias = str(row.get("alias", "")).strip()
    if not alias or not norm_text:
        return []

    pattern = build_alias_pattern(
        alias,
        is_regex=is_truthy(row.get("is_regex", "FALSE")),
        match_mode=str(row.get("match_mode", "")),
    )
    if not pattern:
        return []

    try:
        matches = list(re.finditer(pattern, norm_text, flags=re.IGNORECASE))
    except re.error:
        # Fall back to escaped phrase boundary if a CSV regex is malformed.
        fallback = build_alias_pattern(re.escape(alias), is_regex=False)
        if not fallback:
            return []
        matches = list(re.finditer(fallback, norm_text, flags=re.IGNORECASE))

    return [m for m in matches if row_passes_context_guard(row, norm_text, m.start(), m.end())]


# ─────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────

def extract_skills_from_text(text: str, alias_path: str | Path | None = None) -> list[str]:
    """Extract canonical skills from free text.

    Important behavior:
    - No naive substring matching.
    - Short aliases like ngs / cv / ds / ai require strict boundaries and context.
    - Special skills like C++ use escaped symbol-safe regex.
    """
    if not text or not str(text).strip():
        return []

    if alias_path is None:
        alias_path = project_root() / "skill_alias.csv"

    alias_df = load_skill_aliases(str(Path(alias_path)))
    if alias_df.empty:
        return []

    norm_text = normalize_text_for_match(text)
    matched: list[str] = []
    best_seen: dict[str, float] = {}

    for _, row in alias_df.iterrows():
        canonical = str(row.get("canonical_skill_name", "")).strip()
        if not canonical:
            continue

        found = safe_alias_matches(row, norm_text)
        if not found:
            continue

        priority = float(row.get("priority", 50) or 50)
        if canonical not in best_seen or priority > best_seen[canonical]:
            best_seen[canonical] = priority
            if canonical not in matched:
                matched.append(canonical)

    # Return by best evidence priority, stable enough for UI.
    matched = sorted(matched, key=lambda sk: best_seen.get(sk, 0), reverse=True)
    return matched


def build_role_skill_demand_from_db(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Build role -> skill demand profile from Supabase job rows.

    Expected row keys:
    - role_normalized
    - skill_canonical: list[str]
    """
    role_skill_counts: dict[str, Counter] = defaultdict(Counter)
    role_sample_size: Counter = Counter()

    for r in rows or []:
        role = r.get("role_normalized") if isinstance(r, dict) else None
        if not role or role == "Unclassified":
            continue

        role_sample_size[role] += 1
        skills = r.get("skill_canonical", []) or []
        if not isinstance(skills, list):
            continue

        # De-duplicate within each posting so repeated skills in one JD do not overcount.
        for sk in set(str(x).strip() for x in skills if str(x).strip()):
            role_skill_counts[role][sk] += 1

    demand = {}
    for role, counter in role_skill_counts.items():
        sample_size = max(role_sample_size.get(role, 1), 1)
        skill_weights = {sk: cnt / sample_size for sk, cnt in counter.items()}
        demand[role] = {
            "skill_weights": skill_weights,
            "sample_size": sample_size,
        }

    return demand


def compute_fit_scores(cv_skills: list[str], role_skill_demand: dict[str, Any], top_n: int = 20) -> list[dict[str, Any]]:
    """Compute fit scores between detected CV skills and role demand.

    Compatible with both:
    - {role: {"skill_weights": {...}, "sample_size": n}}
    - {role: {skill: weight}}
    - {role: [skill1, skill2]}
    """
    cv_set = set(cv_skills or [])
    results = []

    for role, demand in (role_skill_demand or {}).items():
        sample_size = 0

        if isinstance(demand, dict) and "skill_weights" in demand:
            skill_weights = demand.get("skill_weights", {}) or {}
            sample_size = int(demand.get("sample_size", 0) or 0)
        elif isinstance(demand, dict):
            skill_weights = demand
        else:
            skill_weights = {sk: 1.0 for sk in (demand or [])}

        if not skill_weights:
            continue

        total_weight = sum(float(w) for w in skill_weights.values()) or 1.0
        matched = [sk for sk in skill_weights if sk in cv_set]
        gaps = [sk for sk in skill_weights if sk not in cv_set]
        matched_weight = sum(float(skill_weights.get(sk, 0)) for sk in matched)

        fit_score = min(matched_weight / total_weight, 1.0)

        results.append({
            "role": role,
            "fit_score": fit_score,
            "matched_skills": sorted(matched, key=lambda sk: skill_weights.get(sk, 0), reverse=True),
            "gap_skills": sorted(gaps, key=lambda sk: skill_weights.get(sk, 0), reverse=True),
            "sample_size": sample_size,
        })

    return sorted(results, key=lambda x: x["fit_score"], reverse=True)[:top_n]
