"""
urahanoi-x-bot / poster.py
Usage:
  python poster.py --category A   # 朝9時: 東南アジア全般 (web検索)
  python poster.py --category B   # 夜21時: 東南アジアの夜遊び (X API検索)
"""

import argparse
import json
import os
import re
from datetime import datetime, timezone, timedelta

import anthropic
import gspread
import tweepy
from google.oauth2.service_account import Credentials

HANOI_TZ = timezone(timedelta(hours=7))

CATEGORY_CONFIG = {
    "A": {"label": "東南アジア全般", "min_chars": 400, "max_chars": 600},
    "B": {"label": "東南アジアの夜遊び", "min_chars": 200, "max_chars": 350},
}

def get_anthropic_client():
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

def get_twitter_client():
    return tweepy.Client(
        consumer_key=os.environ["X_API_KEY"],
        consumer_secret=os.environ["X_API_SECRET"],
        access_token=os.environ["X_ACCESS_TOKEN"],
        access_token_secret=os.environ["X_ACCESS_SECRET"],
        bearer_token=os.environ["X_BEARER_TOKEN"],
    )

def get_sheets_client():
    creds_dict = json.loads(os.environ["GOOGLE_SHEETS_CREDENTIALS"])
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)

SYSTEM_A = """
あなたはハノイ在住の日本人男性。東南アジアの最新ニュース・現地リアルな話題を日本語Xポストに仕上げる。
【制約】事実ベース・色気なし・400〜600文字・リンクなし・ハッシュタグなし・最後に改行して「（ハノイより）」
"""

WEB_SEARCH_PROMPT = """
東南アジアの最新トレンドをリサーチしてXポストを1本作成。
1. web_searchで英語・ベトナム語・タイ語・インドネシア語の各国メディアから今日の注目ニュースを3〜5件収集
2. 最もバズりそうなネタを1つ選ぶ
3. 400〜600文字の日本語Xポストを書く
今日の日付: {today}
JSON出力（```json ... ```）:
{"tweet": "ツイート本文", "source_url": "記事URL", "topic": "ネタ説明"}
"""

def collect_and_generate_A(client):
    today = datetime.now(HANOI_TZ).strftime("%Y-%m-%d")
    response = client.messages.create(
        model="claude-sonnet-4-6", max_tokens=2000, system=SYSTEM_A,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": WEB_SEARCH_PROMPT.format(today=today)}],
    )
    full_text = "".join(b.text for b in response.content if hasattr(b, "text"))
    m = re.search(r"```json\s*(.*?)\s*```", full_text, re.DOTALL)
    if not m: raise ValueError(f"JSON not found:\n{full_text}")
    return json.loads(m.group(1))

SYSTEM_B = """
あなたはハノイ在住の日本人男性。東南アジアの夜遊び情報を色気たっぷりに日本語Xポストに仕上げる。
【制約】色気あり・煽情的・露骨すぎない・200〜350文字・リンクなし・ハッシュタグなし
"""

X_SEARCH_PROMPT = """
以下のトレンド情報を元に東南アジア夜遊びXポスト（200〜350文字）を1本作成。
特定アカウント・個人情報不使用。対象: バンコク・バリ・マニラ・ハノイ・台湾・韓国。
【収集投稿】{tweets_text}
JSON出力（```json ... ```）:
{"tweet": "ツイート本文", "source_url": "", "topic": "テーマ説明"}
"""

X_QUERIES = ["東南アジア 夜遊び", "バンコク ナイトライフ", "バリ島 夜"]

def collect_B_tweets(twitter):
    collected = []
    for q in X_QUERIES:
        try:
            r = twitter.search_recent_tweets(
                query=f"{q} -is:retweet lang:ja", max_results=5,
                tweet_fields=["public_metrics", "text"], sort_order="relevancy",
            )
            if r.data:
                for t in r.data:
                    m = t.public_metrics
                    collected.append((m["like_count"] + m["retweet_count"]*2, t.text))
        except Exception as e:
            print(f"[WARN] {q}: {e}")
    if not collected: return "（X検索結果なし。東南アジア夜遊びトレンドで生成）"
    collected.sort(key=lambda x: x[0], reverse=True)
    return "\n---\n".join([t for _, t in collected[:5]])

def generate_B(client, tweets_text):
    response = client.messages.create(
        model="claude-sonnet-4-6", max_tokens=1000, system=SYSTEM_B,
        messages=[{"role": "user", "content": X_SEARCH_PROMPT.format(tweets_text=tweets_text)}],
    )
    full_text = response.content[0].text
    m = re.search(r"```json\s*(.*?)\s*```", full_text, re.DOTALL)
    if not m: raise ValueError(f"JSON not found:\n{full_text}")
    return json.loads(m.group(1))

def write_to_sheet(gc, result, category, status):
    sh = gc.open_by_key(os.environ["SPREADSHEET_ID"])
    now = datetime.now(HANOI_TZ).strftime("%Y-%m-%d %H:%M")
    tweet = result["tweet"]
    sh.sheet1.append_row([now, category, tweet, len(tweet), result.get("source_url",""), status, now if status=="投稿済" else ""])
    print(f"[Sheets] {len(tweet)}文字 / {category} / {status}")

def post_tweet(twitter, text):
    r = twitter.create_tweet(text=text)
    print(f"[X] https://x.com/i/web/status/{r.data['id']}")
    return r.data["id"]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--category", choices=["A","B"], required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    cat = args.category
    cfg = CATEGORY_CONFIG[cat]
    print(f"[START] {cat} ({cfg['label']})")
    claude = get_anthropic_client()
    twitter = get_twitter_client()
    gc = get_sheets_client()
    result = collect_and_generate_A(claude) if cat=="A" else generate_B(claude, collect_B_tweets(twitter))
    text = result["tweet"]
    print(f"[Generated] {len(text)}文字")
    if not (cfg["min_chars"] <= len(text) <= cfg["max_chars"]):
        print(f"[WARN] 文字数範囲外: {len(text)}")
    if args.dry_run:
        write_to_sheet(gc, result, cat, "ドライラン")
    else:
        post_tweet(twitter, text)
        write_to_sheet(gc, result, cat, "投稿済")
    print("[DONE]")

if __name__ == "__main__":
    main()
