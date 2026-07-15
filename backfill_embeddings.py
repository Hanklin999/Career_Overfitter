#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 job_posting 裡還沒算過 embedding 的資料，批次呼叫 Gemini embedding API
算好寫回去。

第一次執行：所有既有資料都還沒有 embedding，視資料量可能要跑好幾次
（每次用 --limit 控制數量）。之後建議接在 cleaner.py 後面定期跑，
只會處理新進來、embedding 還是 NULL 的資料，不會重算已經算過的。

前提：要先在 Supabase 執行 sql/001_enable_pgvector_rag.sql，
job_posting 才會有 embedding 這個欄位。
"""

import argparse
import time
from pathlib import Path
from typing import Dict, List

import requests
from dotenv import load_dotenv
import os
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from utils.embeddings import embed_texts_batch, is_configured  # noqa: E402

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Missing SUPABASE_URL or SUPABASE_KEY")

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

# 一次送給 Gemini batchEmbedContents 的筆數，留點安全邊界，不要單批太大。
EMBED_BATCH_SIZE = 20


def fetch_rows_missing_embedding(limit: int) -> List[Dict]:
    resp = requests.get(
        f"{SUPABASE_URL}/job_posting",
        headers=HEADERS,
        params={
            "select": "job_no,title_clean,role_normalized,job_parent_category,skill_canonical,job_description",
            "embedding": "is.null",
            "job_description": "not.is.null",
            "limit": str(limit),
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json() or []


def build_embed_text(row: Dict) -> str:
    skills = row.get("skill_canonical")
    skills_text = ", ".join(skills) if isinstance(skills, list) else ""
    parts = [
        row.get("title_clean") or "",
        row.get("role_normalized") or "",
        row.get("job_parent_category") or "",
        skills_text,
        (row.get("job_description") or "")[:4000],
    ]
    return "\n".join(p for p in parts if p)


def update_embedding(job_no: str, embedding: List[float]) -> bool:
    resp = requests.patch(
        f"{SUPABASE_URL}/job_posting",
        headers={**HEADERS, "Prefer": "return=minimal"},
        params={"job_no": f"eq.{job_no}"},
        json={"embedding": embedding},
        timeout=30,
    )
    return resp.status_code in (200, 204)


def chunked(seq: List, size: int):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Backfill job_posting.embedding via Gemini")
    p.add_argument("--limit", type=int, default=200, help="這次最多處理幾筆")
    return p.parse_args()


def main() -> None:
    if not is_configured():
        raise RuntimeError("缺少 GEMINI_API_KEY，無法算 embedding")

    args = parse_args()
    rows = fetch_rows_missing_embedding(args.limit)
    print(f"待算 embedding：{len(rows)} 筆")

    ok = fail = 0
    for batch in chunked(rows, EMBED_BATCH_SIZE):
        texts = [build_embed_text(r) for r in batch]
        embeddings = embed_texts_batch(texts, task_type="RETRIEVAL_DOCUMENT")

        for row, emb in zip(batch, embeddings):
            job_no = row.get("job_no")
            if emb and update_embedding(job_no, emb):
                ok += 1
            else:
                fail += 1
                print(f"❌ {job_no} embedding 失敗")

        # 對 Gemini embedding API 客氣一點，避免瞬間把免費額度的 rate limit 打爆
        time.sleep(1)

    print(f"✅ 完成：成功 {ok}，失敗 {fail}")


if __name__ == "__main__":
    main()
