"""
generate_story.py
ネタストックタブを全件チェックし、ツイート案が未生成のものを全て整形する。
D列が空のものを対象に、Claudeがツイート案を生成してD列・F列を更新。
毎週土曜 朝9時（ハノイ時間）に自動実行。
"""

import json
import os
import re
import time
from datetime import datetime, timezone, timedelta

import anthropic
import gspread
from google.oauth2.service_account import Credentials

NETA_TAB = "ネタストック"
HANOI_TZ = timezone(timedelta(hours=7))

SYSTEM_STORY = """
ハノイに5年以上住む日本人男性として、Xに投稿する。
口調はカジュアルな話し言葉。「〜けど」「〜な気がする」「〜か」など自然な語尾。
煽り・マーケティング的な表現はしない。リアルな体験・観察・感想として書く。
ハッシュタグなし。URLなし。150〜280文字。
句点（。）の後は必ず空行（改行2つ）を入れる。
"""

TWEET_PROMPT = """
以下のネタをもとに、Xのポストを1本書いてください。

ネタ：{neta}
カテゴリ：{category}

JSONで出力（```json ... ```）:
{{"tweet": "ポスト本文"}}
"""

def get_anthropic_client():
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

def get_sheets_client():
    creds_dict = json.loads(os.environ["GOOGLE_SHEETS_CREDENTIALS"])
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)

def generate_tweet(client, neta, category):
    prompt = TWEET_PROMPT.format(neta=neta, category=category)
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=800,
        system=SYSTEM_STORY,
        messages=[{"role": "user", "content": prompt}],
    )
    full_text = response.content[0].text
    m = re.search(r"```json\s*(.*?)\s*```", full_text, re.DOTALL)
    if not m:
        raise ValueError(f"JSON not found: {full_text[:200]}")
    data = json.loads(m.group(1))
    tweet = data["tweet"]
    tweet = re.sub(r'。(?!\n)', '。\n\n', tweet)
    return tweet

def main():
    claude = get_anthropic_client()
    gc = get_sheets_client()
    sh = gc.open_by_key(os.environ["SPREADSHEET_ID"])
    ws = sh.worksheet(NETA_TAB)

    rows = ws.get_all_values()
    if len(rows) <= 1:
        print("[SKIP] ネタストックが空です")
        return

    targets = []
    for i, row in enumerate(rows[1:], start=2):
        row = row + [""] * (7 - len(row))
        neta = row[1].strip()
        category = row[2].strip()
        tweet_draft = row[3].strip()
        status = row[5].strip()
        if neta and not tweet_draft and status != "投稿済":
            targets.append({"row": i, "neta": neta, "category": category or "ハノイリアル"})

    print(f"[CHECK] 未生成: {len(targets)}件")
    if not targets:
        print("[SKIP] 全件ツイート案あり")
        return

    generated = 0
    for t in targets:
        try:
            tweet = generate_tweet(claude, t["neta"], t["category"])
            char_count = len(tweet)
            ws.update_cell(t["row"], 4, tweet)
            ws.update_cell(t["row"], 5, char_count)
            ws.update_cell(t["row"], 6, "確認待ち")
            generated += 1
            print(f"  [{t['row']}] {t['neta'][:30]}... → {char_count}文字")
        except Exception as e:
            print(f"  [ERROR] 行{t['row']}: {e}")
        time.sleep(0.5)

    print(f"\n[完了] {generated}件のツイート案を生成しました")

if __name__ == "__main__":
    main()
