#!/usr/bin/env python3
"""ルート上の天気情報を取得してweather.jsonに保存（cronで10分に1回）"""
import json
import os
import time
from urllib.request import urlopen, Request
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEATHER_FILE = os.path.join(BASE_DIR, "weather.json")
OWM_KEY = "58130931e870f8c89a6eb88eaa5b525c"

# ルート上の主要チェックポイント
CHECKPOINTS = [
    {"name": "練馬", "lat": 35.754, "lng": 139.607},
    {"name": "上里SA", "lat": 36.254, "lng": 139.119},
    {"name": "下仁田", "lat": 36.224, "lng": 138.802},
    {"name": "妙高SA", "lat": 36.929, "lng": 138.212},
    {"name": "名立", "lat": 37.163, "lng": 138.087},
    {"name": "有磯海SA", "lat": 36.770, "lng": 137.400},
    {"name": "氷見", "lat": 36.864, "lng": 136.987},
    {"name": "能登(七尾)", "lat": 37.049, "lng": 136.969},
    {"name": "千里浜", "lat": 36.893, "lng": 136.766},
    {"name": "金沢", "lat": 36.560, "lng": 136.653},
]

def fetch_weather(point):
    """1地点の現在天気+3時間予報を取得"""
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={point['lat']}&lon={point['lng']}&appid={OWM_KEY}&units=metric&lang=ja"
    try:
        req = Request(url, headers={"User-Agent": "SSTR-Tracker/1.0"})
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            weather = data.get("weather", [{}])[0]
            main = data.get("main", {})
            rain = data.get("rain", {})
            wind = data.get("wind", {})
            return {
                "name": point["name"],
                "lat": point["lat"],
                "lng": point["lng"],
                "weather": weather.get("main", ""),
                "description": weather.get("description", ""),
                "icon": weather.get("icon", ""),
                "temp": main.get("temp", 0),
                "humidity": main.get("humidity", 0),
                "wind_speed": wind.get("speed", 0),
                "rain_1h": rain.get("1h", 0),
                "rain_3h": rain.get("3h", 0),
                "is_rain": weather.get("main", "") in ["Rain", "Drizzle", "Thunderstorm"],
                "is_snow": weather.get("main", "") == "Snow",
                "ts": time.time(),
            }
    except Exception as e:
        print(f"  Error fetching {point['name']}: {e}")
        return None

def main():
    print(f"[{datetime.now()}] Fetching weather...")
    results = []
    for pt in CHECKPOINTS:
        w = fetch_weather(pt)
        if w:
            results.append(w)
            status = "🌧" if w["is_rain"] else "☀"
            print(f"  {status} {w['name']}: {w['description']} {w['temp']}°C 風{w['wind_speed']}m/s")
        time.sleep(0.5)  # レート制限対策

    with open(WEATHER_FILE, "w") as f:
        json.dump({"points": results, "updated": datetime.now().isoformat()}, f, ensure_ascii=False)

    rain_count = sum(1 for r in results if r["is_rain"])
    print(f"  Total: {len(results)} points, {rain_count} with rain")

if __name__ == "__main__":
    main()
