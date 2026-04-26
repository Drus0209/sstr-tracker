#!/usr/bin/env python3
"""SSTR API Server — NAS集中管理版（セキュリティ強化）"""
import json,os,time,hashlib,urllib.parse,urllib.request,functools,re,secrets,sqlite3,threading
from flask import Flask,jsonify,request,send_file,abort
app=Flask(__name__)
BD=os.path.dirname(os.path.abspath(__file__))

# === セキュリティ設定 ===
API_KEY="sstr2026_k4w4s4k1_zx4r"

# Gemini APIキー（.env から読む）
GEMINI_API_KEY=""
try:
    _envp=os.path.join(BD,".env")
    if os.path.exists(_envp):
        for _ln in open(_envp):
            _ln=_ln.strip()
            if _ln.startswith("GEMINI_API_KEY="):
                GEMINI_API_KEY=_ln.split("=",1)[1].strip()
                break
except Exception:
    pass

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

# === SQLite ===
DB_PATH=os.path.join(BD,"sstr.db")
_db_local=threading.local()
def get_db():
    if not hasattr(_db_local,'conn') or _db_local.conn is None:
        _db_local.conn=sqlite3.connect(DB_PATH,timeout=10)
        _db_local.conn.execute("PRAGMA journal_mode=WAL")
        _db_local.conn.execute("PRAGMA busy_timeout=5000")
        _db_local.conn.row_factory=sqlite3.Row
    return _db_local.conn

def init_db():
    db=sqlite3.connect(DB_PATH,timeout=10)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=5000")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS locations (
            name TEXT PRIMARY KEY,
            lat REAL, lng REAL, speed REAL DEFAULT 0,
            heading REAL DEFAULT 0, ts REAL
        );
        CREATE TABLE IF NOT EXISTS usage_counter (
            id INTEGER PRIMARY KEY CHECK(id=1),
            maps INTEGER DEFAULT 0, directions INTEGER DEFAULT 0
        );
        INSERT OR IGNORE INTO usage_counter(id,maps,directions) VALUES(1,0,0);
        CREATE TABLE IF NOT EXISTS friends (
            user_name TEXT, friend_name TEXT,
            PRIMARY KEY(user_name, friend_name)
        );
        CREATE TABLE IF NOT EXISTS friend_requests (
            from_name TEXT, to_name TEXT, ts REAL,
            PRIMARY KEY(from_name, to_name)
        );
        CREATE TABLE IF NOT EXISTS shared_plans (
            name TEXT PRIMARY KEY, plan TEXT, updated REAL
        );
    """)
    # 既存JSONデータ移行
    import json as _j
    # locations
    try:
        locs=_j.load(open(os.path.join(BD,"locations.json")))
        for k,v in locs.items():
            db.execute("INSERT OR REPLACE INTO locations VALUES(?,?,?,?,?,?)",
                (k,v.get("lat"),v.get("lng"),v.get("speed",0),v.get("heading",0),v.get("ts",0)))
    except: pass
    # usage
    try:
        u=_j.load(open(os.path.join(BD,"usage.json")))
        db.execute("UPDATE usage_counter SET maps=?,directions=? WHERE id=1",(u.get("maps",0),u.get("directions",0)))
    except: pass
    # friends
    try:
        fr=_j.load(open(os.path.join(BD,"friends.json")))
        for user,flist in fr.items():
            if isinstance(flist,list):
                for f in flist:
                    db.execute("INSERT OR IGNORE INTO friends VALUES(?,?)",(user,f))
    except: pass
    # shared_plans
    try:
        sp=_j.load(open(os.path.join(BD,"shared_plans.json")))
        for name,plan in sp.items():
            db.execute("INSERT OR REPLACE INTO shared_plans VALUES(?,?,?)",(name,_j.dumps(plan,ensure_ascii=False),time.time()))
    except: pass
    db.commit()
    db.close()
init_db()

GMAPS_KEY="AIzaSyBwPBSu3pJ7LBsQ7WvSbTWiQsFY0R8cREY"

# === APIイベントログ（パフォーマンス分析用） ===
LOG_DIR=os.path.join(BD,"logs");os.makedirs(LOG_DIR,exist_ok=True)
def log_event(event_type,duration_ms,status,meta=None):
    """イベントをJSONLで日毎ファイルに追記。失敗しても本処理を妨げない。"""
    try:
        day=time.strftime("%Y%m%d")
        fp=os.path.join(LOG_DIR,"api_events_"+day+".jsonl")
        rec={"t":time.time(),"type":event_type,"ms":round(duration_ms,1),"status":status}
        if meta:rec["meta"]=meta
        with open(fp,"a") as f:f.write(json.dumps(rec,ensure_ascii=False)+"\n")
    except:pass

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
    # 全リクエストを自動ログ
    try:
        if hasattr(request,"_log_t0") and not request.path.startswith("/api/voice_stats") and request.path!="/api/voice/generate":
            dur=(time.time()-request._log_t0)*1000
            # パス先頭2セグメントで分類: /api/voice/xxx → http_api_voice / /api/route → http_api_route
            parts=[p for p in request.path.strip("/").split("/") if p][:2]
            etype="http_"+"_".join(parts) if parts else "http_root"
            status="ok" if r.status_code<400 else "error"
            meta={"path":request.path,"method":request.method,"code":r.status_code}
            if r.status_code>=400:meta["ip"]=request.remote_addr
            log_event(etype,dur,status,meta)
    except:pass
    return r

@app.before_request
def _log_start():
    request._log_t0=time.time()

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
    traffic=bool(d.get("traffic",False))  # 渋滞考慮: trueなら departure_time=now で取得（キャッシュ短縮）
    cache_key_src="%s,%s_%s,%s_%s_%s_%s" % (
        "%.5f"%o["lat"],"%.5f"%o["lng"],
        "%.5f"%dst["lat"],"%.5f"%dst["lng"],
        json.dumps(wp,sort_keys=True),avoid,"T" if traffic else "")
    cache_key=hashlib.md5(cache_key_src.encode()).hexdigest()
    cache_fp=os.path.join(RD,cache_key+".json")
    # キャッシュ有効期限: 通常24h、渋滞考慮は2分
    cache_ttl=120 if traffic else 86400
    if os.path.exists(cache_fp):
        cached=lj(cache_fp,None)
        if cached and time.time()-cached.get("_cachedAt",0)<cache_ttl:
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
    if traffic:
        params["departure_time"]="now"
        params["traffic_model"]="best_guess"
    if wp:
        wp_str="|".join(["%.6f,%.6f"%(w["lat"],w["lng"]) for w in wp])
        params["waypoints"]="via:"+wp_str
    if avoid:params["avoid"]=avoid
    url="https://maps.googleapis.com/maps/api/directions/json?"+urllib.parse.urlencode(params)
    try:
        db=get_db()
        db.execute("UPDATE usage_counter SET directions=directions+1 WHERE id=1")
        db.commit()
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
def stats():
    s=lj(os.path.join(BD,"stats_cache.json"),None)
    db=get_db()
    row=db.execute("SELECT maps,directions FROM usage_counter WHERE id=1").fetchone()
    u={"maps":row["maps"],"directions":row["directions"]} if row else {"maps":0,"directions":0}
    if s and isinstance(s,dict) and "directions" in s:
        r={"maps":max(s.get("maps",0),u.get("maps",0)),"directions":max(s.get("directions",0),u.get("directions",0))}
        if "places" in s:r["places"]=s["places"]
        if "geocoding" in s:r["geocoding"]=s["geocoding"]
        if "breakdown" in s:r["breakdown"]=s["breakdown"]
        if "timestamp" in s:r["timestamp"]=s["timestamp"]
        return jsonify(r)
    return jsonify(u)

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
    db=get_db()
    db.execute("INSERT OR REPLACE INTO locations VALUES(?,?,?,?,?,?)",
        (d["name"],d["lat"],d["lng"],d.get("speed",0),d.get("heading",0),time.time()))
    db.commit()
    return jsonify({"ok":True})

@app.route("/api/locations")
def get_locations():
    db=get_db();now=time.time()
    rows=db.execute("SELECT name,lat,lng,speed,heading,ts FROM locations WHERE ts>?",(now-300,)).fetchall()
    result=[{"name":r["name"],"lat":r["lat"],"lng":r["lng"],"speed":r["speed"],"heading":r["heading"],"ts":r["ts"]} for r in rows]
    return jsonify(result)

# =============================================
# === 音声生成（VOICEVOX）===
# =============================================
VOICEVOX_HOSTS=[
    ("nas","http://localhost:50021",30),   # プライマリ: NAS Docker
    ("pc","http://100.87.205.49:50021",8),  # フォールバック: PC (起動時のみ)
]
def _call_voicevox(host,text,speaker,timeout):
    q=urllib.request.urlopen(urllib.request.Request(
        host+"/audio_query?text="+urllib.parse.quote(text)+"&speaker="+str(speaker),
        method="POST"),timeout=timeout).read()
    wav=urllib.request.urlopen(urllib.request.Request(
        host+"/synthesis?speaker="+str(speaker),
        data=q,headers={"Content-Type":"application/json"},method="POST"),timeout=timeout).read()
    return wav

@app.route("/api/voice/generate",methods=["POST","OPTIONS"])
def generate_voice():
    if request.method=="OPTIONS":return "",204
    d=request.get_json(force=True)
    if not d or "text" not in d:return jsonify({"error":"text required"}),400
    text=d["text"];key=d.get("key","custom");speaker=d.get("speaker",3)
    key=safe_name(key)# 保存ファイル名とGET側のキー正規化を一致させる
    last_err=None
    for name,host,tmo in VOICEVOX_HOSTS:
        t0=time.time()
        try:
            wav=_call_voicevox(host,text,speaker,tmo)
            fp=os.path.join(VD,key+".wav")
            with open(fp,"wb") as f:f.write(wav)
            log_event("voice_generate",(time.time()-t0)*1000,"ok",{"key":key,"size":len(wav),"len":len(text),"host":name})
            return jsonify({"ok":True,"key":key,"size":len(wav),"host":name})
        except Exception as e:
            last_err=str(e)
            log_event("voice_generate",(time.time()-t0)*1000,"error",{"key":key,"err":last_err[:200],"len":len(text),"host":name})
    return jsonify({"error":last_err or "all hosts failed"}),500

@app.route("/api/voice/prefetch",methods=["POST","OPTIONS"])
def prefetch_voices():
    """複数音声を一括生成。既存キャッシュは即返却。
    body: {items:[{text,key},{text,key},...]}
    返却: {ok:true, results:[{key,cached:bool,url}]}
    """
    if request.method=="OPTIONS":return "",204
    d=request.get_json(force=True)
    if not d or "items" not in d:return jsonify({"error":"items required"}),400
    results=[]
    for it in d["items"]:
        text=it.get("text","");key=safe_name(it.get("key","custom"))
        if not text:continue
        fp=os.path.join(VD,key+".wav")
        if os.path.exists(fp):
            results.append({"key":key,"cached":True,"size":os.path.getsize(fp)})
            continue
        # 新規生成
        for name,host,tmo in VOICEVOX_HOSTS:
            try:
                wav=_call_voicevox(host,text,3,tmo)
                with open(fp,"wb") as f:f.write(wav)
                results.append({"key":key,"cached":False,"size":len(wav),"host":name})
                break
            except Exception:
                continue
        else:
            results.append({"key":key,"error":"failed"})
    return jsonify({"ok":True,"results":results})

@app.route("/api/voice_stats")
def voice_stats():
    """直近N日のAPIイベントを集計。クエリ ?days=1 (デフォルト1)"""
    try:
        days=max(1,min(int(request.args.get("days","1")),7))
    except:
        days=1
    records=[]
    for i in range(days):
        day=time.strftime("%Y%m%d",time.localtime(time.time()-i*86400))
        fp=os.path.join(LOG_DIR,"api_events_"+day+".jsonl")
        if os.path.exists(fp):
            try:
                with open(fp,"r") as f:
                    for line in f:
                        try:records.append(json.loads(line))
                        except:pass
            except:pass
    by_type={}
    for r in records:
        t=r.get("type","unknown")
        if t not in by_type:by_type[t]={"count":0,"ok":0,"error":0,"total_ms":0,"max_ms":0,"errors":[]}
        b=by_type[t]
        b["count"]+=1
        if r.get("status")=="ok":b["ok"]+=1
        elif r.get("status")=="error":
            b["error"]+=1
            e=r.get("meta",{}).get("err","")
            if e and len(b["errors"])<5:b["errors"].append(e)
        ms=r.get("ms",0)
        b["total_ms"]+=ms
        if ms>b["max_ms"]:b["max_ms"]=ms
    for t,b in by_type.items():
        b["avg_ms"]=round(b["total_ms"]/b["count"],1) if b["count"]>0 else 0
        del b["total_ms"]
    return jsonify({"days":days,"total_events":len(records),"by_type":by_type})

@app.route("/api/log_tail")
def log_tail():
    """直近Nイベントを返す（監視ダッシュボード用）。?n=100"""
    try:n=max(1,min(int(request.args.get("n","50")),500))
    except:n=50
    day=time.strftime("%Y%m%d")
    fp=os.path.join(LOG_DIR,"api_events_"+day+".jsonl")
    events=[]
    if os.path.exists(fp):
        try:
            with open(fp,"r") as f:
                lines=f.readlines()[-n:]
                for line in lines:
                    try:events.append(json.loads(line))
                    except:pass
        except:pass
    return jsonify({"events":events})

@app.route("/monitor")
def monitor_page():
    """PC ブラウザ向けライブモニタ。?key=APIKEY でアクセス"""
    # security_checkで既に認証済
    return MONITOR_HTML.replace("__API_KEY__",API_KEY)

MONITOR_HTML="""<!DOCTYPE html><html><head><meta charset="utf-8"><title>SSTR NAS Monitor</title>
<style>
body{font-family:-apple-system,sans-serif;background:#06060c;color:#e8e8f0;margin:0;padding:20px;}
h1{color:#00d4ff;margin:0 0 10px;font-size:20px;}
.sub{color:#888;font-size:12px;margin-bottom:20px;}
table{width:100%;border-collapse:collapse;margin-bottom:20px;font-size:13px;}
th{background:#111118;color:#00d4ff;text-align:left;padding:8px;border-bottom:1px solid #333;}
td{padding:6px 8px;border-bottom:1px solid #1e1e2e;}
tr:hover{background:#111118;}
.ok{color:#00e676;}
.err{color:#ff4444;font-weight:700;}
.slow{color:#ffd740;}
.box{background:#111118;border:1px solid #1e1e2e;border-radius:8px;padding:15px;margin-bottom:20px;}
h2{color:#ff9100;font-size:14px;margin:0 0 10px;}
.ev{font-family:monospace;font-size:11px;padding:3px 0;border-bottom:1px solid #1a1a22;}
.ev.err{color:#ff6666;}
.ts{color:#666;}
.err-list{color:#ff9999;font-size:11px;margin-top:5px;}
#status{float:right;font-size:11px;color:#00e676;}
#status.stale{color:#ff9100;}
</style></head><body>
<h1>SSTR NAS Monitor <span id="status">●</span></h1>
<div class="sub">3秒毎更新 / API key: __API_KEY__</div>
<div class="box"><h2>📊 集計（直近24h）</h2><div id="stats"></div></div>
<div class="box"><h2>📜 直近イベント（最新50件）</h2><div id="events"></div></div>
<script>
const KEY="__API_KEY__";
async function refresh(){
  try{
    const s=await fetch("/api/voice_stats?days=1",{headers:{"X-API-Key":KEY}}).then(r=>r.json());
    const e=await fetch("/api/log_tail?n=50",{headers:{"X-API-Key":KEY}}).then(r=>r.json());
    let h='<table><tr><th>エンドポイント</th><th>件数</th><th>成功</th><th>エラー</th><th>平均ms</th><th>最大ms</th><th>直近エラー</th></tr>';
    const types=Object.keys(s.by_type||{}).sort();
    for(const t of types){const b=s.by_type[t];
      const errCls=b.error>0?'err':'ok';
      const slowCls=b.avg_ms>3000?'slow':'';
      h+=`<tr><td>${t}</td><td>${b.count}</td><td class="ok">${b.ok}</td><td class="${errCls}">${b.error}</td><td class="${slowCls}">${b.avg_ms}</td><td>${b.max_ms}</td><td class="err-list">${(b.errors||[]).slice(0,2).join('<br>')}</td></tr>`;
    }
    h+='</table>';
    document.getElementById('stats').innerHTML=h;
    let eh='';
    for(const ev of (e.events||[]).slice().reverse()){
      const d=new Date(ev.t*1000);
      const ts=d.toTimeString().slice(0,8);
      const cls=ev.status==='error'?'ev err':'ev';
      const meta=ev.meta?JSON.stringify(ev.meta).slice(0,120):'';
      eh+=`<div class="${cls}"><span class="ts">${ts}</span> <b>${ev.type}</b> ${ev.ms}ms [${ev.status}] ${meta}</div>`;
    }
    document.getElementById('events').innerHTML=eh||'<div style="color:#666">イベント無し</div>';
    document.getElementById('status').textContent='● '+new Date().toTimeString().slice(0,8);
    document.getElementById('status').className='';
  }catch(ex){
    document.getElementById('status').textContent='● 接続エラー';
    document.getElementById('status').className='stale';
  }
}
refresh();setInterval(refresh,3000);
</script></body></html>"""

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

RQ=os.path.join(BD,"friend_requests.json")  # { to_name: [{from, ts}, ...] }

@app.route("/api/friends/add",methods=["POST","OPTIONS"])
def add_friend():
    """フレンド申請を送る（相手の承認待ち状態にする）"""
    if request.method=="OPTIONS":return "",204
    d=request.get_json()
    if not d or "name" not in d or "friend" not in d:return jsonify({"error":"bad"}),400
    fr=d["name"];to=d["friend"]
    if fr==to:return jsonify({"error":"self"}),400
    # 既にフレンドなら何もしない
    friends=lj(FF,{})
    if to in friends.get(fr,[]):return jsonify({"ok":True,"already_friend":True})
    # 申請保存
    reqs=lj(RQ,{})
    if to not in reqs:reqs[to]=[]
    # 既存申請があれば上書き（タイムスタンプ更新）
    reqs[to]=[r for r in reqs[to] if r.get("from")!=fr]
    reqs[to].append({"from":fr,"ts":time.time()})
    sj(RQ,reqs)
    return jsonify({"ok":True,"pending":True})

@app.route("/api/friends/pending",methods=["GET"])
def pending_friends():
    """自分宛の保留中申請を取得"""
    name=request.args.get("name")
    if not name:return jsonify({"error":"name required"}),400
    reqs=lj(RQ,{})
    return jsonify({"pending":reqs.get(name,[])})

@app.route("/api/friends/respond",methods=["POST","OPTIONS"])
def respond_friend():
    """申請に応答（accept/reject）"""
    if request.method=="OPTIONS":return "",204
    d=request.get_json()
    if not d or "name" not in d or "from" not in d or "accept" not in d:return jsonify({"error":"bad"}),400
    me=d["name"];fr=d["from"];accept=bool(d["accept"])
    reqs=lj(RQ,{})
    if me not in reqs:return jsonify({"error":"no_request"}),404
    reqs[me]=[r for r in reqs[me] if r.get("from")!=fr]
    if not reqs[me]:del reqs[me]
    sj(RQ,reqs)
    if accept:
        friends=lj(FF,{})
        if me not in friends:friends[me]=[]
        if fr not in friends[me]:friends[me].append(fr)
        if fr not in friends:friends[fr]=[]
        if me not in friends[fr]:friends[fr].append(me)
        sj(FF,friends)
    return jsonify({"ok":True,"accepted":accept})

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
# === バージョン情報（認証不要）===
# =============================================
@app.route("/api/version")
def api_version():
    # minVersion: これより古いと強制更新 / latest: 最新推奨バージョン
    return jsonify({
        "minVersion":"260414",
        "latest":"260427",
        "apkUrl":"/download/apk"
    })

# =============================================
# === AI ルート提案（Gemini Flash）===
# =============================================
@app.route("/api/ai/plan",methods=["POST","OPTIONS"])
def ai_plan():
    if request.method=="OPTIONS":return "",204
    if not GEMINI_API_KEY:return jsonify({"error":"gemini_not_configured"}),500
    d=request.get_json(force=True)
    if not d:return jsonify({"error":"bad_request"}),400
    origin=d.get("origin","")
    budget=d.get("budget_hours",6)
    prefs=d.get("preferences","絶景 グルメ")
    start=d.get("start_time","09:00")
    prompt=(
        "あなたは日本のバイクツーリングプランナーです。以下条件で日帰りツーリングプランを作ってください。\n"
        f"出発地：{origin}\n"
        f"出発時刻：{start}\n"
        f"所要時間：約{budget}時間\n"
        f"希望：{prefs}\n\n"
        "制約：\n"
        "- スポットは3〜6箇所\n"
        "- 実在する道の駅・観光地・飲食店のみ（地名だけの抽象表現NG）\n"
        "- 総走行距離は所要時間の目安（下道50km/h, 高速80km/h想定）\n"
        "- 最後は出発地付近に戻るか、明確なゴール地点\n\n"
        "JSON形式で返してください（マークダウンコードブロック無し、生JSONのみ）：\n"
        '{"summary":"プラン概要1行","stops":[{"name":"スポット名","area":"所在地(市町村)","time":"HH:MM","dur_min":滞在分,"memo":"一言説明"}]}'
    )
    req_body={"contents":[{"parts":[{"text":prompt}]}],"generationConfig":{"temperature":0.7,"responseMimeType":"application/json"}}
    url=f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={GEMINI_API_KEY}"
    try:
        req=urllib.request.Request(url,data=json.dumps(req_body).encode("utf-8"),headers={"Content-Type":"application/json"})
        resp=urllib.request.urlopen(req,timeout=30).read()
        rd=json.loads(resp)
        text=rd["candidates"][0]["content"]["parts"][0]["text"]
        plan=json.loads(text)
    except Exception as e:
        return jsonify({"error":"ai_failed","detail":str(e)}),500
    # スポット毎にGoogle Places APIで座標取得（ハルシネーション対策）
    # 注: Places APIキーは既存のMaps JS APIキーを使用（クライアント側経由でもOKだが、
    #     ここではAIが指定した名前ベースで検証せず、クライアント側でPlaces Autocompleteに通す運用とする）
    return jsonify({"ok":True,"plan":plan})

# =============================================
# === Prometheus metrics（fetch鮮度監視用）===
# =============================================
@app.route("/metrics")
def metrics():
    files=[("weather_json",WF),("stats_cache_json",os.path.join(BD,"stats_cache.json")),("orbis_cache_json",OF)]
    lines=[
        "# HELP fetch_last_update_seconds Last modified time of fetch output files (unix seconds)",
        "# TYPE fetch_last_update_seconds gauge",
    ]
    for label,path in files:
        mt=os.path.getmtime(path) if os.path.exists(path) else 0
        lines.append('fetch_last_update_seconds{file="%s"} %d'%(label,int(mt)))
    return ("\n".join(lines)+"\n","200 OK",{"Content-Type":"text/plain; version=0.0.4"})

# =============================================
# === APKダウンロード（認証不要）===
# =============================================
@app.route("/download/apk")
def download_apk():
    fp=os.path.join(BD,"sstr-tracker.apk")
    if os.path.exists(fp):
        # バージョン付きファイル名で配信（DL履歴の重複ダイアログ回避）
        ver=request.args.get("v","")
        fn="sstr-tracker"+("_v"+ver if ver else "")+".apk"
        return send_file(fp,as_attachment=True,download_name=fn)
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
