#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
診斷 embedding 失敗的原因。

用法：
    # 1) 先跑 backfill_embeddings.py，把印出來「失敗的 job_no」清單複製下來
    # 2) 貼進 --job-nos，或存成一行一個的 txt 檔用 --job-nos-file
    python diagnose_embedding_failures.py --job-nos JOB123 JOB456
    python diagnose_embedding_failures.py --job-nos-file failed.txt

會做兩件事：
    a) 印出每筆的 build_embed_text() 組出來的內容長度 / 前 200 字，
       看是不是內容太短、太長、或含有異常字元
    b) 對每一筆單獨呼叫一次 embed_text()，看真正的錯誤訊息是什麼
       （不像 batch 呼叫那樣訊息會被合併、看不出是哪筆的問題）
"""

import argparse
import sys
from pathlib import Path
from typing import Dict, List

import requests
from dotenv import load_dotenv
import os

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from utils.embeddings import embed_text, is_configured  # noqa: E402
from backfill_embeddings import build_embed_text  # noqa: E402

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

HEADERS = {
    "apikey": SUPABASE_KEY,
    # 新版 sb_secret_... key 不是 JWT，不能塞進 Authorization: Bearer header
    # （會被 PostgREST 判定不合法直接 401），只需要 apikey header。
    "Content-Type": "application/json",
}


def fetch_rows_by_job_no(job_nos: List[str]) -> List[Dict]:
    if not job_nos:
        return []
    # PostgREST 的 in.() 語法：in.(a,b,c)
    in_list = ",".join(job_nos)
    resp = requests.get(
        f"{SUPABASE_URL}/job_posting",
        headers=HEADERS,
        params={
            "select": "job_no,title_clean,role_normalized,job_parent_category,skill_canonical,job_description",
            "job_no": f"in.({in_list})",
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json() or []


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Diagnose embedding failures for specific job_no rows")
    p.add_argument("--job-nos", nargs="+", default=[], help="失敗的 job_no，空白分隔")
    p.add_argument("--job-nos-file", type=str, default=None, help="失敗的 job_no 清單檔，一行一個")
    return p.parse_args()


def main() -> None:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("缺少 SUPABASE_URL 或 SUPABASE_KEY")
    if not is_configured():
        raise RuntimeError("缺少 GEMINI_API_KEY")

    args = parse_args()
    job_nos = list(args.job_nos)
    if args.job_nos_file:
        job_nos.extend(
            line.strip() for line in Path(args.job_nos_file).read_text(encoding="utf-8").splitlines() if line.strip()
        )

    if not job_nos:
        print("沒有指定任何 job_no，請用 --job-nos 或 --job-nos-file")
        return

    rows = fetch_rows_by_job_no(job_nos)
    found_job_nos = {r.get("job_no") for r in rows}
    missing = set(job_nos) - found_job_nos
    if missing:
        print(f"⚠️ 這些 job_no 在 job_posting 裡找不到（可能已被清理或打錯）：{missing}")

    for row in rows:
        job_no = row.get("job_no")
        text = build_embed_text(row)
        print("=" * 60)
        print(f"job_no: {job_no}")
        print(f"title_clean: {row.get('title_clean')!r}")
        print(f"role_normalized: {row.get('role_normalized')!r}")
        print(f"組出來的 embed text 長度: {len(text)} 字元")
        print(f"前 200 字: {text[:200]!r}")

        if len(text) < 10:
            print("👉 診斷：內容過短/空白，這筆本來就不該送進 API（可用最新版 backfill_embeddings.py 自動跳過）")
            continue

        result = embed_text(text, task_type="RETRIEVAL_DOCUMENT")
        if result:
            print(f"👉 診斷：單獨呼叫成功（維度 {len(result)}）——代表當初是被同 batch 裡其他壞資料拖累，用最新版 embed_texts_batch() 即可解決")
        else:
            print("👉 診斷：單獨呼叫仍然失敗，看上面 [embeddings] 開頭的 log 訊息（HTTP 狀態碼 / 錯誤原因），可能是內容觸發安全過濾、或超過長度限制")


if __name__ == "__main__":
    main()
