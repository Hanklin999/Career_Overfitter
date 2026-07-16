#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CV Fit 分析用的 RAG 檢索。

流程：把使用者履歷 / 目標 role 轉成 embedding -> 呼叫 Supabase 的
match_job_postings RPC（見 sql/001_enable_pgvector_rag.sql）-> 找出最相似的
真實 job_posting -> 整理成文字片段，讓 llm_advisor.generate_ai_advice()
塞進 Gemini prompt 當作 grounding context，取代原本純靠統計權重腦補建議。

任何一步失敗（沒設定 API key、Supabase 還沒跑 migration、RPC 呼叫失敗）都
回傳空結果，呼叫端要能在沒有檢索結果時照常運作、不阻斷主流程。
"""

import os
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv

from utils.embeddings import embed_text
from utils.embeddings import is_configured as embeddings_configured

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

HEADERS = {
    "apikey": SUPABASE_KEY,
    # 新版 sb_secret_... key 不是 JWT，不能塞進 Authorization: Bearer header
    # （會被 PostgREST 判定不合法直接 401），只需要 apikey header。
    "Content-Type": "application/json",
}


def is_available() -> bool:
    """RAG 檢索需要同時具備：Supabase 連線設定 + Gemini API key。"""
    return bool(SUPABASE_URL and SUPABASE_KEY and embeddings_configured())


def retrieve_similar_jobs(
    query_text: str,
    role_filter: Optional[str] = None,
    match_count: int = 5,
    timeout: int = 30,
) -> List[Dict[str, Any]]:
    """
    回傳最相似的真實職缺列表，每筆包含：
    job_no / title_clean / role_normalized / job_parent_category /
    job_description / similarity

    失敗一律回傳空 list，不丟例外。
    """
    if not is_available() or not query_text or not query_text.strip():
        return []

    query_embedding = embed_text(query_text, task_type="RETRIEVAL_QUERY")
    if not query_embedding:
        return []

    try:
        resp = requests.post(
            f"{SUPABASE_URL}/rpc/match_job_postings",
            headers=HEADERS,
            json={
                "query_embedding": query_embedding,
                "match_count": match_count,
                "filter_role": role_filter,
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        result = resp.json()
        return result if isinstance(result, list) else []
    except Exception as e:
        print(f"[rag_retrieval] retrieve_similar_jobs failed: {e}")
        return []


def format_retrieved_context(
    jobs: List[Dict[str, Any]],
    max_chars_per_job: int = 600,
) -> str:
    """把檢索到的職缺整理成可以直接塞進 Gemini prompt 的文字區塊。"""
    if not jobs:
        return ""

    blocks = []
    for i, job in enumerate(jobs, 1):
        desc = (job.get("job_description") or "")[:max_chars_per_job]
        similarity = job.get("similarity")
        similarity_txt = f"{similarity:.2f}" if isinstance(similarity, (int, float)) else "—"
        blocks.append(
            f"[參考職缺 {i}] {job.get('title_clean', '未知職稱')}"
            f"（角色分類：{job.get('role_normalized') or '未分類'}，"
            f"相似度：{similarity_txt}）\n{desc}"
        )
    return "\n\n".join(blocks)
