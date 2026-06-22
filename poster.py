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
あなたはハノイ在住の日本人男性。東南アジアの最新ニュースを日本語Xポストにまとめる。
記事の要約と自分の感想・レビューを自然な文章で書き、末尾に記事URLを入れる。
見出しや定型文は不要。ハッシュタグなし。URL込みで400〜600文字。
"""

WEB_SEARCH_PROMPT = """
東南アジアの最新トレンドをリサーチしてXポストを1本作成。
1. web_searchで英語・ベトナム語・タイ語・インドネシア語の各国メディアから今日の注目ニュースを3〜5件収集
2. 最もバズりそうなネタを1つ選ぶ
3. 記事の内容を自分なりにまとめ、個人的な感想・レビューを自然に混ぜた文章を書く。末尾に記事URLを入れる。
   見出し（【】など）・定型文・ハッシュタグ不要。URLはt.coで23文字換算。URL込みで400〜600文字以内。
今日の日付: {today}
JSON出力（```json ... ```）:
{"tweet": "ツイート本文（末尾にURL含む）", "source_url": "記事URL", "topic": "ネタ説明"}
"""

def collect_and_generate_A(client):
    today = datetime.now(HANOI_TZ).strftime("%Y-%m-%d")
    response = client.messages.create(
        model="claude-sonnet-4-6", max_tokens=2000, system=SYSTEM_A,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": WEB_SEARCH_PROMPT.replace("{today}", today)}],
    )
    full_text = "".join(b.text for b in response.content if hasattr(b, "text"))
    m = re.search(r"```json\s*(.*?)\s*```", full_text, re.DOTALL)
    if not m: raise ValueError(f"JSON not found:\n{full_text}")
    return json.loads(m.group(1))

SYSTEM_B = """
ハノイに5年以上住む日本人男性として、東南アジアの夜遊び・ナイトライフについてXに投稿する。
口調はカジュアルな話し言葉。「〜けど」「〜な気がする」「〜か」など自然な語尾。
煽り・マーケティング的な表現はしない。実際に行った人間の観察・感想として書く。
ハッシュタグなし・200〜350文字。
"""

X_SEARCH_PROMPT = """
以下のトレンド情報を元に東南アジア夜遊びXポスト（200〜350文字）を1本作成。
特定アカウント・個人情報不使用。対象: バンコク・バリ・マニラ・ハノイ・台湾・韓国。
「現地に住んでいる人間が最近気づいたこと」として、カジュアルな観察・感想として書く。
煽り文句・マーケティング表現は使わない。
最も面白いと思ったツイートを1つ選び、そのIDを quote_tweet_id に入れ、一言コメントを書く。
【収集投稿（ID付き）】{tweets_text}
JSON出力（```json ... ```）:
{"tweet": "コメント本文（200〜350文字）", "quote_tweet_id": "引用するツイートのID", "source_url": "", "topic": "テーマ説明"}
"""

X_QUERIES = ["東南アジア 夜遊び", "バンコク ナイトライフ", "バリ島 夜"]

def collect_B_tweets(twitter):
    collected = []
    for q in X_QUERIES:
        try:
            r = twitter.search_recent_tweets(
                query=f"{q} -is:retweet lang:ja", max_results=10,
                tweet_fields=["public_metrics", "text"], sort_order="relevancy",
            )
            if r.data:
                for t in r.data:
                    m = t.public_metrics
                    collected.append((m["like_count"] + m["retweet_count"]*2, t.id, t.text))
        except Exception as e:
            print(f"[WARN] {q}: {e}")
    if not collected:
        return "（X検索結果なし。東南アジア夜遊びトレンドで生成）", {}
    collected.sort(key=lambda x: x[0], reverse=True)
    top = collected[:5]
    tweet_map = {str(tid): f"https://x.com/i/web/status/{tid}" for _, tid, _ in top}
    tweets_text = "\n---\n".join([f"ID:{tid}\n{text}" for _, tid, text in top])
    return tweets_text, tweet_map

def generate_B(client, tweets_text, tweet_map):
    response = client.messages.create(
        model="claude-sonnet-4-6", max_tokens=1000, system=SYSTEM_B,
        messages=[{"role": "user", "content": X_SEARCH_PROMPT.replace("{tweets_text}", tweets_text)}],
    )
    full_text = response.content[0].text
    m = re.search(r"```json\s*(.*?)\s*```", full_text, re.DOTALL)
    if not m: raise ValueError(f"JSON not found:\n{full_text}")
    result = json.loads(m.group(1))
    qtid = str(result.get("quote_tweet_id", ""))
    if qtid and qtid in tweet_map:
        result["source_url"] = tweet_map[qtid]
        print(f"[QuoteRT] {tweet_map[qtid]}")
    return result

def write_to_sheet(gc, result, category, status):
    sh = gc.open_by_key(os.environ["SPREADSHEET_ID"])
    now = datetime.now(HANOI_TZ).strftime("%Y-%m-%d %H:%M")
    tweet = result["tweet"]
    sh.sheet1.append_row([now, category, tweet, len(tweet), result.get("source_url",""), status, now if status=="投稿済" else ""])
    print(f"[Sheets] {len(tweet)}文字 / {category} / {status}")

def post_tweet(twitter, text, quote_tweet_id=None):
    kwargs = {"text": text}
    if quote_tweet_id:
        kwargs["quote_tweet_id"] = int(quote_tweet_id)
    r = twitter.create_tweet(**kwargs)
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
    if cat == "A":
        result = collect_and_generate_A(claude)
        quote_tweet_id = None
    else:
        tweets_text, tweet_map = collect_B_tweets(twitter)
        result = generate_B(claude, tweets_text, tweet_map)
        quote_tweet_id = str(result.get("quote_tweet_id", "")) or None
    text = result["tweet"]
    print(f"[Generated] {len(text)}文字")
    if not (cfg["min_chars"] <= len(text) <= cfg["max_chars"]):
        print(f"[WARN] 文字数範囲外: {len(text)}")
    if args.dry_run:
        if quote_tweet_id:
            print(f"[DRY-RUN] 引用RT元: https://x.com/i/web/status/{quote_tweet_id}")
        write_to_sheet(gc, result, cat, "ドライラン")
    else:
        post_tweet(twitter, text, quote_tweet_id)
        write_to_sheet(gc, result, cat, "投稿済")
    print("[DONE]")

if __name__ == "__main__":
    main()
