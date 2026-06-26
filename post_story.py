"""
post_story.py
ネタストックのF列=「承認」の行をX投稿して「投稿済」にマークする。
手動でworkflow_dispatchから実行。
"""

import json
import os
from datetime import datetime, timezone, timedelta

import gspread
import tweepy
from google.oauth2.service_account import Credentials

NETA_TAB = "ネタストック"
HANOI_TZ = timezone(timedelta(hours=7))

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

def main():
    twitter = get_twitter_client()
    gc = get_sheets_client()
    sh = gc.open_by_key(os.environ["SPREADSHEET_ID"])
    ws = sh.worksheet(NETA_TAB)

    rows = ws.get_all_values()
    now = datetime.now(HANOI_TZ).strftime("%Y-%m-%d %H:%M")

    targets = []
    for i, row in enumerate(rows[1:], start=2):
        row = row + [""] * (7 - len(row))
        tweet_draft = row[3].strip()
        status = row[5].strip()
        if tweet_draft and status == "承認":
            targets.append({"row": i, "tweet": tweet_draft})

    print(f"[CHECK] 承認済み: {len(targets)}件")
    if not targets:
        print("[SKIP] 承認済みのツイートがありません")
        return

    posted = 0
    for t in targets:
        try:
            r = twitter.create_tweet(text=t["tweet"])
            tweet_id = r.data["id"]
            print(f"  [POST] https://x.com/i/web/status/{tweet_id}")
            ws.update_cell(t["row"], 6, "投稿済")
            ws.update_cell(t["row"], 7, now)
            posted += 1
        except Exception as e:
            print(f"  [ERROR] 行{t['row']}: {e}")

    print(f"\n[完了] {posted}件投稿しました")

if __name__ == "__main__":
    main()
