#!/usr/bin/env node
// SSTR2026スポット一括ジオコーディング
const fs = require('fs');
const https = require('https');

const API_KEY = 'AIzaSyBwPBSu3pJ7LBsQ7WvSbTWiQsFY0R8cREY';
const JSON_PATH = 'C:/Users/Drus/sstr-tracker/www/sstr2026_spots.json';

function geocode(addr) {
  return new Promise((resolve, reject) => {
    const url = `https://maps.googleapis.com/maps/api/geocode/json?address=${encodeURIComponent(addr)}&language=ja&region=jp&key=${API_KEY}`;
    https.get(url, res => {
      let body = '';
      res.on('data', c => body += c);
      res.on('end', () => {
        try {
          const d = JSON.parse(body);
          if (d.status === 'OK' && d.results[0]) {
            const loc = d.results[0].geometry.location;
            resolve({ lat: loc.lat, lng: loc.lng });
          } else {
            resolve(null);
          }
        } catch (e) { reject(e); }
      });
    }).on('error', reject);
  });
}

async function main() {
  const data = JSON.parse(fs.readFileSync(JSON_PATH, 'utf8'));
  let resolved = 0, failed = 0, skipped = 0;
  for (let i = 0; i < data.spots.length; i++) {
    const s = data.spots[i];
    if (s.lat && s.lng) { skipped++; continue; }
    // 施設名+住所で検索精度アップ
    const query = `${s.name} ${s.addr}`;
    try {
      const loc = await geocode(query);
      if (loc) {
        s.lat = loc.lat; s.lng = loc.lng;
        resolved++;
        console.log(`  ✓ [${i+1}/${data.spots.length}] ${s.name} → ${loc.lat.toFixed(4)},${loc.lng.toFixed(4)}`);
      } else {
        // フォールバック：住所のみで再検索
        const loc2 = await geocode(s.addr);
        if (loc2) {
          s.lat = loc2.lat; s.lng = loc2.lng; resolved++;
          console.log(`  ○ [${i+1}/${data.spots.length}] ${s.name} (addr only) → ${loc2.lat.toFixed(4)},${loc2.lng.toFixed(4)}`);
        } else {
          failed++;
          console.log(`  ✗ [${i+1}/${data.spots.length}] ${s.name} (failed)`);
        }
      }
    } catch (e) {
      failed++;
      console.log(`  ✗ [${i+1}/${data.spots.length}] ${s.name} - ${e.message}`);
    }
    await new Promise(r => setTimeout(r, 200));
  }
  fs.writeFileSync(JSON_PATH, JSON.stringify(data, null, 2), 'utf8');
  console.log(`\nDone! resolved=${resolved}, skipped=${skipped}, failed=${failed}`);
}

main().catch(e => console.error(e));
