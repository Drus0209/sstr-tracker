#!/usr/bin/env python3
"""SSTR API Server - APIカウンター + 交通情報"""
import json
import os
import time
from flask import Flask, jsonify, request

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(BASE_DIR, "stats_cache.json")
TRAFFIC_FILE = os.path.join(BASE_DIR, "traffic.json")

def load_json(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False)

@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    if request.method == "OPTIONS":
        response.status_code = 204
    return response

# === APIカウンター ===
@app.route("/api/usage")
@app.route("/api/stats")
def stats():
    data = load_json(CACHE_FILE, {"maps": 0, "directions": 0})
    return jsonify(data)

# === 交通情報 ===
@app.route("/api/traffic")
def get_traffic():
    reports = load_json(TRAFFIC_FILE, [])
    # 24時間以上前の通報は自動削除
    now = time.time()
    reports = [r for r in reports if now - r.get("ts", 0) < 86400]
    save_json(TRAFFIC_FILE, reports)
    return jsonify(reports)

@app.route("/api/report", methods=["POST", "OPTIONS"])
def post_report():
    if request.method == "OPTIONS":
        return "", 204
    data = request.get_json()
    if not data or "lat" not in data or "lng" not in data or "type" not in data:
        return jsonify({"error": "lat, lng, type required"}), 400

    report = {
        "id": int(time.time() * 1000),
        "lat": data["lat"],
        "lng": data["lng"],
        "type": data["type"],  # accident, closure, police, construction, other
        "memo": data.get("memo", ""),
        "ts": time.time(),
    }

    reports = load_json(TRAFFIC_FILE, [])
    reports.append(report)
    save_json(TRAFFIC_FILE, reports)
    return jsonify({"ok": True, "id": report["id"]})

@app.route("/api/report/<int:report_id>", methods=["DELETE"])
def delete_report(report_id):
    reports = load_json(TRAFFIC_FILE, [])
    reports = [r for r in reports if r["id"] != report_id]
    save_json(TRAFFIC_FILE, reports)
    return jsonify({"ok": True})

@app.route("/")
def index():
    return jsonify({"status": "ok", "endpoints": ["/api/usage", "/api/traffic", "/api/report"]})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3456)
