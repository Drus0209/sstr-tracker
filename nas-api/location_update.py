"""
server.pyに追加するロケーション共有エンドポイント

POST /api/location — 位置送信
  body: {"name": "Drus", "lat": 35.69, "lng": 139.84}

GET /api/locations — 全員の位置取得
  response: [{"name": "Drus", "lat": 35.69, "lng": 139.84, "ts": 1234567890, "speed": 80}]
"""
# server.pyに以下を追加:
#
# LOCATION_FILE = os.path.join(BD, "locations.json")
#
# @app.route('/api/location', methods=['POST', 'OPTIONS'])
# def post_location():
#     if request.method == 'OPTIONS': return '', 204
#     d = request.get_json()
#     if not d or 'name' not in d or 'lat' not in d or 'lng' not in d:
#         return jsonify({'error': 'name, lat, lng required'}), 400
#     locs = lj(LOCATION_FILE, {})
#     locs[d['name']] = {'lat': d['lat'], 'lng': d['lng'], 'speed': d.get('speed', 0), 'heading': d.get('heading', 0), 'ts': time.time()}
#     sj(LOCATION_FILE, locs)
#     return jsonify({'ok': True})
#
# @app.route('/api/locations')
# def get_locations():
#     locs = lj(LOCATION_FILE, {})
#     now = time.time()
#     result = [{'name': k, **v} for k, v in locs.items() if now - v.get('ts', 0) < 300]
#     return jsonify(result)
