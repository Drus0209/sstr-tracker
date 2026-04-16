#!/usr/bin/env python3
"""Zabbix 7.0 自動セットアップ: PW変更・Gmail通知・ホスト/テンプレート登録・アクション

環境変数:
  ZBX_URL              Zabbix API URL (default: http://localhost:8080/api_jsonrpc.php)
  ZBX_ADMIN_OLD_PW     初期Admin PW (default: zabbix)
  ZBX_ADMIN_NEW_PW     設定後のAdmin PW (必須)
  GMAIL_USER           通知元Gmailアドレス (必須)
  GMAIL_APP_PW         Gmailアプリパスワード (必須・16桁)
"""
import json, os, urllib.request, sys, time

URL = os.environ.get("ZBX_URL", "http://localhost:8080/api_jsonrpc.php")
ADMIN_OLD_PW = os.environ.get("ZBX_ADMIN_OLD_PW", "zabbix")
ADMIN_NEW_PW = os.environ.get("ZBX_ADMIN_NEW_PW")
GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_APP_PW = os.environ.get("GMAIL_APP_PW")
FLASK_BASE = os.environ.get("FLASK_BASE", "")
FLASK_API_KEY = os.environ.get("FLASK_API_KEY", "")
SWITCH_IP = os.environ.get("SWITCH_IP", "")
NAS_TS_IP = os.environ.get("NAS_TS_IP", NAS_TS_IP)
PC_TS_IP = os.environ.get("PC_TS_IP", PC_TS_IP)
SNMP_COMMUNITY = os.environ.get("SNMP_COMMUNITY", "public")

if not (ADMIN_NEW_PW and GMAIL_USER and GMAIL_APP_PW):
    sys.exit("ERROR: ZBX_ADMIN_NEW_PW / GMAIL_USER / GMAIL_APP_PW を環境変数で指定してください")

HOSTS = [
    # (host, visible_name, interfaces, template_names, groups, tags)
    {"host":"nas-as5304t","name":"NAS (AS5304T)",
     "interfaces":[{"type":1,"main":1,"useip":1,"ip":NAS_TS_IP,"dns":"","port":"10050"},
                   {"type":2,"main":1,"useip":1,"ip":NAS_TS_IP,"dns":"","port":"161",
                    "details":{"version":2,"community":"{$SNMP_COMMUNITY}","bulk":1}}],
     "templates":["Linux by Zabbix agent","ICMP Ping"],
     "groups":["Linux servers"]},
    {"host":"pc-windows","name":"PC (Windows Home)",
     "interfaces":[{"type":1,"main":1,"useip":1,"ip":PC_TS_IP,"dns":"","port":"10050"}],
     "templates":["Windows by Zabbix agent","ICMP Ping"],
     "groups":["Windows servers"]},
    {"host":"flask-api","name":"SSTR Flask API",
     "interfaces":[{"type":1,"main":1,"useip":1,"ip":NAS_TS_IP,"dns":"","port":"10050"}],
     "templates":[],
     "groups":["Applications"]},
    {"host":"voicevox-pc","name":"VOICEVOX (PC)",
     "interfaces":[{"type":1,"main":1,"useip":1,"ip":PC_TS_IP,"dns":"","port":"10050"}],
     "templates":[],
     "groups":["Applications"]},
    {"host":"voicevox-nas","name":"VOICEVOX (NAS Docker)",
     "interfaces":[{"type":1,"main":1,"useip":1,"ip":NAS_TS_IP,"dns":"","port":"10050"}],
     "templates":[],
     "groups":["Applications"]},
    {"host":"switch-sg3210","name":"Switch (TP-Link SG3210X-M2)",
     "interfaces":[{"type":2,"main":1,"useip":1,"ip":SWITCH_IP,"dns":"","port":"161",
                    "details":{"version":2,"community":"{$SNMP_COMMUNITY}","bulk":1}}],
     "templates":["Generic SNMPv2","Network Generic Device SNMP"],
     "groups":["Network devices"]},
]

HTTP_CHECKS = [
    # (host, item_name, key_, url, match)
    ("flask-api","Flask /api/version","web.page.get[flask_api_version]",
     f"{FLASK_BASE}/api/version" + (f"?key={FLASK_API_KEY}" if FLASK_API_KEY else "")),
    ("voicevox-pc","VOICEVOX PC /version","web.page.get[voicevox_pc]",
     f"http://{PC_TS_IP}:50021/version"),
    ("voicevox-nas","VOICEVOX NAS /version","web.page.get[voicevox_nas]",
     f"http://{NAS_TS_IP}:50021/version"),
]

_auth = None
_rid = 0
def rpc(method, params, auth=True):
    global _rid; _rid += 1
    body = {"jsonrpc":"2.0","method":method,"params":params,"id":_rid}
    if auth and _auth: body["auth"]=_auth
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), headers={"Content-Type":"application/json-rpc"})
    r = json.loads(urllib.request.urlopen(req, timeout=30).read())
    if "error" in r: raise Exception(f"{method}: {r['error']}")
    return r["result"]

def login(user, pw):
    global _auth
    _auth = rpc("user.login",{"username":user,"password":pw}, auth=False)
    print(f"[login] {user} OK")

def change_admin_pw(current_pw):
    users = rpc("user.get",{"filter":{"username":"Admin"}})
    uid = users[0]["userid"]
    rpc("user.update",{"userid":uid,"current_passwd":current_pw,"passwd":ADMIN_NEW_PW})
    print(f"[user.update] Admin password changed")

def ensure_group(name):
    g = rpc("hostgroup.get",{"filter":{"name":name}})
    if g: return g[0]["groupid"]
    return rpc("hostgroup.create",{"name":name})["groupids"][0]

def get_template_ids(names):
    if not names: return []
    t = rpc("template.get",{"filter":{"host":names},"output":["templateid","host"]})
    found = {x["host"] for x in t}
    for n in names:
        if n not in found: print(f"  [WARN] template not found: {n}")
    return [{"templateid":x["templateid"]} for x in t]

def create_gmail_media():
    existing = rpc("mediatype.get",{"filter":{"name":"Gmail"}})
    params = {
        "name":"Gmail","type":0,  # 0=email
        "smtp_server":"smtp.gmail.com","smtp_port":587,
        "smtp_helo":"gmail.com","smtp_email":GMAIL_USER,
        "smtp_authentication":1,"username":GMAIL_USER,"passwd":GMAIL_APP_PW,
        "smtp_security":1,  # STARTTLS
        "smtp_verify_peer":1,"smtp_verify_host":1,
        "content_type":1,  # HTML
        "status":0,
        "message_templates":[
            {"eventsource":0,"recovery":0,"subject":"[Zabbix] {EVENT.NAME}",
             "message":"<b>{EVENT.NAME}</b><br>Host: {HOST.NAME}<br>Severity: {EVENT.SEVERITY}<br>Time: {EVENT.TIME} {EVENT.DATE}<br>Info: {EVENT.OPDATA}"},
            {"eventsource":0,"recovery":1,"subject":"[Zabbix RESOLVED] {EVENT.NAME}",
             "message":"<b>RESOLVED: {EVENT.NAME}</b><br>Host: {HOST.NAME}<br>Time: {EVENT.RECOVERY.TIME} {EVENT.RECOVERY.DATE}"},
        ],
    }
    if existing:
        params["mediatypeid"]=existing[0]["mediatypeid"]
        rpc("mediatype.update",params)
        print("[mediatype] Gmail updated")
        return existing[0]["mediatypeid"]
    mid = rpc("mediatype.create",params)["mediatypeids"][0]
    print("[mediatype] Gmail created")
    return mid

def attach_media_to_admin(mid):
    users = rpc("user.get",{"filter":{"username":"Admin"},"selectMedias":"extend"})
    uid = users[0]["userid"]
    medias = users[0].get("medias",[])
    has = any(m.get("mediatypeid")==mid and GMAIL_USER in m.get("sendto","") for m in medias)
    if has:
        print("[user.media] Admin already has Gmail media")
        return
    medias.append({"mediatypeid":mid,"sendto":[GMAIL_USER],"active":0,"severity":63,"period":"1-7,00:00-24:00"})
    clean = [{"mediatypeid":m["mediatypeid"],"sendto":m["sendto"] if isinstance(m["sendto"],list) else [m["sendto"]],
              "active":int(m.get("active",0)),"severity":int(m.get("severity",63)),
              "period":m.get("period","1-7,00:00-24:00")} for m in medias]
    rpc("user.update",{"userid":uid,"medias":clean})
    print(f"[user.media] Admin → {GMAIL_USER} attached")

def ensure_host(h):
    existing = rpc("host.get",{"filter":{"host":h["host"]}})
    gids = [{"groupid":ensure_group(g)} for g in h["groups"]]
    tpls = get_template_ids(h["templates"])
    params = {
        "host":h["host"],"name":h["name"],
        "interfaces":h["interfaces"],
        "groups":gids,"templates":tpls,
        "macros":[{"macro":"{$SNMP_COMMUNITY}","value":SNMP_COMMUNITY}],
    }
    if existing:
        params["hostid"]=existing[0]["hostid"]
        # update doesn't accept 'host' rename freely; remove
        params.pop("host",None)
        rpc("host.update",params)
        print(f"[host.update] {h['host']}")
        return existing[0]["hostid"]
    hid = rpc("host.create",params)["hostids"][0]
    print(f"[host.create] {h['host']} id={hid}")
    return hid

def create_http_item(hostid, host_key, name, key_, url):
    existing = rpc("item.get",{"filter":{"hostid":hostid,"key_":key_}})
    params = {
        "hostid":hostid,"name":name,"key_":key_,"type":19,  # 19=HTTP agent
        "value_type":4,  # text
        "url":url,"delay":"60s","timeout":"10s",
        "request_method":0,"retrieve_mode":0,
    }
    if existing:
        params["itemid"]=existing[0]["itemid"]; params.pop("hostid"); params.pop("key_")
        rpc("item.update",params); print(f"  [item.update] {name}")
        return existing[0]["itemid"]
    iid = rpc("item.create",params)["itemids"][0]
    print(f"  [item.create] {name}")
    # trigger: no data for 3min
    tname=f"{name} unreachable"
    expr=f"nodata(/{host_key}/{key_},3m)=1"
    et = rpc("trigger.get",{"filter":{"description":tname}})
    tp={"description":tname,"expression":expr,"priority":4}
    if et:
        tp["triggerid"]=et[0]["triggerid"]; rpc("trigger.update",tp)
    else:
        rpc("trigger.create",tp); print(f"  [trigger.create] {tname}")
    return iid

def create_notify_action(mid):
    name = "Notify Admin on any problem"
    existing = rpc("action.get",{"filter":{"name":name}})
    ops = [{"operationtype":0,"opmessage":{"mediatypeid":mid,"default_msg":1},
            "opmessage_usr":[{"userid":rpc("user.get",{"filter":{"username":"Admin"}})[0]["userid"]}]}]
    rops = [{"operationtype":0,"opmessage":{"mediatypeid":mid,"default_msg":1},
             "opmessage_usr":[{"userid":rpc("user.get",{"filter":{"username":"Admin"}})[0]["userid"]}]}]
    params={"name":name,"eventsource":0,"status":0,"esc_period":"1h",
            "operations":ops,"recovery_operations":rops,
            "filter":{"evaltype":0,"conditions":[]}}
    if existing:
        params["actionid"]=existing[0]["actionid"]; params.pop("eventsource",None)
        rpc("action.update",params); print("[action.update] notify")
    else:
        rpc("action.create",params); print("[action.create] notify")

def main():
    # Wait for web
    for _ in range(30):
        try:
            rpc("apiinfo.version",{},auth=False); break
        except Exception as e:
            print(f"  waiting Zabbix API... {e}"); time.sleep(4)
    # Try new PW first (idempotent), fallback to default
    try: login("Admin", ADMIN_NEW_PW)
    except: login("Admin", ADMIN_OLD_PW); change_admin_pw(ADMIN_OLD_PW); login("Admin", ADMIN_NEW_PW)

    mid = create_gmail_media()
    attach_media_to_admin(mid)

    host_ids = {}
    for h in HOSTS:
        host_ids[h["host"]] = ensure_host(h)

    for host_key, name, key_, url in HTTP_CHECKS:
        create_http_item(host_ids[host_key], host_key, name, key_, url)

    create_notify_action(mid)
    print("\n=== Zabbix setup complete ===")
    print(f"Web UI: http://100.64.10.54:8080  (Admin / {ADMIN_NEW_PW})")

if __name__=="__main__": main()
