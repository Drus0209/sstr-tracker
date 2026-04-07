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

def main():
    client = monitoring_v3.MetricServiceClient()

    maps = get_api_usage(client, "maps-backend.googleapis.com")
    directions = get_api_usage(client, "routes.googleapis.com")

    # Legacy directions API
    try:
        directions += get_api_usage(client, "directions-backend.googleapis.com")
    except Exception:
        pass

    data = {
        "maps": maps,
        "directions": directions,
        "month": datetime.utcnow().strftime("%Y-%m"),
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

    with open(CACHE_FILE, "w") as f:
        json.dump(data, f)

    print(f"Updated: Maps={maps}, Dir={directions}")

if __name__ == "__main__":
    main()
