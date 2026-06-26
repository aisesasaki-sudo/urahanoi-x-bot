"""
extract_neta.py
掲示板タブを全行読んで、ネタになりそうな内容をClaudeが抽出しネタストックに追加。
8,000行をバッチ処理（150行ずつ）して Claude haiku で判定。
"""

import json
import os
import re
import time
from datetime import datetime, timezone, timedelta

import anthropic
import gspread
from google.oauth2.service_account import Credentials

KEIJIBAN_TAB = "掲示板"
NETA_TAB = "ネタストック"
HANOI_TZ = timezone(timedelta(hours=7))
BATCH_SIZE = 150

EXTRACT_PROMPT = """
以下は東南アジア旅行・夜遊びコミュニティの掲示板テキストです。
この中から @urahanoi（ハノイ在住5年の日本人男性）のXポスト（ツイート）のネタになりそうな内容を抽出してください。

【抽出基準】
- ハノイ or ベトナムに関係する内容を優先
- 旅行者のリアルな質問・悩み・体験談
- ハノイとホーチミン・タイ・フィリピン等との比較
- 現地の生活・文化・物価・交通のリアル
- 夜遊び・ナイトライフに関する情報・疑問
- 移住・長期滞在に関する視点
- 「あるある」「意外な事実」「知ってると得する情報」

【除外】
- 特定サービスの具体的な価格・店名・URL・画像リンク
- 個人名・個人を特定できる情報
- スパム・宣伝・意味のないメッセージ
- ハノイに無関係な内容（比較でない場合）

【出力形式】
JSONで出力。最低0件、最大15件まで。

```json
[
  {"neta": "ネタの内容", "category": "カテゴリ"},
  ...
]
```

カテゴリ: ハノイリアル / 夜遊び / 比較コンテンツ / ストーリー / ハノイ時事

---

【掲示板テキスト】
{text}
"""

def get_sheets_client():
    creds_dict = json.loads(os.environ["GOOGLE_SHEETS_CREDENTIALS"])
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)

def extract_neta_from_batch(client, text_batch):
    prompt = EXTRACT_PROMPT.replace("{text}", text_batch)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    full_text = response.content[0].text
    m = re.search(r"```json\s*(.*?)\s*```", full_text, re.DOTALL)
    if not m:
        print(f"[WARN] JSONが見つかりませんでした")
        return []
    try:
        return json.loads(m.group(1))
    except Exception as e:
        print(f"[WARN] JSON解析エラー: {e}")
        return []

def main():
    claude = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    gc = get_sheets_client()
    sh = gc.open_by_key(os.environ["SPREADSHEET_ID"])

    print(f"[READ] 掲示板タブを読み込み中...")
    keijiban_ws = sh.worksheet(KEIJIBAN_TAB)
    all_values = keijiban_ws.get_all_values()
    print(f"[READ] 合計 {len(all_values)} 行")

    all_text_rows = []
    for row in all_values:
        line = " ".join(cell.strip() for cell in row if cell.strip())
        if line:
            all_text_rows.append(line)

    print(f"[READ] テキスト行: {len(all_text_rows)} 行")

    neta_ws = sh.worksheet(NETA_TAB)
    today = datetime.now(HANOI_TZ).strftime("%Y-%m-%d")

    existing_neta = set()
    for row in neta_ws.get_all_values()[1:]:
        if len(row) >= 2:
            existing_neta.add(row[1][:30])

    total_added = 0
    total_batches = (len(all_text_rows) + BATCH_SIZE - 1) // BATCH_SIZE

    for i in range(0, len(all_text_rows), BATCH_SIZE):
        batch = all_text_rows[i:i + BATCH_SIZE]
        batch_text = "\n".join(batch)
        batch_num = i // BATCH_SIZE + 1
        print(f"[BATCH {batch_num}/{total_batches}] {i}〜{i+len(batch)}行...")

        try:
            neta_list = extract_neta_from_batch(claude, batch_text)
            added = 0
            for item in neta_list:
                neta_text = item.get("neta", "").strip()
                category = item.get("category", "ハノイリアル")
                if not neta_text or neta_text[:30] in existing_neta:
                    continue
                neta_ws.append_row([today, neta_text, category, "", "", "", ""])
                existing_neta.add(neta_text[:30])
                added += 1
                total_added += 1
            print(f"  → {len(neta_list)}件抽出、{added}件追加")
        except Exception as e:
            print(f"[ERROR] バッチ{batch_num}: {e}")

        time.sleep(1)

    print(f"\n[完了] 合計 {total_added} 件のネタを追加しました")

if __name__ == "__main__":
    main()
