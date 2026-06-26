"""
import_neta.py
掲示板から抽出したネタをネタストックタブに追加する。
"""

import json
import os
from datetime import datetime, timezone, timedelta
import gspread
from google.oauth2.service_account import Credentials

NETA_TAB = "ネタストック"
HANOI_TZ = timezone(timedelta(hours=7))

NETA_LIST = [
    ["ハノイでのナンパは旧市街地が人多いが、道が細くて交通量が激しくて難しいと言われる。実際どうなのか", "ハノイリアル"],
    ["ハノイとホーチミンの違い：ホーチミンは至る所でナンパできるが、ハノイは風俗のイメージが薄い。なぜそうなったのか", "比較コンテンツ"],
    ["友達の友達（ほぼ他人）の超美女がハノイでバイク2ケツで観光案内してくれた体験。東南アジアあるある", "ハノイリアル"],
    ["電子タバコ（IQOS）のベトナム持ち込み問題。自己責任で持ち込む人の実態と没収リスク", "ハノイリアル"],
    ["ベトナムエアラインの情報漏洩事件。ハノイ在住者としてアカウント管理の実態", "ハノイ時事"],
    ["ハノイ旅行のバランス論：風俗50旅行50説。実際に住んでみての感想", "比較コンテンツ"],
    ["ハノイのガールズバー事情。地元民でも意外と知らない夜の選択肢", "夜遊び"],
    ["ホーチミン乗り継ぎ6時間でデリヘル行ってきた旅行者レポートを読んで思うこと。ハノイはなぜこういう話が少ないか", "比較コンテンツ"],
    ["ハノイに来る日本人旅行者がよく聞く質問TOP：ナンパできる場所、ガールズバー、電子タバコ持ち込み", "ハノイリアル"],
    ["年始のベトナム旅行、ハノイかホーチミンか問題。5年住んでみての正直な意見", "比較コンテンツ"],
    ["ハノイ旧市街地の夜の実態：観光地っぽい顔と地元民が使う裏の顔の違い", "夜遊び"],
    ["ハノイのZaloとLINEの使い分け。現地の夜遊びコミュニティはどっちを使うか", "ハノイリアル"],
    ["ホーチミンから移住してきた人がハノイで最初に驚くこと", "ハノイリアル"],
    ["P活（パパ活）の東南アジア事情。ベトナムでは何と呼ばれてどう機能しているか", "夜遊び"],
    ["ハノイのマッチングアプリ事情。タイやフィリピンと比べて全然違う件", "夜遊び"],
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
    ws = sh.worksheet(NETA_TAB)

    today = datetime.now(HANOI_TZ).strftime("%Y-%m-%d")

    added = 0
    for neta, category in NETA_LIST:
        ws.append_row([today, neta, category, "", "", "", ""])
        added += 1

    print(f"[完了] {added}件のネタを追加しました")

if __name__ == "__main__":
    main()
