#!/usr/bin/env python3
"""Cloud Monitoring APIから使用量を取得してJSONにキャッシュする（cronで3時間に1回実行）"""
import json
import os
from datetime import datetime

from google.cloud import monitoring_v3

PROJECT_ID = "sstr-492316"
CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stats_cache.json")

def get_api_usage(client, service_name):
    now = datetime.utcnow()
    start = datetime(now.year, now.month, 1)

    interval = monitoring_v3.TimeInterval({
        "start_time": {"seconds": int(start.timestamp())},
        "end_time": {"seconds": int(now.timestamp())},
    })
    aggregation = monitoring_v3.Aggregation({
        "alignment_period": {"seconds": int((now - start).total_seconds())},
        "per_series_aligner": monitoring_v3.Aggregation.Aligner.ALIGN_SUM,
    })

    results = client.list_time_series(
        request={
            "name": f"projects/{PROJECT_ID}",
            "filter": f'metric.type="serviceruntime.googleapis.com/api/request_count" AND resource.labels.service="{service_name}"',
            "interval": interval,
            "aggregation": aggregation,
        }
    )

    total = 0
    for ts in results:
        for point in ts.points:
            total += point.value.int64_value
    return total

def safe_get(client, svc):
    try: return get_api_usage(client, svc)
    except Exception: return 0

# Cloud Console と同じ表示名へのマッピング
SVC_LABELS = {
    "maps-backend.googleapis.com": "Maps JS",
    "directions-backend.googleapis.com": "Directions",
    "routes.googleapis.com": "Routes",
    "places-backend.googleapis.com": "Places",
    "places.googleapis.com": "Places (New)",
    "geocoding-backend.googleapis.com": "Geocoding",
    "generativelanguage.googleapis.com": "Gemini",
    "artifactregistry.googleapis.com": "Artifact Registry",
    "cloudfunctions.googleapis.com": "Cloud Functions",
    "monitoring.googleapis.com": "Cloud Monitoring",
    "logging.googleapis.com": "Cloud Logging",
    "cloudbuild.googleapis.com": "Cloud Build",
    "pubsub.googleapis.com": "Cloud Pub/Sub",
    "run.googleapis.com": "Cloud Run",
    "iam.googleapis.com": "IAM",
    "iamcredentials.googleapis.com": "IAM Credentials",
    "storage.googleapis.com": "Cloud Storage",
    "bigquery.googleapis.com": "BigQuery",
    "secretmanager.googleapis.com": "Secret Manager",
    "containerregistry.googleapis.com": "Container Registry",
    "cloudtrace.googleapis.com": "Cloud Trace",
    "serviceusage.googleapis.com": "Service Usage",
    "servicemanagement.googleapis.com": "Service Management",
}

def discover_used_services(client):
    """Cloud Monitoring APIから今月使われた全サービスを動的に検出"""
    now = datetime.utcnow()
    start = datetime(now.year, now.month, 1)
    interval = monitoring_v3.TimeInterval({
        "start_time": {"seconds": int(start.timestamp())},
        "end_time": {"seconds": int(now.timestamp())},
    })
    aggregation = monitoring_v3.Aggregation({
        "alignment_period": {"seconds": int((now - start).total_seconds())},
        "per_series_aligner": monitoring_v3.Aggregation.Aligner.ALIGN_SUM,
    })
    results = client.list_time_series(
        request={
            "name": f"projects/{PROJECT_ID}",
            "filter": 'metric.type="serviceruntime.googleapis.com/api/request_count"',
            "interval": interval,
            "aggregation": aggregation,
        }
    )
    totals = {}
    for ts in results:
        svc = ts.resource.labels.get("service", "")
        if not svc: continue
        for point in ts.points:
            totals[svc] = totals.get(svc, 0) + point.value.int64_value
    return totals

def main():
    client = monitoring_v3.MetricServiceClient()

    # 動的に全サービス使用量を取得
    raw = discover_used_services(client)
    breakdown = {}
    for svc, n in raw.items():
        if n <= 0: continue
        label = SVC_LABELS.get(svc, svc.split(".")[0])  # 未マップは生のサブドメイン名
        breakdown[label] = breakdown.get(label, 0) + n

    # 後方互換用のフラット数値
    maps = raw.get("maps-backend.googleapis.com", 0)
    directions = raw.get("routes.googleapis.com", 0) + raw.get("directions-backend.googleapis.com", 0)
    places = raw.get("places-backend.googleapis.com", 0) + raw.get("places.googleapis.com", 0)
    geocoding = raw.get("geocoding-backend.googleapis.com", 0)

    data = {
        "maps": maps,
        "directions": directions,
        "places": places,
        "geocoding": geocoding,
        "breakdown": breakdown,
        "month": datetime.utcnow().strftime("%Y-%m"),
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

    with open(CACHE_FILE, "w") as f:
        json.dump(data, f)

    print(f"Updated: {len(breakdown)} services auto-discovered, total={sum(breakdown.values())}")

if __name__ == "__main__":
    main()
