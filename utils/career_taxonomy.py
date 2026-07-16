#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
utils/career_taxonomy.py
Analytics Career Map — 分類 overlay

把 job_posting.role_normalized 對應到「Google Maps for Analytics Careers」
需要的兩個軸：
  domain      業務應用領域（Business / Product / Marketing / Operations Analytics）
  tech_depth  工程深度（BA → DA → DS → DE，由淺入深）

這一層只是「疊加在既有分類之上的顯示層」：不會改變 cleaner.py 的分類邏輯，
只是把 job_posting 裡本來就有的 role_normalized 值，重新組織成使用者好理解的
職涯地圖。資料來源是 analytics_career_map.csv（role_normalized → domain,
tech_depth），只涵蓋「分析類」職稱 — 也就是說，不在這份表裡的職稱
（例如 Product Manager、Sales Associate）不會出現在 Analytics Career Map，
這是刻意的：地圖的目的是讓使用者找到「藏在各種職稱底下的分析工作」，
不是變成一個全職能地圖。
"""

import os
from collections import Counter, defaultdict
from typing import Dict, List, Optional

import pandas as pd

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAP_PATH = os.path.join(_HERE, "analytics_career_map.csv")

DOMAIN_ORDER = [
    "Business Analytics",
    "Product Analytics",
    "Marketing Analytics",
    "Operations Analytics",
]

DOMAIN_LABEL_ZH = {
    "Business Analytics": "商業分析",
    "Product Analytics": "產品分析",
    "Marketing Analytics": "行銷分析",
    "Operations Analytics": "營運分析",
}

TECH_DEPTH_ORDER = ["BA", "DA", "DS", "DE"]

TECH_DEPTH_LABEL = {
    "BA": "Business Analyst",
    "DA": "Data Analyst",
    "DS": "Data Scientist",
    "DE": "Data Engineer",
}

TECH_DEPTH_RANK = {label: i for i, label in enumerate(TECH_DEPTH_ORDER)}

# "What do people actually do?" — 每個 domain 的定性描述（先於任何 job list 出現）
DOMAIN_WHAT_THEY_DO = {
    "Business Analytics": [
        "把原始商業數據轉換成給主管的具體建議",
        "建立並維護 BI 儀表板與週期性報表",
        "建構預算、財務預測與單位經濟模型（FP&A / RevOps）",
        "把模糊的商業問題轉換成有結構的分析",
        "向非技術背景的利害關係人簡報分析結果",
    ],
    "Product Analytics": [
        "分析使用者行為",
        "設計實驗（A/B Test）",
        "定義產品指標",
        "與 PM 密切合作",
        "驅動產品決策",
    ],
    "Marketing Analytics": [
        "衡量行銷活動與渠道成效",
        "分析顧客分群與行為模式",
        "執行並解讀市場／消費者研究",
        "把營收歸因到不同行銷投放",
        "建議行銷預算該往哪裡投",
    ],
    "Operations Analytics": [
        "分析流程效率與瓶頸",
        "預測需求、規劃庫存與供應",
        "追蹤跨team的營運關鍵指標",
        "支援流程改善專案",
        "為物流／供應鏈決策建立報表",
    ],
}

DOMAIN_TAGLINE = {
    "Business Analytics": "用數據支援商業決策 — 從報表、預算到策略分析",
    "Product Analytics": "用數據驅動產品決策 — 從用戶行為到實驗設計",
    "Marketing Analytics": "用數據驅動行銷投資 — 從成效衡量到顧客洞察",
    "Operations Analytics": "用數據優化營運流程 — 從供應鏈到需求預測",
}


def _load_map() -> pd.DataFrame:
    df = pd.read_csv(MAP_PATH, encoding="utf-8-sig").fillna("")
    df["role_normalized"] = df["role_normalized"].str.strip()
    df["domain"] = df["domain"].str.strip()
    df["tech_depth"] = df["tech_depth"].str.strip()
    return df


_MAP_DF = _load_map()
_ROLE_TO_DOMAIN: Dict[str, str] = dict(zip(_MAP_DF["role_normalized"], _MAP_DF["domain"]))
_ROLE_TO_DEPTH: Dict[str, str] = dict(zip(_MAP_DF["role_normalized"], _MAP_DF["tech_depth"]))
_DOMAIN_TO_ROLES: Dict[str, List[str]] = defaultdict(list)
for _, _row in _MAP_DF.iterrows():
    _DOMAIN_TO_ROLES[_row["domain"]].append(_row["role_normalized"])


def get_domain(role_normalized: Optional[str]) -> Optional[str]:
    if not role_normalized:
        return None
    return _ROLE_TO_DOMAIN.get(role_normalized.strip())


def get_tech_depth(role_normalized: Optional[str]) -> Optional[str]:
    if not role_normalized:
        return None
    return _ROLE_TO_DEPTH.get(role_normalized.strip())


def is_analytics_role(role_normalized: Optional[str]) -> bool:
    return get_domain(role_normalized) is not None


def list_domains() -> List[str]:
    return list(DOMAIN_ORDER)


def list_roles_in_domain(domain: str) -> List[str]:
    return sorted(_DOMAIN_TO_ROLES.get(domain, []))


def annotate_rows(rows: List[Dict]) -> List[Dict]:
    """幫一批 job_posting rows 加上 domain / tech_depth 欄位，
    並濾掉不在 Analytics Career Map 涵蓋範圍內的職稱。"""
    out = []
    for r in rows:
        role = r.get("role_normalized")
        domain = get_domain(role)
        if not domain:
            continue
        r = dict(r)
        r["career_domain"] = domain
        r["career_tech_depth"] = get_tech_depth(role)
        out.append(r)
    return out


def build_landscape(rows: List[Dict]) -> List[Dict]:
    """給 Explore Careers 頁面用的 XY 市場分布資料：
    每一列是 (domain, tech_depth) 的組合，count = 落在這個象限的職缺數。"""
    annotated = annotate_rows(rows)
    counter = Counter((r["career_domain"], r["career_tech_depth"]) for r in annotated)
    out = []
    for domain in DOMAIN_ORDER:
        for depth in TECH_DEPTH_ORDER:
            out.append({
                "domain": domain,
                "tech_depth": depth,
                "tech_depth_label": TECH_DEPTH_LABEL[depth],
                "count": counter.get((domain, depth), 0),
            })
    return out


def build_role_summary(rows: List[Dict], domain: Optional[str] = None) -> List[Dict]:
    """依 role_normalized 彙整：職缺數、中位數薪資、Top skills、Top companies。
    可選擇只看某個 domain。"""
    annotated = annotate_rows(rows)
    if domain:
        annotated = [r for r in annotated if r["career_domain"] == domain]

    by_role: Dict[str, List[Dict]] = defaultdict(list)
    for r in annotated:
        by_role[r["role_normalized"]].append(r)

    summaries = []
    for role, items in by_role.items():
        salaries = sorted(
            i["salary_low"] for i in items
            if isinstance(i.get("salary_low"), (int, float)) and i.get("salary_low")
        )
        median_salary = salaries[len(salaries) // 2] if salaries else None

        skill_counter: Counter = Counter()
        for i in items:
            skills = i.get("skill_canonical") or []
            if isinstance(skills, list):
                skill_counter.update(skills)

        company_counter: Counter = Counter()
        for i in items:
            c = i.get("company_clean")
            if c:
                company_counter[c] += 1

        summaries.append({
            "role_normalized": role,
            "domain": get_domain(role),
            "tech_depth": get_tech_depth(role),
            "count": len(items),
            "median_salary": median_salary,
            "top_skills": [s for s, _ in skill_counter.most_common(8)],
            "top_companies": [c for c, _ in company_counter.most_common(6)],
            "jobs": items,
        })

    summaries.sort(key=lambda s: s["count"], reverse=True)
    return summaries


def build_skill_matrix(rows: List[Dict], top_n_skills: int = 12) -> Dict:
    """Compare Career Paths 用：skill x domain 的星等矩陣（1~5 顆星）。
    星等 = 該 domain 內含有此技能的職缺比例，分 5 個等第。"""
    annotated = annotate_rows(rows)

    domain_counts = Counter(r["career_domain"] for r in annotated)
    skill_domain_counts: Dict[str, Counter] = {d: Counter() for d in DOMAIN_ORDER}

    overall_skill_counter: Counter = Counter()
    for r in annotated:
        skills = r.get("skill_canonical") or []
        if not isinstance(skills, list):
            continue
        overall_skill_counter.update(set(skills))
        for s in set(skills):
            skill_domain_counts[r["career_domain"]][s] += 1

    top_skills = [s for s, _ in overall_skill_counter.most_common(top_n_skills)]

    def stars(skill: str, domain: str) -> int:
        total = domain_counts.get(domain, 0)
        if not total:
            return 0
        ratio = skill_domain_counts[domain].get(skill, 0) / total
        if ratio >= 0.55:
            return 5
        if ratio >= 0.40:
            return 4
        if ratio >= 0.25:
            return 3
        if ratio >= 0.12:
            return 2
        if ratio > 0:
            return 1
        return 0

    matrix = []
    for skill in top_skills:
        row = {"skill": skill}
        for domain in DOMAIN_ORDER:
            row[domain] = stars(skill, domain)
        matrix.append(row)

    return {"skills": top_skills, "domains": DOMAIN_ORDER, "matrix": matrix}
