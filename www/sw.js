// Service Worker - バージョンチェック付き自動更新
const CURRENT_VERSION = 'v.260405132.b909c5b';
const CACHE = 'sstr-' + CURRENT_VERSION;

self.addEventListener('install', e => {
  self.skipWaiting(); // 即座にアクティベート
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll([
      '/sstr-tracker/',
      '/sstr-tracker/index.html',
      '/sstr-tracker/bg.jpg',
      '/sstr-tracker/bg2.jpg',
      '/sstr-tracker/maou_bgm_neorock83.mp3',
      '/sstr-tracker/icon-192.png',
      '/sstr-tracker/icon-512.png',
    ]))
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim()) // 全クライアントを即座に制御
  );
});

self.addEventListener('fetch', e => {
  // index.htmlは常にネットワークから取得（最新確認）
  if(e.request.url.includes('index.html') || e.request.url.endsWith('/sstr-tracker/')) {
    e.respondWith(
      fetch(e.request).then(res => {
        const clone = res.clone();
        caches.open(CACHE).then(c => c.put(e.request, clone));
        return res;
      }).catch(() => caches.match(e.request))
    );
  } else {
    e.respondWith(
      caches.match(e.request).then(r => r || fetch(e.request))
    );
  }
});
