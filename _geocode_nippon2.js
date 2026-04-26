#!/usr/bin/env node
// nippon2_1-7 全スポットを一括ジオコーディング → STOPS用JSON出力
const https = require('https');
const fs = require('fs');
const API_KEY = 'AIzaSyBwPBSu3pJ7LBsQ7WvSbTWiQsFY0R8cREY';

// 全Day全スポット定義（time/name/search/pt/type/memo/dur）
const days = {
  nippon2_1: [
    {time:'15:00',name:'🏠 自宅出発',search:'江東区大島7丁目',pt:0,type:'move',memo:'7/14 火',dur:0},
    {time:'17:00',name:'⛴️ 大洗フェリーターミナル',search:'大洗フェリーターミナル 茨城',pt:0,type:'move',memo:'さんふらわあ受付',dur:0},
    {time:'18:45',name:'🚢 さんふらわあ出航',search:'大洗フェリーターミナル 茨城',pt:0,type:'move',memo:'船中泊→苫小牧',dur:0},
  ],
  nippon2_2: [
    {time:'14:00',name:'⛴️ 苫小牧フェリーターミナル',search:'苫小牧西港フェリーターミナル',pt:0,type:'move',memo:'7/15 水 上陸',dur:0},
    {time:'14:30',name:'🚀 苫小牧西IC',search:'苫小牧西IC 道央自動車道',pt:0,type:'move',memo:'道央道へ',dur:0},
    {time:'17:30',name:'🍑 砂川SA',search:'砂川SA 道央自動車道',pt:0,type:'qk',memo:'休憩',dur:10},
    {time:'19:30',name:'⬇️ 稚内IC',search:'稚内 国道40号',pt:0,type:'move',memo:'稚内市内へ',dur:0},
    {time:'20:00',name:'🏨 Hotel Trunk Wakkanai',search:'Hotel Trunk Wakkanai 稚内',pt:0,type:'goal',memo:'20:00まで着必須',dur:0},
  ],
  nippon2_3: [
    {time:'07:00',name:'🏨 Trunk Wakkanai 出発',search:'Hotel Trunk Wakkanai 稚内',pt:0,type:'move',memo:'7/16 木',dur:0},
    {time:'07:45',name:'📍 CP1 宗谷岬',search:'宗谷岬 稚内',pt:10,type:'goal',memo:'🏝️ 日本本土最北端',dur:15},
    {time:'10:00',name:'⭐ 道の駅 ロマン街道しょさんべつ',search:'道の駅 ロマン街道しょさんべつ',pt:1,type:'michi',memo:'観光応援',dur:10},
    {time:'12:30',name:'⭐ 道の駅 鐘のなるまち・ちっぷべつ',search:'道の駅 鐘のなるまち ちっぷべつ',pt:1,type:'michi',memo:'観光応援',dur:10},
    {time:'13:30',name:'🍑 上興部鉄道資料館',search:'上興部鉄道資料館 北海道',pt:1,type:'other',memo:'観光応援',dur:15},
    {time:'15:30',name:'⭐ 博物館網走監獄',search:'博物館網走監獄',pt:1,type:'other',memo:'観光応援',dur:30},
    {time:'17:00',name:'⭐ 白滝ジオパーク',search:'白滝ジオパーク 北海道',pt:1,type:'other',memo:'ジオパーク観光応援',dur:10},
    {time:'19:30',name:'🏨 ルートイン釧路駅前',search:'ホテルルートイン釧路駅前',pt:0,type:'goal',memo:'宿泊',dur:0},
  ],
  nippon2_4: [
    {time:'07:00',name:'🏨 ルートイン釧路 出発',search:'ホテルルートイン釧路駅前',pt:0,type:'move',memo:'7/17 金',dur:0},
    {time:'08:00',name:'⭐ 厚岸漁協市場',search:'厚岸漁業協同組合 地方卸売市場',pt:1,type:'other',memo:'観光応援・朝食',dur:30},
    {time:'10:30',name:'📍 CP2 納沙布岬',search:'納沙布岬 根室',pt:10,type:'goal',memo:'🏝️ 日本本土最東端',dur:15},
    {time:'11:30',name:'⭐ 道の駅 スワン44ねむろ',search:'道の駅 スワン44ねむろ',pt:1,type:'michi',memo:'観光応援',dur:15},
    {time:'14:00',name:'⭐ 道の駅 阿寒丹頂の里',search:'道の駅 阿寒丹頂の里',pt:1,type:'michi',memo:'観光応援',dur:15},
    {time:'15:30',name:'🍑 占冠PA',search:'占冠PA 道東自動車道',pt:0,type:'qk',memo:'道東道経由',dur:10},
    {time:'19:00',name:'🏨 ルートイン札幌白石',search:'ホテルルートイン札幌白石',pt:0,type:'goal',memo:'温泉・大浴場あり',dur:0},
  ],
  nippon2_5: [
    {time:'05:30',name:'🏨 ルートイン札幌白石 出発',search:'ホテルルートイン札幌白石',pt:0,type:'move',memo:'7/18 土・朝食抜き',dur:0},
    {time:'06:00',name:'🚀 札幌IC',search:'札幌IC 道央自動車道',pt:0,type:'move',memo:'札樽道→R230',dur:0},
    {time:'08:30',name:'🍑 中山峠コンビニ',search:'中山峠 北海道',pt:0,type:'qk',memo:'朝食補給',dur:15},
    {time:'09:30',name:'📍 CP3 尾花岬（太田緑地広場駐車場）',search:'太田緑地広場 せたな町',pt:6,type:'goal',memo:'🏝️ 北海道最西端',dur:15},
    {time:'12:00',name:'📍 CP4 白神岬',search:'白神岬 松前町',pt:6,type:'goal',memo:'🏝️ 北海道最南端',dur:15},
    {time:'12:50',name:'🍴 道の駅 北前船松前',search:'道の駅 北前船松前',pt:1,type:'michi',memo:'松前マグロ丼45分',dur:45},
    {time:'14:50',name:'⛴️ 函館フェリーターミナル',search:'函館フェリーターミナル',pt:0,type:'move',memo:'大函丸 16:00発',dur:0},
    {time:'17:30',name:'⛴️ 大間港 上陸',search:'大間港',pt:0,type:'move',memo:'青森入り',dur:0},
    {time:'17:45',name:'📍 CP5 大間崎',search:'大間崎',pt:10,type:'goal',memo:'🏝️ 本州最北端',dur:15},
    {time:'19:00',name:'♨️ 斗南温泉 美人の湯',search:'斗南温泉 美人の湯 むつ',pt:0,type:'qk',memo:'¥700 5-23時',dur:60},
    {time:'20:15',name:'🏨 Hotel Unisite Mutsu',search:'Hotel Unisite Mutsu',pt:0,type:'goal',memo:'宿泊',dur:0},
  ],
  nippon2_6: [
    {time:'07:00',name:'🏨 Unisite Mutsu 出発',search:'Hotel Unisite Mutsu',pt:0,type:'move',memo:'7/19 日',dur:0},
    {time:'07:30',name:'⭐ むつ来さまい館（下北ジオパーク）',search:'むつ来さまい館',pt:1,type:'other',memo:'下北ジオパーク打刻',dur:15},
    {time:'08:30',name:'⭐ 道の駅 みさわ',search:'道の駅 みさわ',pt:1,type:'michi',memo:'斗南藩記念観光村',dur:10},
    {time:'09:30',name:'⭐ 三沢航空科学館',search:'青森県立三沢航空科学館',pt:1,type:'other',memo:'9-17時',dur:30},
    {time:'11:00',name:'⭐ 蕪嶋神社',search:'蕪嶋神社 八戸',pt:1,type:'other',memo:'ウミネコ',dur:15},
    {time:'12:00',name:'🍴 種差海岸 駐車場',search:'種差海岸 八戸',pt:1,type:'other',memo:'昼飯',dur:45},
    {time:'13:30',name:'🚀 八戸IC',search:'八戸IC 八戸自動車道',pt:0,type:'move',memo:'八戸道→東北道',dur:0},
    {time:'14:30',name:'⭐ 石神の丘美術館',search:'石神の丘美術館 岩手町',pt:1,type:'other',memo:'観光応援',dur:15},
    {time:'15:30',name:'⭐ 道の駅 もりおか渋民 たみっと',search:'道の駅 もりおか渋民 たみっと',pt:1,type:'michi',memo:'観光応援',dur:10},
    {time:'16:00',name:'⭐ 志波城跡',search:'志波城跡 盛岡',pt:1,type:'other',memo:'観光応援',dur:10},
    {time:'17:00',name:'⭐ 道の駅 区界高原',search:'道の駅 区界高原',pt:1,type:'michi',memo:'観光応援',dur:10},
    {time:'18:00',name:'📍 CP6 魹ヶ崎',search:'道の駅 みなとオアシスみやこ シートピアなあど',pt:10,type:'goal',memo:'🏝️ 本州最東端',dur:15},
    {time:'18:30',name:'⭐ 道の駅 高田松原',search:'道の駅 高田松原',pt:1,type:'michi',memo:'観光応援',dur:10},
    {time:'19:30',name:'⭐ 石ノ森萬画館',search:'石ノ森萬画館 石巻',pt:1,type:'other',memo:'観光応援',dur:15},
    {time:'21:00',name:'🏨 ルートイン仙台泉',search:'ホテルルートイン仙台泉インター',pt:0,type:'goal',memo:'宿泊',dur:0},
  ],
  nippon2_7: [
    {time:'07:00',name:'🏨 ルートイン仙台泉 出発',search:'ホテルルートイン仙台泉インター',pt:0,type:'move',memo:'7/20 月祝',dur:0},
    {time:'07:15',name:'🚀 仙台泉IC',search:'仙台泉IC 東北自動車道',pt:0,type:'move',memo:'東北道南下',dur:0},
    {time:'09:00',name:'🍑 那須高原SA',search:'那須高原SA 東北自動車道',pt:0,type:'qk',memo:'休憩',dur:15},
    {time:'10:30',name:'🍑 蓮田SA',search:'蓮田SA 東北自動車道',pt:0,type:'qk',memo:'休憩',dur:10},
    {time:'11:00',name:'⬇️ 川口JCT',search:'川口JCT 首都高',pt:0,type:'move',memo:'首都高6号',dur:0},
    {time:'11:30',name:'🏁 自宅 GOAL',search:'江東区大島7丁目',pt:0,type:'goal',memo:'🏆完走',dur:0},
  ],
};

function geocode(q){return new Promise((res,rej)=>{
  const url=`https://maps.googleapis.com/maps/api/geocode/json?address=${encodeURIComponent(q)}&language=ja&region=jp&key=${API_KEY}`;
  https.get(url,r=>{let b='';r.on('data',c=>b+=c);r.on('end',()=>{try{const d=JSON.parse(b);if(d.status==='OK'&&d.results[0]){const l=d.results[0].geometry.location;res({lat:l.lat,lng:l.lng});}else res(null);}catch(e){rej(e);}});}).on('error',rej);
});}

(async()=>{
  let lines=[];
  for(const [key,stops] of Object.entries(days)){
    lines.push(`],${key}:[`);
    lines.push(`// ${key}`);
    for(const s of stops){
      const g=await geocode(s.search);
      const lat=g?g.lat.toFixed(4):'?';
      const lng=g?g.lng.toFixed(4):'?';
      lines.push(`{time:"${s.time}",name:"${s.name}",lat:${lat},lng:${lng},pt:${s.pt},type:"${s.type}",memo:"${s.memo}",dur:${s.dur}},`);
      console.log(`  ${g?'✓':'✗'} ${s.name} → ${lat},${lng}`);
      await new Promise(r=>setTimeout(r,200));
    }
  }
  fs.writeFileSync('C:/Users/Drus/sstr-tracker/_nippon2_stops.js',lines.join('\n'),'utf8');
  console.log('\nWrote _nippon2_stops.js');
})();
