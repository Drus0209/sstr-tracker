# OCI Zabbix 監視スタック

## 構成
- Oracle Cloud Ampere A1 (aarch64) Ubuntu 24.04
- Tailscale 経由で自宅 NAS/PC/スイッチを監視
- Zabbix 7.0 LTS + MySQL 8.0 + zabbix-agent2 + snmptraps

## デプロイ
```bash
# 初回
scp -i ~/.ssh/sstr-monitor -r oci ubuntu@<vm-ip>:~/
ssh -i ~/.ssh/sstr-monitor ubuntu@<vm-ip>
cd ~/oci
cp .env.example .env  # 各値を実際のものに編集
docker compose up -d

# Zabbix初期設定（PW変更・Gmail通知・ホスト登録）
set -a && . .env && set +a
python3 setup_zabbix.py
```

## アクセス
- Web UI: http://<tailscale-ip>:8080
- 初期ログイン: Admin / zabbix

## アイドル回収対策
`cron/stress-keepalive` 参照。毎時1分CPU負荷で Always Free 回収を回避。
