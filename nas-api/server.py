#!/usr/bin/env python3
"""SSTR API Server — NAS集中管理版（セキュリティ強化）"""
import json,os,time,hashlib,urllib.parse,urllib.request,functools,re,secrets
from flask import Flask,jsonify,request,send_file,abort
app=Flask(__name__)
BD=os.path.dirname(os.path.abspath(__file__))

# === セキュリティ設定 ===
API_KEY="sstr2026_k4w4s4k1_zx4r"

# レート制限: IP毎に1分間のリクエスト数を制限
_rate_limit={}
_rate_max=120  # 1分あたり最大リクエスト数
_rate_ban={}   # BANされたIP

# ファイル名サニタイズ（パストラバーサル防止）
def safe_name(name):
    name=re.sub(r'[/\\\.]{2,}','',name)  # ../防止
    name=re.sub(r'[^\w\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF\u3000-\u303Fー\-]','_',name)
    return name[:100]  # 最大100文字

# リクエストサイズ制限
app.config['MAX_CONTENT_LENGTH']=1*1024*1024  # 1MB

# === ディレクトリ・ファイル ===
VD=os.path.join(BD,"voices");os.makedirs(VD,exist_ok=True)
UD=os.path.join(BD,"users");os.makedirs(UD,exist_ok=True)
RD=os.path.join(BD,"routes");os.makedirs(RD,exist_ok=True)
TF=os.path.join(BD,"traffic.json")
WF=os.path.join(BD,"weather.json")
LF=os.path.join(BD,"locations.json")
OF=os.path.join(BD,"orbis_cache.json")
FF=os.path.join(BD,"friends.json")
SF=os.path.join(BD,"shared_plans.json")
UF=os.path.join(BD,"usage.json")

GMAPS_KEY="AIzaSyBwPBSu3pJ7LBsQ7WvSbTWiQsFY0R8cREY"

def lj(p,d):
    try:
        with open(p,"r") as f:return json.load(f)
    except:return d
def sj(p,d):
    with open(p,"w") as f:json.dump(d,f,ensure_ascii=False)

@app.after_request
def cors(r):
    r.headers["Access-Control-Allow-Origin"]="*"
    r.headers["Access-Control-Allow-Methods"]="GET,POST,DELETE,PUT"
    r.headers["Access-Control-Allow-Headers"]="Content-Type,X-API-Key"
    if request.method=="OPTIONS":r.status_code=204
    return r

@app.before_request
def security_check():
    ip=request.remote_addr
    # BANチェック（5分間）
    if ip in _rate_ban and time.time()-_rate_ban[ip]<300:
        return jsonify({"error":"rate limited"}),429
    # OPTIONSは通す
    if request.method=="OPTIONS":return
    # 認証不要パス
    if request.path=="/" or request.path=="/download/apk":return
    if request.path.startswith("/pwa"):return  # PWAは認証不要
    # APIキー認証
    key=request.headers.get("X-API-Key") or request.args.get("key")
    if key!=API_KEY:
        # 不正アクセスログ
        print("[SECURITY] Unauthorized: %s %s from %s"%(request.method,request.path,ip))
        return jsonify({"error":"unauthorized"}),401
    # レート制限
    now=time.time()
    if ip not in _rate_limit:_rate_limit[ip]=[]
    _rate_limit[ip]=[t for t in _rate_limit[ip] if now-t<60]
    _rate_limit[ip].append(now)
    if len(_rate_limit[ip])>_rate_max:
        _rate_ban[ip]=now
        print("[SECURITY] Rate limit exceeded, banned: %s"%ip)
        return jsonify({"error":"rate limited"}),429

# =============================================
# === ユーザーデータ管理 ===
# =============================================
@app.route("/api/userdata/<name>",methods=["GET"])
def get_userdata(name):
    name=safe_name(name)
    fp=os.path.join(UD,name+".json")
    if not os.path.exists(fp):return jsonify({"error":"not found"}),404
    return jsonify(lj(fp,{}))

@app.route("/api/userdata/<name>",methods=["POST","PUT","OPTIONS"])
def save_userdata(name):
    if request.method=="OPTIONS":return "",204
    name=safe_name(name)
    d=request.get_json(force=True)
    if not d:return jsonify({"error":"no data"}),400
    fp=os.path.join(UD,name+".json")
    existing=lj(fp,{})
    existing.update(d)
    existing["name"]=name
    existing["updatedAt"]=time.time()
    sj(fp,existing)
    return jsonify({"ok":True})

@app.route("/api/userdata/<name>",methods=["DELETE"])
def delete_userdata(name):
    name=safe_name(name)
    fp=os.path.join(UD,name+".json")
    if os.path.exists(fp):os.remove(fp)
    return jsonify({"ok":True})

@app.route("/api/users",methods=["GET"])
def list_users():
    users=[]
    for f in os.listdir(UD):
        if f.endswith(".json"):
            users.append(f[:-5])
    return jsonify({"users":users})

# =============================================
# === ルート検索キャッシュ（Directions API代行）===
# =============================================
@app.route("/api/route",methods=["POST","OPTIONS"])
def route_search():
    if request.method=="OPTIONS":return "",204
    d=request.get_json(force=True)
    if not d or "origin" not in d or "destination" not in d:
        return jsonify({"error":"origin, destination required"}),400
    # キャッシュキー生成
    o=d["origin"];dst=d["destination"]
    wp=d.get("waypoints",[])
    avoid=d.get("avoid","")  # "tolls","highways","tolls|highways"
    cache_key_src="%s,%s_%s,%s_%s_%s" % (
        "%.5f"%o["lat"],"%.5f"%o["lng"],
        "%.5f"%dst["lat"],"%.5f"%dst["lng"],
        json.dumps(wp,sort_keys=True),avoid)
    cache_key=hashlib.md5(cache_key_src.encode()).hexdigest()
    cache_fp=os.path.join(RD,cache_key+".json")
    # キャッシュがあれば返す（24時間有効）
    if os.path.exists(cache_fp):
        cached=lj(cache_fp,None)
        if cached and time.time()-cached.get("_cachedAt",0)<86400:
            cached["_fromCache"]=True
            return jsonify(cached)
    # Google Directions API呼び出し
    params={
        "origin":"%.6f,%.6f"%(o["lat"],o["lng"]),
        "destination":"%.6f,%.6f"%(dst["lat"],dst["lng"]),
        "mode":"driving",
        "language":"ja",
        "key":GMAPS_KEY,
    }
    if wp:
        wp_str="|".join(["%.6f,%.6f"%(w["lat"],w["lng"]) for w in wp])
        params["waypoints"]="via:"+wp_str
    if avoid:params["avoid"]=avoid
    url="https://maps.googleapis.com/maps/api/directions/json?"+urllib.parse.urlencode(params)
    try:
        usage=lj(UF,{"maps":0,"directions":0})
        usage["directions"]=usage.get("directions",0)+1
        sj(UF,usage)
        req=urllib.request.Request(url,headers={"User-Agent":"SSTR-Tracker/1.0"})
        with urllib.request.urlopen(req,timeout=15) as r:
            result=json.loads(r.read().decode())
        result["_cachedAt"]=time.time()
        result["_fromCache"]=False
        sj(cache_fp,result)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error":str(e),"status":"FAILED"}),500

# =============================================
# === API使用量 ===
# =============================================
@app.route("/api/usage")
@app.route("/api/stats")
def stats():return jsonify(lj(UF,{"maps":0,"directions":0}))

@app.route("/api/usage/increment",methods=["POST","OPTIONS"])
def usage_increment():
    if request.method=="OPTIONS":return "",204
    d=request.get_json(force=True) or {}
    usage=lj(UF,{"maps":0,"directions":0})
    if d.get("maps"):usage["maps"]=usage.get("maps",0)+d["maps"]
    if d.get("directions"):usage["directions"]=usage.get("directions",0)+d["directions"]
    sj(UF,usage)
    return jsonify(usage)

# =============================================
# === 交通情報 ===
# =============================================
@app.route("/api/traffic")
def traffic():
    rr=lj(TF,[]);now=time.time()
    rr=[r for r in rr if now-r.get("ts",0)<86400]
    sj(TF,rr);return jsonify(rr)

@app.route("/api/report",methods=["POST","OPTIONS"])
def report():
    if request.method=="OPTIONS":return "",204
    d=request.get_json()
    if not d or "lat" not in d or "lng" not in d or "type" not in d:return jsonify({"error":"bad"}),400
    r={"id":int(time.time()*1000),"lat":d["lat"],"lng":d["lng"],"type":d["type"],"memo":d.get("memo",""),"ts":time.time()}
    rr=lj(TF,[]);rr.append(r);sj(TF,rr)
    return jsonify({"ok":True,"id":r["id"]})

@app.route("/api/report/<int:report_id>",methods=["DELETE"])
def delete_report(report_id):
    rr=lj(TF,[]);rr=[r for r in rr if r["id"]!=report_id];sj(TF,rr)
    return jsonify({"ok":True})

# =============================================
# === 天気情報 ===
# =============================================
@app.route("/api/weather")
def weather():return jsonify(lj(WF,{"points":[]}))

# =============================================
# === 位置共有 ===
# =============================================
@app.route("/api/location",methods=["POST","OPTIONS"])
def post_location():
    if request.method=="OPTIONS":return "",204
    d=request.get_json()
    if not d or "name" not in d or "lat" not in d or "lng" not in d:return jsonify({"error":"bad"}),400
    locs=lj(LF,{})
    locs[d["name"]]={"lat":d["lat"],"lng":d["lng"],"speed":d.get("speed",0),"heading":d.get("heading",0),"ts":time.time()}
    sj(LF,locs)
    return jsonify({"ok":True})

@app.route("/api/locations")
def get_locations():
    locs=lj(LF,{});now=time.time()
    result=[{"name":k,**v} for k,v in locs.items() if now-v.get("ts",0)<300]
    return jsonify(result)

# =============================================
# === 音声生成（VOICEVOX）===
# =============================================
@app.route("/api/voice/generate",methods=["POST","OPTIONS"])
def generate_voice():
    if request.method=="OPTIONS":return "",204
    d=request.get_json(force=True)
    if not d or "text" not in d:return jsonify({"error":"text required"}),400
    text=d["text"];key=d.get("key","custom");speaker=d.get("speaker",3)
    try:
        q=urllib.request.urlopen(urllib.request.Request(
            "http://localhost:50021/audio_query?text="+urllib.parse.quote(text)+"&speaker="+str(speaker),
            method="POST"),timeout=30).read()
        wav=urllib.request.urlopen(urllib.request.Request(
            "http://localhost:50021/synthesis?speaker="+str(speaker),
            data=q,headers={"Content-Type":"application/json"},method="POST"),timeout=30).read()
        fp=os.path.join(VD,key+".wav")
        with open(fp,"wb") as f:f.write(wav)
        return jsonify({"ok":True,"key":key,"size":len(wav)})
    except Exception as e:
        return jsonify({"error":str(e)}),500

@app.route("/api/voice/<path:key>",methods=["GET","HEAD"])
def get_voice(key):
    key=urllib.parse.unquote(key)
    key=safe_name(key)
    fp=os.path.join(VD,key+".wav")
    if os.path.exists(fp):return send_file(fp,mimetype="audio/wav")
    return jsonify({"error":"not found"}),404

# =============================================
# === オービス（スピードカメラ）===
# =============================================
@app.route("/api/orbis")
def orbis():return jsonify(lj(OF,{"cameras":[],"count":0}))

# =============================================
# === 場所名（ジオコーディング）===
# =============================================
_place_cache={}
@app.route("/api/placename")
def get_placename():
    lat=request.args.get("lat");lng=request.args.get("lng")
    if not lat or not lng:return jsonify({"error":"lat,lng required"}),400
    ck="%.4f,%.4f"%(float(lat),float(lng))
    if ck in _place_cache:return jsonify(_place_cache[ck])
    try:
        import re
        gurl="https://maps.googleapis.com/maps/api/geocode/json?latlng=%s,%s&language=ja&key=%s"%(lat,lng,GMAPS_KEY)
        gd=json.loads(urllib.request.urlopen(gurl,timeout=10).read().decode())
        if gd.get("results"):
            addr=gd["results"][0]["formatted_address"]
            clean=re.sub(r"^日本[、,]\s*","",addr)
            clean=re.sub(r"〒[\d-]+\s*","",clean)
            clean=re.sub(r"[A-Z0-9]{2,}\+[A-Z0-9]+\s*","",clean).strip()
            result={"name":clean,"address":addr}
            _place_cache[ck]=result
            return jsonify(result)
    except:pass
    return jsonify({"name":"%s,%s"%(lat,lng),"address":""})

# =============================================
# === フレンド管理 ===
# =============================================
@app.route("/api/friends",methods=["GET"])
def get_friends():
    name=request.args.get("name")
    if not name:return jsonify({"error":"name required"}),400
    friends=lj(FF,{})
    return jsonify({"friends":friends.get(name,[])})

@app.route("/api/friends/add",methods=["POST","OPTIONS"])
def add_friend():
    if request.method=="OPTIONS":return "",204
    d=request.get_json()
    if not d or "name" not in d or "friend" not in d:return jsonify({"error":"bad"}),400
    friends=lj(FF,{})
    if d["name"] not in friends:friends[d["name"]]=[]
    if d["friend"] not in friends[d["name"]]:friends[d["name"]].append(d["friend"])
    if d["friend"] not in friends:friends[d["friend"]]=[]
    if d["name"] not in friends[d["friend"]]:friends[d["friend"]].append(d["name"])
    sj(FF,friends)
    return jsonify({"ok":True})

@app.route("/api/friends/remove",methods=["POST","OPTIONS"])
def remove_friend():
    if request.method=="OPTIONS":return "",204
    d=request.get_json()
    if not d or "name" not in d or "friend" not in d:return jsonify({"error":"bad"}),400
    friends=lj(FF,{})
    if d["name"] in friends and d["friend"] in friends[d["name"]]:friends[d["name"]].remove(d["friend"])
    if d["friend"] in friends and d["name"] in friends[d["friend"]]:friends[d["friend"]].remove(d["name"])
    sj(FF,friends)
    return jsonify({"ok":True})

# =============================================
# === プラン共有 ===
# =============================================
@app.route("/api/plans/share",methods=["POST","OPTIONS"])
def share_plan():
    if request.method=="OPTIONS":return "",204
    d=request.get_json()
    if not d or "from" not in d or "to" not in d or "plan" not in d:return jsonify({"error":"bad"}),400
    shared=lj(SF,{})
    if d["to"] not in shared:shared[d["to"]]=[]
    plan=d["plan"];plan["sharedBy"]=d["from"];plan["sharedAt"]=time.time()
    shared[d["to"]].append(plan)
    sj(SF,shared)
    return jsonify({"ok":True})

@app.route("/api/plans/shared")
def get_shared_plans():
    name=request.args.get("name")
    if not name:return jsonify({"error":"name required"}),400
    shared=lj(SF,{})
    return jsonify({"plans":shared.get(name,[])})

# =============================================
# === カスタムプラン保存（NAS集中管理）===
# =============================================
@app.route("/api/plans/<name>",methods=["GET"])
def get_plans(name):
    name=safe_name(name)
    fp=os.path.join(UD,name+".json")
    ud=lj(fp,{})
    return jsonify({"plans":ud.get("customPlans",[])})

@app.route("/api/plans/<name>",methods=["POST","OPTIONS"])
def save_plans(name):
    if request.method=="OPTIONS":return "",204
    name=safe_name(name)
    d=request.get_json(force=True)
    if not d or "plans" not in d:return jsonify({"error":"plans required"}),400
    fp=os.path.join(UD,name+".json")
    ud=lj(fp,{})
    ud["name"]=name
    ud["customPlans"]=d["plans"]
    ud["updatedAt"]=time.time()
    sj(fp,ud)
    return jsonify({"ok":True})

# =============================================
# === APKダウンロード（認証不要）===
# =============================================
@app.route("/download/apk")
def download_apk():
    fp=os.path.join(BD,"sstr-tracker.apk")
    if os.path.exists(fp):return send_file(fp,as_attachment=True,download_name="sstr-tracker.apk")
    return jsonify({"error":"not found"}),404

# =============================================
# === PWA配信 ===
# =============================================
PWA_DIR=os.path.join(BD,"pwa")
@app.route("/pwa/")
def pwa_index():
    r=send_file(os.path.join(PWA_DIR,"index.html"))
    r.headers["Cache-Control"]="no-cache, no-store, must-revalidate"
    r.headers["Pragma"]="no-cache"
    r.headers["Expires"]="0"
    return r
@app.route("/pwa/<path:filename>")
def pwa_static(filename):
    fp=os.path.join(PWA_DIR,filename)
    if not os.path.exists(fp):return jsonify({"error":"not found"}),404
    r=send_file(fp)
    if filename.endswith('.html'):
        r.headers["Cache-Control"]="no-cache, no-store, must-revalidate"
    return r

# =============================================
@app.route("/")
def index():
    return jsonify({"status":"ok","version":"2.0","endpoints":[
        "/api/userdata/<name>","/api/users",
        "/api/route","/api/usage",
        "/api/traffic","/api/weather",
        "/api/location","/api/locations",
        "/api/voice/generate","/api/voice/<key>",
        "/api/orbis","/api/placename",
        "/api/friends","/api/plans/<name>","/api/plans/share"
    ]})

if __name__=="__main__":app.run(host="0.0.0.0",port=3456)
