#!/usr/bin/env python3
"""ルート上の交通規制情報を取得してtraffic.jsonに保存（cronで30分に1回）"""
import json
import os
import time
import xml.etree.ElementTree as ET
from urllib.request import urlopen, Request
from urllib.error import URLError
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TRAFFIC_FILE = os.path.join(BASE_DIR, "traffic.json")

# SSTRルート上の高速道路キーワード
ROUTE_KEYWORDS = [
    "関越", "上信越", "北陸道", "北陸自動車道", "中央道", "中央自動車道",
    "首都高", "長野道", "練馬", "藤岡", "上越", "富山", "金沢",
    "滑川", "魚津", "氷見", "七尾", "能登", "千里浜",
    "談合坂", "双葉", "諏訪", "安曇野", "松本",
]

def fetch_driveplaza_rss():
    """ドラぷらRSSから交通ニュースを取得"""
    url = "https://www.driveplaza.com/cms/news/traffic.xml"
    results = []
    try:
        req = Request(url, headers={"User-Agent": "SSTR-Tracker/1.0"})
        with urlopen(req, timeout=10) as resp:
            tree = ET.parse(resp)
            root = tree.getroot()
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            for entry in root.findall(".//item") or root.findall(".//atom:entry", ns):
                title = ""
                link = ""
                desc = ""
                if entry.find("title") is not None:
                    title = entry.find("title").text or ""
                if entry.find("link") is not None:
                    link = entry.find("link").text or ""
                if entry.find("description") is not None:
                    desc = entry.find("description").text or ""
                text = title + " " + desc
                if any(kw in text for kw in ROUTE_KEYWORDS):
                    results.append({
                        "type": "nexco",
                        "title": title.strip(),
                        "memo": desc.strip()[:200],
                        "link": link.strip(),
                        "source": "ドラぷら",
                        "ts": time.time(),
                    })
    except Exception as e:
        print(f"RSS fetch error: {e}")
    return results

def fetch_drivetraffic():
    """ドラとらからリアルタイム規制情報をスクレイピング"""
    results = []
    # 関越道・上信越道・北陸道・中央道のページ
    roads = [
        ("関越道", "https://www.drivetraffic.jp/map.html?t=r&area=04&lv=6"),
        ("北陸道", "https://www.drivetraffic.jp/map.html?t=r&area=06&lv=6"),
        ("中央道", "https://www.drivetraffic.jp/map.html?t=r&area=04&lv=6"),
    ]
    # ドラとらはJSレンダリングなのでスクレイピング困難
    # 代わりにNEXCO中日本の規制情報ページをチェック
    try:
        url = "https://www.c-nexco.co.jp/traffic/jam/"
        req = Request(url, headers={"User-Agent": "SSTR-Tracker/1.0"})
        with urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
            # 簡易パース：ルート上のキーワードを含む行を抽出
            for line in html.split("\n"):
                if any(kw in line for kw in ROUTE_KEYWORDS):
                    # HTMLタグ除去
                    import re
                    text = re.sub(r"<[^>]+>", "", line).strip()
                    if len(text) > 10:
                        results.append({
                            "type": "regulation",
                            "title": text[:100],
                            "memo": "",
                            "source": "NEXCO中日本",
                            "ts": time.time(),
                        })
    except Exception as e:
        print(f"NEXCO fetch error: {e}")
    return results

def main():
    print(f"[{datetime.now()}] Fetching traffic info...")

    all_reports = []

    # ドラぷらRSS
    rss = fetch_driveplaza_rss()
    print(f"  ドラぷら: {len(rss)} items")
    all_reports.extend(rss)

    # NEXCO中日本
    nexco = fetch_drivetraffic()
    print(f"  NEXCO: {len(nexco)} items")
    all_reports.extend(nexco)

    # 既存の手動通報を保持
    existing = []
    try:
        with open(TRAFFIC_FILE, "r") as f:
            existing = json.load(f)
    except:
        pass

    # 手動通報（lat/lngがあるもの）は保持、古い自動取得は削除
    manual = [r for r in existing if "lat" in r and time.time() - r.get("ts", 0) < 86400]
    all_reports = manual + all_reports

    # 重複除去（titleベース）
    seen = set()
    unique = []
    for r in all_reports:
        key = r.get("title", "") or str(r.get("id", ""))
        if key not in seen:
            seen.add(key)
            unique.append(r)

    with open(TRAFFIC_FILE, "w") as f:
        json.dump(unique, f, ensure_ascii=False)

    print(f"  Total: {len(unique)} items saved")

if __name__ == "__main__":
    main()
