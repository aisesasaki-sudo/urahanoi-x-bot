"""
setup_neta_sheet.py
既存スプレッドシートに「ネタストック」タブを追加してヘッダーを設定する。
一度だけ実行するセットアップスクリプト。
"""

import json
import os
import gspread
from google.oauth2.service_account import Credentials

NETA_TAB = "ネタストック"

HEADERS = [
    "投入日",
    "生ネタ（乱雑でOK）",
    "カテゴリ",
    "ツイート案",
    "文字数",
    "ステータス",
    "投稿日",
]

SAMPLE_ROWS = [
    ["", "ハノイでバイク事故った、病院が想像と違いすぎた", "ハノイリアル", "", "", "", ""],
    ["", "20歳のFC2時代、一番印象に残った出来事", "ストーリー", "", "", "", ""],
    ["", "自己破産の手続きが意外と普通だった話", "ストーリー", "", "", "", ""],
    ["", "ベトナム人と日本人の金銭感覚の違い", "ハノイリアル", "", "", "", ""],
    ["", "マレーシアで逃げてきてモテ始めた理由を考えてみた", "ストーリー", "", "", "", ""],
]

def main():
    creds_dict = json.loads(os.environ["GOOGLE_SHEETS_CREDENTIALS"])
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    gc = gspread.authorize(creds)

    sh = gc.open_by_key(os.environ["SPREADSHEET_ID"])

    existing = [ws.title for ws in sh.worksheets()]
    if NETA_TAB in existing:
        print(f"[SKIP] タブ「{NETA_TAB}」はすでに存在します")
        ws = sh.worksheet(NETA_TAB)
    else:
        ws = sh.add_worksheet(title=NETA_TAB, rows=1000, cols=7)
        print(f"[作成] タブ「{NETA_TAB}」を追加しました")

    existing_vals = ws.get_all_values()
    if not existing_vals or existing_vals[0] != HEADERS:
        ws.clear()
        ws.append_row(HEADERS)
        for row in SAMPLE_ROWS:
            ws.append_row(row)
        print("[完了] ヘッダーとサンプルデータを追加しました")

    ws.format("A1:G1", {
        "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
        "backgroundColor": {"red": 0.13, "green": 0.13, "blue": 0.13},
    })

    url = f"https://docs.google.com/spreadsheets/d/{sh.id}"
    print(f"[URL] {url}")

if __name__ == "__main__":
    main()
