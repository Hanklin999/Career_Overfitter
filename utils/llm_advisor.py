#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM 輔助建議（Gemini）
================================================================
把 CV Fitting Tool 已經在算的 llm_ready_diagnosis_payload
（見 pages/3_CV_Fitting_Tool.py 的 build_llm_ready_diagnosis_payload）
送給 Gemini，換回一份結構化、個人化的中文建議：

    best_fit_role / why_fit / key_skill_evidence / biggest_gap /
    rewrite_suggestions / next_learning_actions

設計原則：
- 沒有設定 GEMINI_API_KEY -> is_configured() 回傳 False，呼叫端要 fallback
  回既有的規則式 structured diagnosis，不能讓頁面掛掉或空白。
- Gemini 回傳格式不符 / API 出錯 -> generate_ai_advice() 回傳 None，
  一樣讓呼叫端 fallback。
- 只根據傳入的 payload 做推論，不在這裡另外打 Supabase 或做爬蟲。
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_API_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
)

REQUIRED_KEYS = [
    "best_fit_role",
    "why_fit",
    "key_skill_evidence",
    "biggest_gap",
    "rewrite_suggestions",
    "next_learning_actions",
]

DEFAULT_TIMEOUT = 30


def is_configured() -> bool:
    """True 代表有設定 GEMINI_API_KEY，可以呼叫 Gemini。"""
    return bool(GEMINI_API_KEY)


def _build_prompt(payload: Dict[str, Any]) -> str:
    instruction = payload.get("llm_instruction", {}) or {}
    output_language = instruction.get("output_language", "zh-TW")
    style = instruction.get("style", "concise, practical, non-exaggerated")

    return (
        "你是一位資深職涯顧問，根據以下 JSON 診斷資料，為使用者產生履歷與職涯建議。\n"
        "只能根據資料中出現的事實與數字推論，不要虛構使用者履歷中沒有出現的技能或經歷。\n"
        f"輸出語言：{output_language}\n"
        f"語氣風格：{style}\n"
        "只回傳一個 JSON 物件，不要加上 markdown code fence，也不要有 JSON 以外的文字，"
        "物件需包含以下 key：\n"
        f"{json.dumps(REQUIRED_KEYS, ensure_ascii=False)}\n\n"
        "各 key 的內容規則：\n"
        "- best_fit_role: string，從 role_fit 中選一個最適合的職能名稱\n"
        "- why_fit: string list（2-4 條），說明為什麼 best_fit_role 適合使用者\n"
        "- key_skill_evidence: string list（3-6 條），指出履歷中最有說服力的技能證據\n"
        "- biggest_gap: string list（2-5 條），使用者最需要補強的技能缺口\n"
        "- rewrite_suggestions: list of object，每個物件包含 original / rewritten / reason 三個 "
        "string 欄位，最多 3 條；如果 payload 沒有提供可改寫的原文，回傳空 list\n"
        "- next_learning_actions: string list（3-5 條），具體、可在 1-3 個月內執行的下一步學習建議\n\n"
        "診斷資料 JSON：\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None

    cleaned = text.strip()
    cleaned = re.sub(r"^```(json)?", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()

    try:
        return json.loads(cleaned)
    except Exception:
        pass

    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            return None

    return None


def generate_ai_advice(payload: Dict[str, Any], timeout: int = DEFAULT_TIMEOUT) -> Optional[Dict[str, Any]]:
    """
    呼叫 Gemini，回傳結構化建議 dict（見 REQUIRED_KEYS）。

    失敗時一律回傳 None（不丟例外），呼叫端應該 fallback 回規則式 structured
    diagnosis，並可選擇性提示使用者「AI 建議暫時無法使用」。
    """
    if not is_configured():
        return None

    prompt = _build_prompt(payload)
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 1500,
            "responseMimeType": "application/json",
        },
    }

    try:
        resp = requests.post(
            GEMINI_API_URL,
            params={"key": GEMINI_API_KEY},
            json=body,
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()

        candidates = data.get("candidates") or []
        if not candidates:
            return None

        parts = (candidates[0].get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts)

        result = _extract_json(text)
        if not isinstance(result, dict):
            return None

        for key in REQUIRED_KEYS:
            if key not in result:
                result[key] = "" if key == "best_fit_role" else []

        return result

    except Exception as e:
        print(f"[llm_advisor] Gemini call failed: {e}")
        return None
