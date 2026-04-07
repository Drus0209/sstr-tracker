const http = require('http');
const fs = require('fs');
const path = require('path');

const SPEAKER = 3; // ずんだもん（ノーマル）
const OUT_DIR = path.join(__dirname, 'www', 'voice');

// アプリで使う全フレーズ
const phrases = {
  // スケジュール
  'on_time': 'ほぼ予定通りなのだ。',
  'ahead_5': '予定より5分早いのだ。',
  'ahead_10': '予定より10分早いのだ。',
  'ahead_20': '予定より20分早いのだ。',
  'ahead_30': '予定より30分早いのだ。',
  'behind_5': '予定より5分遅れているのだ。',
  'behind_10': '予定より10分遅れているのだ。ペースを上げるのだ！',
  'behind_20': '予定より20分遅れているのだ。ペースを上げるのだ！',
  'behind_30': '予定より30分遅れているのだ。巻いていくのだ！',
  'behind_60': '予定より1時間遅れているのだ。巻いていくのだ！',
  // 距離
  'dist_1': '約1キロ先なのだ。',
  'dist_2': '約2キロ先なのだ。',
  'dist_3': '約3キロ先なのだ。',
  'dist_5': '約5キロ先なのだ。',
  'dist_10': '約10キロ先なのだ。',
  'dist_20': '約20キロ先なのだ。',
  'dist_30': '約30キロ先なのだ。',
  'dist_50': '約50キロ先なのだ。',
  'dist_100': '約100キロ先なのだ。',
  'dist_150': '約150キロ先なのだ。',
  'dist_200': '約200キロ先なのだ。',
  // オービス
  'orbis_1km': 'この先1キロ、オービスなのだ。速度注意なのだ。',
  'orbis_300m': 'まもなくオービスなのだ！速度注意なのだ！',
  'orbis_speed': '速度注意なのだ！',
  // 取り締まり
  'police_area': 'この先、取り締まり注意区間なのだ。',
  'shirobai_area': 'この先、白バイ注意区間なのだ。',
  // 制限速度
  'limit_40': '制限速度40キロなのだ。',
  'limit_50': '制限速度50キロなのだ。',
  'limit_60': '制限速度60キロなのだ。',
  'limit_80': '制限速度80キロなのだ。',
  'limit_100': '制限速度100キロなのだ。',
  // 15pt達成
  'pt_15': '15ポイント達成なのだ！完走条件クリアなのだ！おめでとうなのだ！',
  // GPS
  'gps_ok': 'GPS情報を取得したのだ。',
  // プラン選択
  'sstr_selected': 'SSTR2026が選択されたのだ。GPS情報取得までお待ちなのだ。',
  // 天気
  'rain_ahead': 'この先、雨の予報なのだ。気をつけるのだ。',
  // ゴール
  'goal_near': 'まもなくゴールなのだ！',
};

async function generateVoice(key, text) {
  return new Promise((resolve, reject) => {
    // Step 1: audio_query
    const queryReq = http.request({
      hostname: 'localhost', port: 50021,
      path: `/audio_query?text=${encodeURIComponent(text)}&speaker=${SPEAKER}`,
      method: 'POST'
    }, (res) => {
      let data = '';
      res.on('data', c => data += c);
      res.on('end', () => {
        // Step 2: synthesis
        const synthReq = http.request({
          hostname: 'localhost', port: 50021,
          path: `/synthesis?speaker=${SPEAKER}`,
          method: 'POST',
          headers: { 'Content-Type': 'application/json' }
        }, (res2) => {
          const chunks = [];
          res2.on('data', c => chunks.push(c));
          res2.on('end', () => {
            const wav = Buffer.concat(chunks);
            const outPath = path.join(OUT_DIR, key + '.wav');
            fs.writeFileSync(outPath, wav);
            console.log(`  ✓ ${key}: ${text} (${(wav.length/1024).toFixed(0)}KB)`);
            resolve();
          });
        });
        synthReq.on('error', reject);
        synthReq.write(data);
        synthReq.end();
      });
    });
    queryReq.on('error', reject);
    queryReq.end();
  });
}

async function main() {
  console.log(`Generating ${Object.keys(phrases).length} voice files with VOICEVOX (ずんだもん)...`);
  for (const [key, text] of Object.entries(phrases)) {
    await generateVoice(key, text);
    await new Promise(r => setTimeout(r, 200)); // rate limit
  }
  console.log(`\nDone! ${Object.keys(phrases).length} files in www/voice/`);
}

main().catch(e => console.error(e));
