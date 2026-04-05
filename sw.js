const CACHE = 'sstr-2026-v2';
const FILES = [
  '/sstr-tracker/',
  '/sstr-tracker/index.html',
  '/sstr-tracker/bg.jpg',
  '/sstr-tracker/bg2.jpg',
  '/sstr-tracker/icon-192.png',
  '/sstr-tracker/icon-512.png',
  '/sstr-tracker/maou_bgm_neorock83.mp3'
];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(FILES)));
});

self.addEventListener('fetch', e => {
  e.respondWith(
    caches.match(e.request).then(r => r || fetch(e.request))
  );
});
