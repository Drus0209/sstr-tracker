#!/bin/bash
# NASセットアップスクリプト
# 実行: bash setup.sh

INSTALL_DIR="/volume1/home/Drus/sstr-api"

echo "=== SSTR API Server Setup ==="

# ディレクトリ作成
mkdir -p "$INSTALL_DIR"
cp fetch_stats.py server.py requirements.txt "$INSTALL_DIR/"

# pip install
echo "Installing Python packages..."
pip3 install -r "$INSTALL_DIR/requirements.txt" --user

# サービスアカウントキーの確認
if [ ! -f "$INSTALL_DIR/service-account-key.json" ]; then
    echo ""
    echo "⚠️  サービスアカウントキーが必要です！"
    echo "1. https://console.cloud.google.com/iam-admin/serviceaccounts?project=sstr-492316 を開く"
    echo "2. デフォルトのサービスアカウントを選択（または新規作成）"
    echo "3. 「キー」タブ → 「鍵を追加」→「新しい鍵を作成」→ JSON"
    echo "4. ダウンロードしたJSONを $INSTALL_DIR/service-account-key.json に配置"
    echo ""
fi

# 初回データ取得
echo "Fetching initial stats..."
export GOOGLE_APPLICATION_CREDENTIALS="$INSTALL_DIR/service-account-key.json"
cd "$INSTALL_DIR" && python3 fetch_stats.py

# cron設定（3時間に1回）
CRON_CMD="0 */3 * * * cd $INSTALL_DIR && GOOGLE_APPLICATION_CREDENTIALS=$INSTALL_DIR/service-account-key.json python3 fetch_stats.py >> /tmp/sstr-fetch.log 2>&1"
(crontab -l 2>/dev/null | grep -v "fetch_stats.py"; echo "$CRON_CMD") | crontab -

echo ""
echo "=== サーバー起動 ==="
echo "手動起動: cd $INSTALL_DIR && python3 server.py"
echo "バックグラウンド: cd $INSTALL_DIR && nohup python3 server.py > /tmp/sstr-api.log 2>&1 &"
echo ""
echo "エンドポイント: http://100.64.1.46:3456/api/usage"
