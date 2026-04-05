// Service Worker - キャッシュなし版（常に最新を取得）
self.addEventListener('fetch', e => {
  e.respondWith(fetch(e.request));
});
