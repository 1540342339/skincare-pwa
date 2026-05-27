// sw.js - 修复缓存，自动更新
const CACHE_NAME = 'skincare-pwa-v2'; // 每次部署建议递增版本号

self.addEventListener('install', event => {
  console.log('[SW] 安装新版本');
  // 跳过等待，立即激活
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  console.log('[SW] 激活新版本，清理旧缓存');
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.map(cache => {
          if (cache !== CACHE_NAME) {
            console.log('[SW] 删除旧缓存:', cache);
            return caches.delete(cache);
          }
        })
      );
    }).then(() => {
      // 让新 Service Worker 控制所有页面
      return self.clients.claim();
    })
  );
});

// 精简的 fetch 策略：优先网络，失败时回退缓存
self.addEventListener('fetch', event => {
  // 对于 API 请求不缓存
  if (event.request.url.includes('/api/')) {
    return;
  }
  event.respondWith(
    fetch(event.request)
      .then(response => {
        // 复制一份放入缓存
        const responseClone = response.clone();
        caches.open(CACHE_NAME).then(cache => {
          cache.put(event.request, responseClone);
        });
        return response;
      })
      .catch(() => {
        return caches.match(event.request);
      })
  );
});