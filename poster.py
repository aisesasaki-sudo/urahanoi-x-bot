"""
urahanoi-x-bot / poster.py
Usage:
  python poster.py --category A   # 朝9時: 東南アジア全般 (web検索)
  python poster.py --category B   # 夜21時: ブログ記事紹介
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
    "B": {"label": "ブログ記事紹介", "min_chars": 200, "max_chars": 350},
}

ARTICLES_TAB = "記事リスト"


# ── クライアント初期化 ─────────────────────────────────────────────────────────

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
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)


# ── Category A ────────────────────────────────────────────────────────────────

SYSTEM_A = """
あなたはハノイ在住の日本人男性。東南アジアの最新ニュースを日本語Xポストにまとめる。
記事の要約と自分の感想・レビューを自然な文章で書き、末尾に記事URLを入れる。
見出しや定型文は不要。ハッシュタグなし。URL込みで400〜600文字。
句点（。）の後は必ず空行（改行2つ）を入れる。
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
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=SYSTEM_A,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": WEB_SEARCH_PROMPT.replace("{today}", today)}],
    )
    full_text = "".join(b.text for b in response.content if hasattr(b, "text"))
    m = re.search(r"```json\s*(.*?)\s*```", full_text, re.DOTALL)
    if not m:
        raise ValueError(f"JSON not found:\n{full_text}")
    return json.loads(m.group(1))


# ── Category B ────────────────────────────────────────────────────────────────

SYSTEM_B = """
ハノイに5年以上住む日本人男性として、東南アジアの夜遊び・ナイトライフについてXに投稿する。
口調はカジュアルな話し言葉。「〜けど」「〜な気がする」「〜か」など自然な語尾。
煽り・マーケティング的な表現はしない。実際に行った人間の観察・感想として書く。
ハッシュタグなし。文末にブログURLをそのまま貼る。URL込みで200〜350文字。
句点（。）の後は必ず空行（改行2つ）を入れる。
"""

BLOG_PROMPT = """
以下のブログ記事一覧から1本選んで、Xポストを作成。
記事を読みたくなるような自然な紹介文を書く。定型文・煽り・マーケティング表現は使わない。
文末にそのままURLを貼る（ハッシュタグなし）。URL込みで200〜350文字。

【記事リスト】
{articles_text}

JSON出力（```json ... ```）:
{{"tweet": "投稿本文（末尾にURL含む）", "source_url": "選んだ記事のURL", "topic": "テーマ説明"}}
"""

def collect_B_articles(gc):
    sh = gc.open_by_key(os.environ["SPREADSHEET_ID"])
    try:
        ws = sh.worksheet(ARTICLES_TAB)
    except gspread.exceptions.WorksheetNotFound:
        print(f"[WARN] タブ「{ARTICLES_TAB}」が存在しません。scraper.py を先に実行してください。")
        return [], None

    rows = ws.get_all_values()
    if len(rows) <= 1:
        print("[WARN] 記事リストが空です。")
        return [], None

    unposted = []
    for i, row in enumerate(rows[1:], start=2):
        if len(row) >= 6 and row[5] == "":
            unposted.append({
                "row": i,
                "title": row[0],
                "url": row[1],
                "site": row[2],
                "category": row[3],
                "date": row[4],
                "ws": ws,
            })

    print(f"[B] 未投稿記事: {len(unposted)} 件")
    return unposted, ws

def generate_B(client, articles):
    if not articles:
        articles_text = "（記事リストが空のため、ハノイ夜遊びトピックで自由に生成）"
    else:
        lines = [
            f"{i+1}. [{a['title']}]({a['url']}) ({a['site']} / {a['category']} / {a['date']})"
            for i, a in enumerate(articles[:20])
        ]
        articles_text = "\n".join(lines)

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        system=SYSTEM_B,
        messages=[{"role": "user", "content": BLOG_PROMPT.replace("{articles_text}", articles_text)}],
    )
    full_text = response.content[0].text
    m = re.search(r"```json\s*(.*?)\s*```", full_text, re.DOTALL)
    if not m:
        raise ValueError(f"JSON not found:\n{full_text}")
    return json.loads(m.group(1))

def mark_article_posted(articles, source_url, gc):
    now = datetime.now(HANOI_TZ).strftime("%Y-%m-%d %H:%M")
    for a in articles:
        if a["url"] == source_url:
            a["ws"].update_cell(a["row"], 6, "○")
            a["ws"].update_cell(a["row"], 7, now)
            print(f"[Sheets] 投稿済みマーク: {a['title'][:30]}...")
            return
    print(f"[WARN] 記事が見つかりませんでした（URL不一致）: {source_url}")


# ── 共通 ──────────────────────────────────────────────────────────────────────

def write_to_sheet(gc, result, category, status):
    sh = gc.open_by_key(os.environ["SPREADSHEET_ID"])
    now = datetime.now(HANOI_TZ).strftime("%Y-%m-%d %H:%M")
    tweet = result["tweet"]
    sh.sheet1.append_row(
        [now, category, tweet, len(tweet), result.get("source_url", ""), status,
         now if status == "投稿済" else ""]
    )
    print(f"[Sheets] {len(tweet)}文字 / {category} / {status}")

def post_tweet(twitter, text):
    r = twitter.create_tweet(text=text)
    print(f"[X] https://x.com/i/web/status/{r.data['id']}")
    return r.data["id"]


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--category", choices=["A", "B"], required=True)
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
        articles = []
    else:
        articles, _ = collect_B_articles(gc)
        result = generate_B(claude, articles)

    text = result["tweet"]
    # 句点の後に空行を挿入（A・B共通）
    text = re.sub(r'。(?!\n)', '。\n\n', text)
    result["tweet"] = text
    source_url = result.get("source_url", "")
    print(f"[Generated] {len(text)}文字")
    if source_url:
        print(f"[Source] {source_url}")

    if not (cfg["min_chars"] <= len(text) <= cfg["max_chars"]):
        print(f"[WARN] 文字数範囲外: {len(text)}")

    if args.dry_run:
        write_to_sheet(gc, result, cat, "ドライラン")
    else:
        post_tweet(twitter, text)
        write_to_sheet(gc, result, cat, "投稿済")
        if cat == "B" and source_url and articles:
            mark_article_posted(articles, source_url, gc)

    print("[DONE]")

if __name__ == "__main__":
    main()
