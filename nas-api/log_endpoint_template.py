# NAS Flask server に追加すべき開発ログエンドポイント
# /volume1/home/Drus/sstr-api/server.py に統合してください
#
# 動作:
# - クライアントから {"events": [...]} を受け取る
# - JSONLines (1行1イベント) で /volume1/home/Drus/sstr-api/logs/app/<YYYY-MM-DD>.jsonl に追記
# - イベント例: {"ts":1714467890123,"type":"gps","rider":"てつにん","plan":"day1","data":{"lat":35.69,"lng":139.84}}

from flask import request, jsonify
import os, json
from datetime import datetime

LOG_DIR = '/volume1/home/Drus/sstr-api/logs/app'
os.makedirs(LOG_DIR, exist_ok=True)

@app.route('/api/log/upload', methods=['POST'])
def log_upload():
    """クライアントから蓄積ログを受け取りJSONLines追記"""
    # X-API-Key 認証チェック（既存パターンに合わせる）
    if request.headers.get('X-API-Key') != API_KEY:
        return jsonify({'error': 'unauthorized'}), 401
    body = request.get_json(silent=True) or {}
    events = body.get('events', [])
    if not isinstance(events, list):
        return jsonify({'error': 'events must be array'}), 400
    today = datetime.now().strftime('%Y-%m-%d')
    fpath = os.path.join(LOG_DIR, f'{today}.jsonl')
    written = 0
    try:
        with open(fpath, 'a', encoding='utf-8') as f:
            for ev in events:
                if not isinstance(ev, dict):
                    continue
                f.write(json.dumps(ev, ensure_ascii=False) + '\n')
                written += 1
        return jsonify({'ok': True, 'written': written}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/log/sessions', methods=['GET'])
def log_sessions():
    """日付別ログファイル一覧"""
    if request.headers.get('X-API-Key') != API_KEY:
        return jsonify({'error': 'unauthorized'}), 401
    files = sorted([f for f in os.listdir(LOG_DIR) if f.endswith('.jsonl')], reverse=True)
    out = []
    for f in files:
        fp = os.path.join(LOG_DIR, f)
        try:
            with open(fp, 'r', encoding='utf-8') as fh:
                cnt = sum(1 for _ in fh)
            sz = os.path.getsize(fp)
            out.append({'date': f.replace('.jsonl', ''), 'count': cnt, 'size_bytes': sz})
        except Exception:
            pass
    return jsonify({'sessions': out})


@app.route('/api/log/sessions/<date>', methods=['GET'])
def log_session_detail(date):
    """特定日の全イベント取得"""
    if request.headers.get('X-API-Key') != API_KEY:
        return jsonify({'error': 'unauthorized'}), 401
    fpath = os.path.join(LOG_DIR, f'{date}.jsonl')
    if not os.path.exists(fpath):
        return jsonify({'events': []}), 200
    events = []
    try:
        with open(fpath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except Exception:
                    continue
        return jsonify({'events': events})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
