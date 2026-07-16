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
        "enabled": "TRUE",
    }
    for col, default in defaults.items():
        if col not in df.columns:
            df[col] = default

    for col in ["canonical_skill_name", "alias", "alias_type", "is_regex", "requires_context", "positive_context", "negative_context", "match_mode", "enabled"]:
        df[col] = df[col].astype(str).str.strip()

    # Respect optional enabled flag in upgraded skill_alias.csv.
    # Disabled aliases are removed at load time so old extraction logic cannot accidentally use them.
    if "enabled" in df.columns:
        df = df[df["enabled"].astype(str).str.strip().str.upper().isin({"TRUE", "1", "YES", "Y"})].copy()

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


# ---------------------------------------------------------------------------
# 規則式改寫建議用：從履歷全文挑出「看起來像經歷 bullet」的行
# ---------------------------------------------------------------------------

_PHONE_RE = re.compile(r"(\+?\d[\d\-\s]{7,}\d)")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")

# 常見的「工作經歷 / 專案經驗」章節標題，找到之後從下一行開始找 bullet，
# 避開履歷最上面姓名 / 地址 / 電話這種抬頭資訊。
_EXPERIENCE_SECTION_KEYWORDS = (
    "工作經歷", "工作經驗", "專業經歷", "職涯經歷", "專案經驗", "相關經驗",
    "Experience", "Employment", "Work History", "Professional Experience",
    "Projects", "Project Experience",
)

_BULLET_MARKERS = ("•", "-", "‣", "▪", "◦", "*", "●", "·")
_ACTION_HINTS = (
    "負責", "執行", "開發", "分析", "建置", "設計", "優化", "提升", "管理",
    "帶領", "完成", "協助", "推動", "規劃", "導入", "維護", "撰寫", "整合",
    "led", "built", "developed", "designed", "improved", "managed", "analyzed",
    "implemented", "launched", "reduced", "increased", "optimized",
)

# 「July 2019 ~ 現在」「May 2016 ~ June 2019」「2019 - Present」「2012 - 2014」
# 這類日期區間，是經歷條目的結構性資訊，不是成果描述。
_DATE_RANGE_RE = re.compile(
    r"(19|20)\d{2}.{0,15}(~|-|–|至|to)\s*.{0,15}"
    r"((19|20)\d{2}|現在|至今|Present|present|Now|now)"
)


def _looks_like_entry_meta_line(line: str) -> bool:
    """
    判斷是不是履歷經歷條目裡的『結構性資訊』行，例如：
        'Lead Data Analyst • 104人力銀行'        （職稱 • 公司）
        'July 2019 ~ 現在・7年 1個月 | 台北市'    （日期區間 | 地點）
    這種行只是排版上的抬頭／中繼資料，本身沒有「做了什麼」的內容，
    套用「補量化成果」的改寫建議沒有意義，長度雖然常常超過 20 字
    但不該被當成 bullet。

    判斷依據：
    1. 如果行本身就是以 bullet 符號開頭（例如「• 管理並指導...」），代表
       這是明確的列點格式，不是標題分隔符，直接視為非 meta 行
    2. 符合日期區間的樣式（年份 + ~/-/至 + 年份或「現在」）
    3. 或是含有「•」「｜」「|」這種行內分隔符，且沒有逗號類分句標點、
       也不是以中文句尾標點結尾——代表比較像「職稱 • 公司」這種標題
       格式，不是完整敘述句。

       注意：這裡刻意不用「有沒有含動詞字樣」來判斷，因為中文職稱本身
       常常就包含「分析」「設計」「管理」這些字（例如「數據分析師」），
       用動詞字樣比對職稱行會誤判成不是 meta 行。改用「有沒有逗號分句」
       更可靠：真正的成果描述幾乎都是「做了什麼，達成了什麼」的逗號
       分句格式，職稱/公司抬頭通常沒有逗號。
    """
    stripped = line.strip()
    if stripped.startswith(_BULLET_MARKERS):
        return False

    if _DATE_RANGE_RE.search(stripped):
        return True

    has_inline_separator = any(sep in stripped for sep in ("•", "·", "｜", "|"))
    has_clause_punct = any(p in stripped for p in ("，", "、", ","))
    ends_like_sentence = stripped.endswith(("。", "！", "!", "."))
    if has_inline_separator and not has_clause_punct and not ends_like_sentence:
        return True

    return False


def _looks_like_header_line(line: str) -> bool:
    """判斷是不是姓名 / 電話 / email / 地址這類履歷抬頭資訊，不是經歷 bullet。"""
    stripped = line.strip()
    if not stripped:
        return True
    if _EMAIL_RE.search(stripped):
        return True
    # 電話號碼：一串數字為主的短行（避免誤判含數字的正常 bullet，例如
    # 「提升轉換率 15%」，所以只在整行夠短時才判定為電話）
    if len(stripped) <= 20 and _PHONE_RE.search(stripped):
        return True
    # 短行（<=12 字）又沒有任何數字或行動詞，多半是姓名或地址片段
    if len(stripped) <= 12 and not any(ch.isdigit() for ch in stripped):
        if not any(h in stripped for h in _ACTION_HINTS):
            return True
    return False


def select_resume_bullets(cv_text: str, max_bullets: int = 3) -> list[str]:
    """
    從履歷全文挑出適合拿去做規則式改寫建議的「經歷 bullet」，
    取代原本直接抓「前 N 個非空行」的做法（那樣永遠抓到姓名/地址/電話）。

    策略：
    1. 過濾掉明顯是聯絡資訊 / 抬頭的行
    2. 如果找得到「工作經歷 / 專案經驗」之類的章節標題，優先從標題之後找
    3. 判斷一行像不像 bullet：有 bullet 符號開頭、含常見經歷動詞、
       或長度夠長（>=20 字，通常代表有實質內容而非單一詞語）
    4. 全部被濾掉時 fallback：退回用最長的幾行（至少不要開天窗）
    """
    lines = [ln.strip() for ln in cv_text.splitlines() if ln.strip()]
    if not lines:
        return []

    start_idx = 0
    for i, ln in enumerate(lines):
        if any(kw in ln for kw in _EXPERIENCE_SECTION_KEYWORDS):
            start_idx = i + 1
            break

    candidates = lines[start_idx:] if start_idx else lines

    bullets: list[str] = []
    for ln in candidates:
        if _looks_like_header_line(ln) or _looks_like_entry_meta_line(ln):
            continue
        is_bulletish = (
            ln.startswith(_BULLET_MARKERS)
            or any(h in ln for h in _ACTION_HINTS)
            or len(ln) >= 20
        )
        if is_bulletish:
            bullets.append(ln)
        if len(bullets) >= max_bullets:
            break

    if not bullets:
        # 找不到明顯 bullet 時，至少避免開天窗：退回用非抬頭/非結構性行裡最長的幾行
        non_header = [
            ln for ln in candidates
            if not _looks_like_header_line(ln) and not _looks_like_entry_meta_line(ln)
        ] or candidates
        bullets = sorted(non_header, key=len, reverse=True)[:max_bullets]

    return bullets


# ---------------------------------------------------------------------------
# Bullet 檢查器：把履歷拆成「經歷條目 → 底下的 bullet」，並對每條 bullet
# 做「有沒有量化成果 / 有沒有具體影響」的規則式檢查。
# ---------------------------------------------------------------------------

# 經歷區塊的結束點：出現這些關鍵字代表已經跳到學歷/技能/語言等其他章節，
# 不該再繼續往下抓 bullet。
_SECTION_END_KEYWORDS = (
    "學歷", "教育背景", "技能", "證照", "資格認證", "語言能力", "語言",
    "Education", "Skills", "Certifications", "Certificates", "Languages",
)


def extract_experience_entries(
    cv_text: str,
    max_entries: int = 6,
    max_bullets_per_entry: int = 6,
) -> list[dict]:
    """
    把履歷解析成「經歷條目」結構：每個條目有一個標題（職稱/公司行）跟底下
    對應的 bullet 清單，例如：
        [{"title": "Lead Data Analyst • 104人力銀行",
          "bullets": ["管理並指導七人分析團隊...", "利用 Python 與 R ..."]},
         {"title": "資深數據分析師 • 蝦皮購物", "bullets": [...]}]

    跟 select_resume_bullets() 用同一套行分類規則（header / 日期區間 /
    職稱・公司 / bullet），差別是這裡保留「哪個標題底下接哪些 bullet」的
    分組關係，讓 UI 可以照「經驗 1 / 經驗 2 / ...」分段顯示，而不是把全
    履歷的 bullet 打散成一個扁平清單。

    遇到學歷/技能/語言等章節關鍵字就停止（經歷區塊視為結束）。
    """
    lines = [ln.strip() for ln in cv_text.splitlines() if ln.strip()]
    if not lines:
        return []

    start_idx = 0
    for i, ln in enumerate(lines):
        if any(kw in ln for kw in _EXPERIENCE_SECTION_KEYWORDS):
            start_idx = i + 1
            break

    candidates = lines[start_idx:] if start_idx else lines

    entries: list[dict] = []
    current: dict | None = None

    for ln in candidates:
        if any(kw in ln for kw in _SECTION_END_KEYWORDS):
            break

        if _looks_like_header_line(ln):
            continue

        if _DATE_RANGE_RE.search(ln):
            continue  # 日期/地點行，不顯示，也不是新條目的標題

        has_inline_separator = any(sep in ln for sep in ("•", "·", "｜", "|"))
        has_clause_punct = any(p in ln for p in ("，", "、", ","))
        ends_like_sentence = ln.endswith(("。", "！", "!", "."))
        is_entry_title = (
            not ln.startswith(_BULLET_MARKERS)
            and has_inline_separator
            and not has_clause_punct
            and not ends_like_sentence
        )

        if is_entry_title:
            if len(entries) >= max_entries:
                break
            current = {"title": ln, "bullets": []}
            entries.append(current)
            continue

        is_bulletish = (
            ln.startswith(_BULLET_MARKERS)
            or any(h in ln for h in _ACTION_HINTS)
            or len(ln) >= 20
        )
        if not is_bulletish:
            continue

        if current is None:
            # 履歷開頭的自我介紹段落，還沒遇到任何「職稱 • 公司」標題行
            # 就先出現看起來像 bullet 的句子，歸到一個沒有標題的條目
            current = {"title": None, "bullets": []}
            entries.append(current)

        if len(current["bullets"]) < max_bullets_per_entry:
            current["bullets"].append(ln)

    return [e for e in entries if e["bullets"]]


# 量化成果偵測：阿拉伯數字或中文數字 + 常見單位（%、人、個、次、萬、成...），
# 或是獨立的兩位數以上數字（例如「提升 18」「節省 500」）。
_QUANT_UNIT_RE = re.compile(
    r"[0-9一二三四五六七八九十百千萬億]+\s*"
    r"(%|％|倍|萬|億|人|次|個|件|小時|天|週|月|年|元|成|折|美元|新台幣)"
)
_PERCENT_RE = re.compile(r"\d+(\.\d+)?\s*%")
_BARE_NUMBER_RE = re.compile(r"(?<![A-Za-z])\d{2,}(?![A-Za-z])")

# 具體影響：描述「造成的改變/成效」的動詞，跟單純列工具名稱（例如「熟悉
# SQL」）區分開來。
_IMPACT_HINTS = (
    "提升", "降低", "減少", "增加", "改善", "優化", "節省", "縮短", "增長",
    "提高", "達成", "超越", "成長", "擴大", "縮減", "促進",
    "increase", "decrease", "reduce", "improve", "save", "grow", "boost",
    "cut", "lower", "raise",
)


def check_bullet_quality(bullet: str) -> dict:
    """
    對單一 bullet 做兩項規則式檢查（純字串比對，不牽涉 LLM）：
    - has_quantified_result：有沒有具體數字/百分比/量級
      （例如「18%」「七人」「500 萬元」「四成」）
    - has_concrete_impact：有沒有描述「造成的改變/成效」的動詞
      （提升、降低、節省...），而不只是列出用了什麼工具

    這兩項合起來大致對應「做了什麼＋影響了什麼指標」這個好 bullet 的
    判斷標準；兩項都沒有的 bullet，代表比較像是在列工作內容而非成果，
    值得優先改寫。
    """
    has_quant = bool(
        _QUANT_UNIT_RE.search(bullet)
        or _PERCENT_RE.search(bullet)
        or _BARE_NUMBER_RE.search(bullet)
    )
    has_impact = any(h in bullet for h in _IMPACT_HINTS)
    return {
        "has_quantified_result": has_quant,
        "has_concrete_impact": has_impact,
    }
