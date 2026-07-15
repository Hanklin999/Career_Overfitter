#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gemini embedding 共用工具。

用同一組 GEMINI_API_KEY 打 Gemini 的 embedContent / batchEmbedContents，
不需要另外申請帳號或裝 SDK，維持跟 llm_advisor.py 一樣「純 requests」的風格。

用途：
- embed_text(): embed 單一段文字，用在使用者查詢（CV 內容 / 搜尋字串）
- embed_texts_batch(): 一次 embed 多段文字，用在 backfill_embeddings.py
  批次處理既有的 job_posting 資料

兩個函式失敗時都不丟例外，回傳 None（或對應長度、內容是 None 的 list），
呼叫端要能在沒有 embedding 時照常運作（純 fallback，不阻斷主流程）。
"""

import os
from typing import List, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
EMBEDDING_MODEL = os.environ.get("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
EMBEDDING_DIM = int(os.environ.get("GEMINI_EMBEDDING_DIM", "768"))

BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

# 送進 embedding API 的文字上限，避免超長 job_description 把單次呼叫拖垮。
MAX_EMBED_CHARS = 8000


def is_configured() -> bool:
    return bool(GEMINI_API_KEY)


def embed_text(
    text: str,
    task_type: str = "RETRIEVAL_QUERY",
    timeout: int = 30,
) -> Optional[List[float]]:
    """embed 單一段文字。失敗回傳 None。"""
    if not is_configured() or not text or not text.strip():
        return None

    try:
        resp = requests.post(
            f"{BASE_URL}/{EMBEDDING_MODEL}:embedContent",
            params={"key": GEMINI_API_KEY},
            json={
                "content": {"parts": [{"text": text[:MAX_EMBED_CHARS]}]},
                "taskType": task_type,
                "outputDimensionality": EMBEDDING_DIM,
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        values = (data.get("embedding") or {}).get("values")
        return values if isinstance(values, list) else None
    except Exception as e:
        print(f"[embeddings] embed_text failed: {e}")
        return None


def embed_texts_batch(
    texts: List[str],
    task_type: str = "RETRIEVAL_DOCUMENT",
    timeout: int = 60,
) -> List[Optional[List[float]]]:
    """
    一次 embed 多段文字（batchEmbedContents）。

    回傳跟輸入等長的 list；整批呼叫失敗時全部回傳 None，呼叫端要逐項檢查、
    不要假設每個位置一定有值。
    """
    if not is_configured() or not texts:
        return [None] * len(texts)

    requests_payload = [
        {
            "model": f"models/{EMBEDDING_MODEL}",
            "content": {"parts": [{"text": (t or "")[:MAX_EMBED_CHARS]}]},
            "taskType": task_type,
            "outputDimensionality": EMBEDDING_DIM,
        }
        for t in texts
    ]

    try:
        resp = requests.post(
            f"{BASE_URL}/{EMBEDDING_MODEL}:batchEmbedContents",
            params={"key": GEMINI_API_KEY},
            json={"requests": requests_payload},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        embeddings = data.get("embeddings") or []
        if len(embeddings) != len(texts):
            print(
                f"[embeddings] batch size mismatch: sent {len(texts)}, got {len(embeddings)}"
            )
            return [None] * len(texts)
        return [e.get("values") if isinstance(e, dict) else None for e in embeddings]
    except Exception as e:
        print(f"[embeddings] embed_texts_batch failed: {e}")
        return [None] * len(texts)
