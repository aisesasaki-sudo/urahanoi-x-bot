"""
urahanoi-x-bot / scraper.py
urahanoi.com と aise-sasaki.com の記事をスクレイピングして
Google Sheets「記事リスト」タブに蓄積する。
Usage: python scraper.py
"""

import json
import os
import requests
import gspread
from google.oauth2.service_account import Credentials

BLOGS = [
    {
        "site": "urahanoi.com",
        "api_url": "https://urahanoi.com/wp-json/wp/v2/posts",
        "cat_url": "https://urahanoi.com/wp-json/wp/v2/categories",
    },
    {
        "site": "aise-sasaki.com",
        "api_url": "https://aise-sasaki.com/wp-json/wp/v2/posts",
        "cat_url": "https://aise-sasaki.com/wp-json/wp/v2/categories",
    },
]

TAB_NAME = "記事リスト"
HEADERS = ["タイトル", "URL", "サイト", "カテゴリ", "公開日", "投稿済み", "投稿日"]


def get_sheets_client():
    creds_dict = json.loads(os.environ["GOOGLE_SHEETS_CREDENTIALS"])
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)


def ensure_tab(spreadsheet):
    try:
        ws = spreadsheet.worksheet(TAB_NAME)
    except gspread.exceptions.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=TAB_NAME, rows=1000, cols=7)
        ws.append_row(HEADERS)
        print(f"[Sheets] タブ「{TAB_NAME}」を新規作成")
    return ws


def fetch_categories(cat_url):
    cat_map = {}
    try:
        r = requests.get(cat_url, params={"per_page": 100}, timeout=15)
        for cat in r.json():
            cat_map[cat["id"]] = cat["name"]
    except Exception as e:
        print(f"[WARN] カテゴリ取得失敗 ({cat_url}): {e}")
    return cat_map


def fetch_posts(api_url, cat_url, site_name):
    """WordPress REST API で記事一覧を全件取得"""
    cat_map = fetch_categories(cat_url)
    posts = []
    page = 1
    while True:
        try:
            r = requests.get(
                api_url,
                params={
                    "per_page": 100,
                    "page": page,
                    "orderby": "date",
                    "order": "desc",
                    "_fields": "title,link,date,categories",
                },
                timeout=15,
            )
            if r.status_code != 200:
                break
            data = r.json()
            if not data:
                break
            for p in data:
                cat_names = [cat_map.get(c, "") for c in p.get("categories", [])]
                posts.append(
                    {
                        "title": p["title"]["rendered"],
                        "url": p["link"],
                        "site": site_name,
                        "category": ", ".join(filter(None, cat_names)),
                        "date": p["date"][:10],
                    }
                )
            page += 1
            if len(data) < 100:
                break
        except Exception as e:
            print(f"[WARN] {site_name} page {page}: {e}")
            break
    return posts


def main():
    gc = get_sheets_client()
    sh = gc.open_by_key(os.environ["SPREADSHEET_ID"])
    ws = ensure_tab(sh)

    # 既存URLを取得（重複防止）
    existing_rows = ws.get_all_values()
    existing_urls = {row[1] for row in existing_rows[1:] if len(row) > 1 and row[1]}
    print(f"[Sheets] 既存記事数: {len(existing_urls)}")

    new_rows = []
    for blog in BLOGS:
        print(f"[Scrape] {blog['site']} ...")
        posts = fetch_posts(blog["api_url"], blog["cat_url"], blog["site"])
        print(f"[Scrape] {len(posts)} 件取得")
        for p in posts:
            if p["url"] not in existing_urls:
                new_rows.append(
                    [p["title"], p["url"], p["site"], p["category"], p["date"], "", ""]
                )
                existing_urls.add(p["url"])

    # バッチ書き込み（レートリミット対策）
    if new_rows:
        ws.append_rows(new_rows, value_input_option="USER_ENTERED")
        print(f"[DONE] {len(new_rows)} 件追加 / 合計 {len(existing_urls)} 件")
    else:
        print(f"[DONE] 新規記事なし / 合計 {len(existing_urls)} 件")


if __name__ == "__main__":
    main()
