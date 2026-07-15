#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
清空 jd_raw + job_posting 兩張表的全部資料。

用在 .github/workflows/cleaner-weekly.yml 的 clear-data job，
只有手動觸發 workflow 時把 truncate_before_run 打開才會被呼叫。

⚠️ 這個操作不可復原，執行前請再三確認要清的是正確的 Supabase 專案。
"""

import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Missing SUPABASE_URL or SUPABASE_KEY")

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal",
}

# 先清 job_posting 再清 jd_raw：job_posting 是清洗後的表，順序對正確性沒有影響，
# 但邏輯上「先清下游、再清上游」比較直覺。
TABLES = ["job_posting", "jd_raw"]


def clear_table(table: str) -> None:
    # job_no 是兩張表都有的必填欄位（scraper / cleaner upsert 用的 conflict key），
    # 用 not.is.null 當作「符合全部資料列」的篩選條件，PostgREST 的 DELETE 需要至少一個篩選條件。
    resp = requests.delete(
        f"{SUPABASE_URL}/{table}",
        headers=HEADERS,
        params={"job_no": "not.is.null"},
        timeout=60,
    )
    if resp.status_code not in (200, 204):
        print(f"❌ 清空 {table} 失敗: HTTP {resp.status_code} - {resp.text[:500]}")
        sys.exit(1)
    print(f"✅ 已清空 {table}")


def main() -> None:
    print("⚠️ 開始清空 jd_raw / job_posting 全部資料...")
    for table in TABLES:
        clear_table(table)
    print("✅ 清空完成")


if __name__ == "__main__":
    main()
