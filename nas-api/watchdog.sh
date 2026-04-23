#!/bin/sh
# fetchループ停止検知→自動再起動
# cron/起動スクリプトから5分間隔で実行される前提

BD="/volume1/home/Drus/sstr-api"
LOG="$BD/logs/watchdog.log"
NOW=$(date +%s)

_log(){ echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG"; }

_mtime(){ [ -f "$1" ] && stat -c %Y "$1" 2>/dev/null || echo 0; }

_is_running(){ ps w | grep -v grep | grep -q "$1"; }

_start_weather(){
  _log "Starting fetch_weather loop"
  nohup sh -c 'while true; do cd '"$BD"' && python3 fetch_weather.py >> '"$BD"'/logs/weather.log 2>&1; sleep 600; done' > /dev/null 2>&1 &
}

_start_stats(){
  _log "Starting fetch_stats loop"
  nohup sh -c 'while true; do cd '"$BD"' && GOOGLE_APPLICATION_CREDENTIALS='"$BD"'/service-account-key.json python3 fetch_stats.py >> '"$BD"'/logs/fetch.log 2>&1; sleep 10800; done' > /dev/null 2>&1 &
}

_start_orbis(){
  _log "Starting fetch_orbis loop"
  nohup sh -c 'while true; do cd '"$BD"' && python3 fetch_orbis.py >> '"$BD"'/logs/orbis.log 2>&1; sleep 86400; done' > /dev/null 2>&1 &
}

# 1. プロセスチェック：ループ自体が消えてたら即起動
_is_running "fetch_weather.py" || _start_weather
_is_running "fetch_stats.py"   || _start_stats
_is_running "fetch_orbis.py"   || _start_orbis

# 2. 出力ファイルのmtimeチェック：ループは動いてても出力が古ければ異常
# weather: 30分以上古ければ異常（正常は10分間隔）
WM=$(_mtime "$BD/weather.json")
if [ "$WM" -gt 0 ] && [ $((NOW - WM)) -gt 1800 ]; then
  AGE=$((NOW - WM))
  _log "weather.json stale (age=${AGE}s), killing loop and restarting"
  pkill -f "fetch_weather.py"
  sleep 2
  _start_weather
fi

# stats: 6時間以上古ければ異常（正常は3時間間隔）
SM=$(_mtime "$BD/stats_cache.json")
if [ "$SM" -gt 0 ] && [ $((NOW - SM)) -gt 21600 ]; then
  AGE=$((NOW - SM))
  _log "stats_cache.json stale (age=${AGE}s), killing loop and restarting"
  pkill -f "fetch_stats.py"
  sleep 2
  _start_stats
fi

# orbis: 2日以上古ければ異常（正常は1日間隔）
OM=$(_mtime "$BD/orbis_cache.json")
if [ "$OM" -gt 0 ] && [ $((NOW - OM)) -gt 172800 ]; then
  AGE=$((NOW - OM))
  _log "orbis_cache.json stale (age=${AGE}s), killing loop and restarting"
  pkill -f "fetch_orbis.py"
  sleep 2
  _start_orbis
fi
