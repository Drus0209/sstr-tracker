#!/usr/bin/env python3
"""Grafana Alert Rules + Gmail Contact Point 自動セットアップ"""
import json, urllib.request, os

BASE = "http://localhost:3000"
AUTH = ("admin", os.environ.get("GRAFANA_PASSWORD", ""))
DS_UID = "PBFA97CFB590B2093"

def api(method, path, data=None):
    url = BASE + path
    body = json.dumps(data).encode() if data else None
    headers = {"Content-Type": "application/json"}
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    import base64
    req.add_header("Authorization", "Basic " + base64.b64encode(f"{AUTH[0]}:{AUTH[1]}".encode()).decode())
    try:
        r = urllib.request.urlopen(req, timeout=20)
        body = r.read()
        return json.loads(body) if body else {"ok": True}
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"ERR {e.code}: {body[:200]}")
        return None

def api_read(path):
    url = BASE + path
    req = urllib.request.Request(url)
    import base64
    req.add_header("Authorization", "Basic " + base64.b64encode(f"{AUTH[0]}:{AUTH[1]}".encode()).decode())
    r = urllib.request.urlopen(req, timeout=20)
    return json.loads(r.read())

# 1. Gmail Contact Point
print("=== Contact Point ===")
cp = {
    "name": "Gmail",
    "type": "email",
    "settings": {
        "addresses": os.environ.get("GMAIL_USER", ""),
        "singleEmail": True
    },
    "disableResolveMessage": False
}
r = api("POST", "/api/v1/provisioning/contact-points", cp)
print("contact point:", r)

# 2. Notification Policy → Gmail
print("=== Notification Policy ===")
policy = {
    "receiver": "Gmail",
    "group_by": ["alertname"],
    "group_wait": "30s",
    "group_interval": "5m",
    "repeat_interval": "4h"
}
r = api("PUT", "/api/v1/provisioning/policies", policy)
print("policy:", r)

# 3. Alert Rules
print("=== Alert Rules ===")
def make_rule(title, expr, for_dur, folder_uid, summary, severity="critical"):
    return {
        "title": title,
        "ruleGroup": "SSTR Monitoring",
        "folderUID": folder_uid,
        "condition": "C",
        "data": [
            {
                "refId": "A",
                "queryType": "",
                "relativeTimeRange": {"from": 300, "to": 0},
                "datasourceUid": DS_UID,
                "model": {
                    "expr": expr,
                    "refId": "A"
                }
            },
            {
                "refId": "B",
                "queryType": "",
                "relativeTimeRange": {"from": 300, "to": 0},
                "datasourceUid": "__expr__",
                "model": {
                    "type": "reduce",
                    "expression": "A",
                    "reducer": "last",
                    "refId": "B"
                }
            },
            {
                "refId": "C",
                "queryType": "",
                "relativeTimeRange": {"from": 300, "to": 0},
                "datasourceUid": "__expr__",
                "model": {
                    "type": "threshold",
                    "expression": "B",
                    "conditions": [{"evaluator": {"type": "lt", "params": [1]}}],
                    "refId": "C"
                }
            }
        ],
        "for": for_dur,
        "noDataState": "Alerting",
        "execErrState": "Alerting",
        "labels": {"severity": severity},
        "annotations": {"summary": summary}
    }

# Create folder for alerts
folder = api("POST", "/api/folders", {"title": "SSTR Alerts"})
if folder:
    folder_uid = folder.get("uid", "")
    print("folder:", folder_uid)
else:
    folders = api_read("/api/folders")
    folder_uid = next((f["uid"] for f in folders if f["title"] == "SSTR Alerts"), "")
    print("folder exists:", folder_uid)

rules = [
    ("Flask API ダウン", "probe_success{service=\"Flask API\"}", "2m", "Flask APIが2分以上応答なし", "critical"),
    ("VOICEVOX PC ダウン", "probe_success{service=\"VOICEVOX PC\"}", "2m", "VOICEVOX PCが2分以上応答なし", "critical"),
    ("VOICEVOX NAS ダウン", "probe_success{service=\"VOICEVOX NAS\"}", "2m", "VOICEVOX NASが2分以上応答なし", "critical"),
    ("NAS Ping失敗", "probe_success{service=\"NAS Ping\"}", "3m", "NASが3分以上Ping応答なし", "critical"),
    ("PC Ping失敗", "probe_success{service=\"PC Ping\"}", "3m", "PCが3分以上Ping応答なし", "warning"),
    ("Switch Ping失敗", "probe_success{service=\"Switch Ping\"}", "3m", "スイッチが3分以上Ping応答なし", "warning"),
    ("NAS CPU高負荷", "100 - (avg(rate(node_cpu_seconds_total{mode=\"idle\",host=\"nas-as5304t\"}[5m])) * 100)", "5m", "NAS CPU 90%超が5分継続", "warning"),
    ("NAS メモリ逼迫", "(1 - node_memory_MemAvailable_bytes{host=\"nas-as5304t\"} / node_memory_MemTotal_bytes{host=\"nas-as5304t\"}) * 100", "5m", "NAS メモリ90%超", "warning"),
    ("NAS ディスク逼迫", "(1 - node_filesystem_avail_bytes{host=\"nas-as5304t\",mountpoint=\"/volume1\"} / node_filesystem_size_bytes{host=\"nas-as5304t\",mountpoint=\"/volume1\"}) * 100", "5m", "NAS ディスク85%超", "warning"),
]

for title, expr, dur, summary, sev in rules:
    # CPU/Memory/Disk alerts use "gt" threshold (> 90 or > 85)
    rule = make_rule(title, expr, dur, folder_uid, summary, sev)
    if "CPU" in title or "メモリ" in title:
        rule["data"][2]["model"]["conditions"][0]["evaluator"] = {"type": "gt", "params": [90]}
    elif "ディスク" in title:
        rule["data"][2]["model"]["conditions"][0]["evaluator"] = {"type": "gt", "params": [85]}
    r = api("POST", "/api/v1/provisioning/alert-rules", rule)
    print(f"  {title}: {'OK' if r else 'FAIL'}")

print("\n=== Done ===")
